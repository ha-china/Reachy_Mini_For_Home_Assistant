"""Voice satellite protocol for Reachy Mini."""

import importlib.metadata
import logging
import threading
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..vision.camera_server import MJPEGCameraServer

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    HomeAssistantStateResponse,
    VoiceAssistantAudio,
    VoiceAssistantExternalWakeWord,
)
from google.protobuf import message
from pymicro_wakeword import MicroWakeWord
from pyopen_wakeword import OpenWakeWord

from ..entities.event_emotion_mapper import BuiltinBehaviorController, EventEmotionMapper
from ..models import AvailableWakeWord, ServerState
from ..reachy_controller import ReachyController
from .api_server import APIServer
from .entity_bridge import (
    bind_camera_callbacks,
    create_entity_registry,
    initialize_entities,
    load_optional_mappings,
    on_authenticated as replay_entity_states,
    run_ha_disconnected_callback,
    update_camera_server as update_entity_bridge_camera_server,
)
from .message_dispatch import handle_message as dispatch_message
from .motion_bridge import (
    enter_motion_state,
    play_emotion,
    queue_emotion_move,
    reachy_on_idle,
    reachy_on_listening,
    reachy_on_speaking,
    reachy_on_thinking,
    reachy_on_timer_finished,
    run_motion_state,
    set_conversation_mode,
    turn_to_sound_source,
)
from .session_flow import (
    cancel_delayed_idle_return,
    clear_conversation,
    get_or_create_conversation_id,
    on_wakeup_sound_finished,
    play_wakeup_sound,
    queue_voice_request_after_wakeup,
    schedule_delayed_idle_return,
    tts_finished,
)
from .voice_pipeline import (
    duck,
    handle_timer_event,
    handle_voice_event,
    play_timer_finished,
    play_tts,
    stop as stop_pipeline,
    unduck,
)
from .wakeword_assets import download_external_wake_word

_LOGGER = logging.getLogger(__name__)
IDLE_RETURN_DELAY_S = 10.0

try:
    _AIOESPHOMEAPI_VERSION = importlib.metadata.version("aioesphomeapi")
except Exception:
    _AIOESPHOMEAPI_VERSION = "unknown"


class VoiceSatelliteProtocol(APIServer):
    """Voice satellite protocol handler for ESPHome."""

    def __init__(
        self, state: ServerState, camera_server: Optional["MJPEGCameraServer"] = None, voice_assistant_service=None
    ) -> None:
        _LOGGER.info("VoiceSatelliteProtocol.__init__ called - new connection")
        super().__init__(state.name)
        self.state = state
        self.state.satellite = self
        self.camera_server = camera_server
        self._voice_assistant_service = voice_assistant_service  # Store reference for mute functionality
        self._aioesphomeapi_version = _AIOESPHOMEAPI_VERSION

        # Home Assistant connection callbacks
        self._on_ha_connected_callback = None
        self._on_ha_disconnected_callback = None

        # Initialize streaming state early (before entity setup)
        self._is_streaming_audio = False
        self._tts_url: str | None = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._timer_ring_start: float | None = None
        self._pending_voice_request: tuple[str | None, str | None] | None = None
        self._external_wake_words: dict[str, VoiceAssistantExternalWakeWord] = {}
        self._optional_mappings_loaded = False

        # Conversation tracking for continuous conversation
        self._conversation_id: str | None = None
        self._conversation_timeout = 300.0  # 5 minutes, same as ESPHome default
        self._last_conversation_time = 0.0

        # Track Home Assistant entity states for change detection
        self._ha_entity_states: dict[str, str] = {}
        self._idle_return_timer: threading.Timer | None = None
        self._pipeline_active = False

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        # Connect MovementManager to ReachyController for pose control from HA
        if state.motion is not None and state.motion.movement_manager is not None:
            self.reachy_controller.set_movement_manager(state.motion.movement_manager)

            # Setup speech sway callback for audio-driven head motion
            def sway_callback(sway: dict) -> None:
                mm = state.motion.movement_manager
                if mm is not None:
                    mm.set_speech_sway(
                        sway.get("x_m", 0.0),
                        sway.get("y_m", 0.0),
                        sway.get("z_m", 0.0),
                        sway.get("roll_rad", 0.0),
                        sway.get("pitch_rad", 0.0),
                        sway.get("yaw_rad", 0.0),
                    )

            state.tts_player.set_sway_callback(sway_callback)
            _LOGGER.info("Speech sway callback configured for TTS player")

        # Initialize entity registry
        self._entity_registry = create_entity_registry(self)

        # Connect gesture state callback
        bind_camera_callbacks(self, camera_server)

        self._event_emotion_mapper = EventEmotionMapper()
        self._behavior_controller = BuiltinBehaviorController(
            event_mapper=self._event_emotion_mapper,
            cancel_delayed_idle_return=self._cancel_delayed_idle_return,
            set_conversation_mode=self._set_conversation_mode,
            enter_motion_state=self._enter_motion_state,
            run_motion_state=self._run_motion_state,
            queue_emotion_move=self._queue_emotion_move,
        )
        _LOGGER.info("Event emotion mapper initialized")

        # Only setup entities once (check if already initialized)
        # This prevents duplicate entity registration on reconnection
        initialize_entities(self)

        # Initialize emotion keyword detector for auto-triggering emotions from LLM responses
        # DISABLED: Emotion detection moved to Home Assistant blueprint
        # self._emotion_detector = EmotionKeywordDetector(play_emotion_callback=self._play_emotion)
        _LOGGER.info("VoiceSatelliteProtocol.__init__ completed")

    def set_ha_connection_callbacks(self, on_connected, on_disconnected):
        """Set callbacks for Home Assistant connection/disconnection."""
        self._on_ha_connected_callback = on_connected
        self._on_ha_disconnected_callback = on_disconnected

    def connection_made(self, transport) -> None:
        """Called when a client connects."""
        peer = transport.get_extra_info("peername")
        _LOGGER.info("ESPHome client connected from %s", peer)
        super().connection_made(transport)

    def update_camera_server(self, camera_server):
        """Update the camera server reference in entity registry.

        Called when camera server is started after Home Assistant connection.
        """
        update_entity_bridge_camera_server(self, camera_server)

    def _load_optional_mappings(self) -> None:
        load_optional_mappings(self)

    # Note: connection_lost is defined later in the class with full cleanup logic

    def handle_voice_event(self, event_type, data: dict[str, str]) -> None:
        handle_voice_event(self, event_type, data)

    def handle_timer_event(self, event_type, msg) -> None:
        handle_timer_event(self, event_type, msg)

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        yield from dispatch_message(self, msg)

    @property
    def is_streaming_audio(self) -> bool:
        return self._is_streaming_audio

    def handle_audio(self, audio_chunk: bytes) -> None:
        if not self._is_streaming_audio:
            return
        # Check if transport is still valid before sending
        if self._writelines is None:
            _LOGGER.warning("Cannot send audio: transport not available, stopping stream")
            self._is_streaming_audio = False
            return
        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def _get_or_create_conversation_id(self) -> str:
        return get_or_create_conversation_id(self)

    def _clear_conversation(self) -> None:
        clear_conversation(self)

    def wakeup(self, wake_word: MicroWakeWord | OpenWakeWord) -> None:
        """Handle wake word detection - start voice pipeline."""
        if self._timer_finished:
            self._timer_finished = False
            self._timer_ring_start = None
            self.unduck()
            self.state.active_wake_words.discard(self.state.stop_word.id)
            self._set_stop_word_active(False)
            self.state.tts_player.stop()
            _LOGGER.debug("Stopping timer finished sound")
            return

        if self.state.is_muted:
            return

        if self._pipeline_active:
            _LOGGER.debug("Ignoring wake word - pipeline already active")
            return

        wake_word_phrase = wake_word.wake_word
        _LOGGER.debug("Detected wake word: %s", wake_word_phrase)

        self._turn_to_sound_source()
        conv_id = self._get_or_create_conversation_id()
        self._pipeline_active = True
        self.duck()
        self._queue_voice_request_after_wakeup(wake_word_phrase=wake_word_phrase, conversation_id=conv_id)
        self._play_wakeup_sound()

    def _queue_voice_request_after_wakeup(
        self, *, wake_word_phrase: str | None = None, conversation_id: str | None = None
    ) -> None:
        queue_voice_request_after_wakeup(self, wake_word_phrase=wake_word_phrase, conversation_id=conversation_id)

    def _on_wakeup_sound_finished(self) -> None:
        on_wakeup_sound_finished(self)

    def _play_wakeup_sound(self) -> None:
        play_wakeup_sound(self)

    def on_authenticated(self) -> None:
        replay_entity_states(self)

    def stop(self) -> None:
        stop_pipeline(self)

    def play_tts(self) -> None:
        play_tts(self)

    def duck(self) -> None:
        duck(self)

    def unduck(self) -> None:
        unduck(self)

    def _tts_finished(self) -> None:
        tts_finished(self)

    def _cancel_delayed_idle_return(self) -> None:
        cancel_delayed_idle_return(self)

    def _schedule_delayed_idle_return(self) -> None:
        schedule_delayed_idle_return(self, IDLE_RETURN_DELAY_S)

    def _set_face_tracking_for_state(self, enabled: bool, context: str) -> None:
        from .motion_bridge import set_face_tracking_for_state

        set_face_tracking_for_state(self, enabled, context)

    def _enter_motion_state(self, context: str, callback_name: str, *, face_tracking: bool | None = None) -> None:
        enter_motion_state(self, context, callback_name, face_tracking=face_tracking)

    def _run_motion_state(self, context: str, callback_name: str) -> None:
        run_motion_state(self, context, callback_name)

    def _set_stop_word_active(self, active: bool) -> None:
        """Toggle stop word detector when model supports runtime activation."""
        try:
            self.state.stop_word.is_active = active
        except Exception:
            pass

    def _play_timer_finished(self) -> None:
        play_timer_finished(self)

    def connection_lost(self, exc):
        super().connection_lost(exc)
        _LOGGER.info("Disconnected from Home Assistant")
        self._cancel_delayed_idle_return()
        # Clear streaming state on disconnect
        self._is_streaming_audio = False
        self._pipeline_active = False
        self._pending_voice_request = None
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._timer_ring_start = None
        self._set_stop_word_active(False)

        run_ha_disconnected_callback(self)

    def _download_external_wake_word(
        self, external_wake_word: VoiceAssistantExternalWakeWord
    ) -> AvailableWakeWord | None:
        return download_external_wake_word(self, external_wake_word)

    # -------------------------------------------------------------------------
    # Reachy Mini Motion Control
    # -------------------------------------------------------------------------

    def _turn_to_sound_source(self) -> None:
        turn_to_sound_source(self)

    def _reachy_on_listening(self) -> None:
        reachy_on_listening(self)

    def _reachy_on_thinking(self) -> None:
        reachy_on_thinking(self)

    def _reachy_on_speaking(self) -> None:
        reachy_on_speaking(self)

    def _reachy_on_idle(self) -> None:
        reachy_on_idle(self)

    def _set_conversation_mode(self, in_conversation: bool) -> None:
        set_conversation_mode(self, in_conversation)

    def _reachy_on_timer_finished(self) -> None:
        reachy_on_timer_finished(self)

    def _play_emotion(self, emotion_name: str) -> None:
        play_emotion(self, emotion_name)

    def _queue_emotion_move(self, emotion_name: str) -> None:
        queue_emotion_move(self, emotion_name)

    def _handle_ha_state_change(self, msg: HomeAssistantStateResponse) -> None:
        from .entity_bridge import handle_ha_state_change

        handle_ha_state_change(self, msg)

    def suspend(self) -> None:
        """Suspend the satellite runtime resources.

        Stops any current playback and releases resources.
        """
        _LOGGER.info("Suspending VoiceSatellite resources...")
        self._cancel_delayed_idle_return()
        self._pipeline_active = False
        self._pending_voice_request = None
        self._timer_finished = False
        self._timer_ring_start = None

        # Stop any current TTS/music
        if self.state.tts_player:
            self.state.tts_player.stop()
        if self.state.music_player:
            self.state.music_player.stop()

        # Keep configured wake words intact.
        # Audio processing is paused by runtime resource suspension, so clearing wake words here
        # can cause Home Assistant UI to temporarily show an empty wake word selection.

        # Reset conversation state
        self._tts_url = None
        self._tts_played = True
        self._continue_conversation = False
        self._is_streaming_audio = False

        _LOGGER.info("VoiceSatellite suspended")

    def resume(self) -> None:
        """Resume the satellite runtime resources."""
        _LOGGER.info("Resuming VoiceSatellite resources...")

        # Ensure wake word processing context is refreshed after resume.
        self.state.wake_words_changed = True

        _LOGGER.info("VoiceSatellite resumed")
