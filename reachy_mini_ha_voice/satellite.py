"""Voice satellite protocol for Reachy Mini."""

import hashlib
import logging
import math
import posixpath
import shutil
import time
from collections.abc import Iterable
from typing import Dict, Optional, Set, Union, TYPE_CHECKING
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

if TYPE_CHECKING:
    from .camera_server import MJPEGCameraServer

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ButtonCommandRequest,
    CameraImageRequest,
    DeviceInfoRequest,
    DeviceInfoResponse,
    HomeAssistantStateResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    NumberCommandRequest,
    SelectCommandRequest,
    SubscribeHomeAssistantStatesRequest,
    SubscribeStatesRequest,
    SwitchCommandRequest,
    VoiceAssistantAnnounceFinished,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAudio,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantExternalWakeWord,
    VoiceAssistantRequest,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.model import (
    VoiceAssistantEventType,
    VoiceAssistantFeature,
    VoiceAssistantTimerEventType,
)
from google.protobuf import message
from pymicro_wakeword import MicroWakeWord
from pyopen_wakeword import OpenWakeWord

from .api_server import APIServer
from .entity import MediaPlayerEntity
from .entity_registry import EntityRegistry, get_entity_key
from .models import AvailableWakeWord, ServerState, WakeWordType
from .util import call_all
from .reachy_controller import ReachyController
from .motion.gesture_actions import GestureActionMapper
from .entities.event_emotion_mapper import EventEmotionMapper
from .entities.emotion_detector import EmotionKeywordDetector

_LOGGER = logging.getLogger(__name__)


class VoiceSatelliteProtocol(APIServer):
    """Voice satellite protocol handler for ESPHome."""

    def __init__(self, state: ServerState, camera_server: Optional["MJPEGCameraServer"] = None) -> None:
        _LOGGER.info("VoiceSatelliteProtocol.__init__ called - new connection")
        super().__init__(state.name)
        self.state = state
        self.state.satellite = self
        self.camera_server = camera_server

        # Initialize streaming state early (before entity setup)
        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._external_wake_words: Dict[str, VoiceAssistantExternalWakeWord] = {}

        # Conversation tracking for continuous conversation
        self._conversation_id: Optional[str] = None
        self._conversation_timeout = 300.0  # 5 minutes, same as ESPHome default
        self._last_conversation_time = 0.0

        # Track Home Assistant entity states for change detection
        self._ha_entity_states: Dict[str, str] = {}

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        # Connect sleep/wake callbacks to ServerState callbacks
        def on_sleep_from_ha():
            if state.on_ha_sleep is not None:
                try:
                    state.on_ha_sleep()
                except Exception as e:
                    _LOGGER.error("Error in on_ha_sleep callback: %s", e)

        def on_wake_from_ha():
            if state.on_ha_wake is not None:
                try:
                    state.on_ha_wake()
                except Exception as e:
                    _LOGGER.error("Error in on_ha_wake callback: %s", e)

        self.reachy_controller.set_sleep_callback(on_sleep_from_ha)
        self.reachy_controller.set_wake_callback(on_wake_from_ha)

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
        self._entity_registry = EntityRegistry(
            server=self,
            reachy_controller=self.reachy_controller,
            camera_server=camera_server,
            play_emotion_callback=self._play_emotion,
        )

        # Connect gesture state callback
        if camera_server:
            camera_server.set_gesture_state_callback(self._entity_registry.update_gesture_state)
            camera_server.set_face_state_callback(self._entity_registry.update_face_detected_state)
            camera_server.set_gesture_action_callback(self.handle_detected_gesture)

        # Initialize gesture action mapper for local gesture → action handling
        self._gesture_action_mapper = GestureActionMapper()
        self._gesture_action_mapper.set_emotion_callback(self._play_emotion)
        self._gesture_action_mapper.set_start_listening_callback(self._trigger_wake_word)
        self._gesture_action_mapper.set_stop_speaking_callback(self._stop_current_tts)
        self._gesture_action_mapper.set_ha_event_callback(self._send_gesture_event_to_ha)
        _LOGGER.info("Gesture action mapper initialized")

        # Initialize event-emotion mapper for HA state change reactions
        self._event_emotion_mapper = EventEmotionMapper()
        self._event_emotion_mapper.set_emotion_callback(self._play_emotion)
        # Load custom mappings from JSON if available
        from pathlib import Path
        mappings_file = Path(__file__).parent / "animations" / "event_mappings.json"
        if mappings_file.exists():
            self._event_emotion_mapper.load_from_json(mappings_file)
        _LOGGER.info("Event emotion mapper initialized")

        # Only setup entities once (check if already initialized)
        # This prevents duplicate entity registration on reconnection
        try:
            _LOGGER.info("Checking entity initialization state...")
            if not getattr(self.state, '_entities_initialized', False):
                _LOGGER.info("Setting up entities for first time...")
                if self.state.media_player_entity is None:
                    _LOGGER.info("Creating MediaPlayerEntity...")
                    self.state.media_player_entity = MediaPlayerEntity(
                        server=self,
                        key=get_entity_key("reachy_mini_media_player"),
                        name="Media Player",
                        object_id="reachy_mini_media_player",
                        music_player=state.music_player,
                        announce_player=state.tts_player,
                    )
                    self.state.entities.append(self.state.media_player_entity)
                    _LOGGER.info("MediaPlayerEntity created")

                # Setup all entities using the registry
                _LOGGER.info("Setting up all entities via registry...")
                self._entity_registry.setup_all_entities(self.state.entities)

                # Mark entities as initialized
                self.state._entities_initialized = True
                _LOGGER.info("Entities initialized: %d total", len(self.state.entities))
            else:
                _LOGGER.info("Entities already initialized, updating server references")
                # Update server reference in existing entities
                for entity in self.state.entities:
                    entity.server = self
                _LOGGER.info("Server references updated for %d entities", len(self.state.entities))
        except Exception as e:
            _LOGGER.error("Error during entity setup: %s", e, exc_info=True)
            raise

        # Initialize emotion keyword detector for auto-triggering emotions from LLM responses
        self._emotion_detector = EmotionKeywordDetector(play_emotion_callback=self._play_emotion)
        _LOGGER.info("VoiceSatelliteProtocol.__init__ completed")

    def connection_made(self, transport) -> None:
        """Called when a client connects."""
        peer = transport.get_extra_info('peername')
        _LOGGER.info("ESPHome client connected from %s", peer)
        super().connection_made(transport)

    def connection_lost(self, exc) -> None:
        """Called when a client disconnects."""
        _LOGGER.info("ESPHome client disconnected: %s", exc)
        super().connection_lost(exc)

    def handle_voice_event(
        self, event_type: VoiceAssistantEventType, data: Dict[str, str]
    ) -> None:
        _LOGGER.debug("Voice event: type=%s, data=%s", event_type.name, data)

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            self._tts_url = data.get("url")
            self._tts_played = False
            self._continue_conversation = False
            # Reachy Mini: Start listening animation
            self._reachy_on_listening()

            # Note: TTS URL requires HA authentication, cannot pre-download
            # Speaking animation uses JSON-defined multi-frequency sway instead

        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            self._is_streaming_audio = False
            # Reachy Mini: Stop listening, start thinking
            self._reachy_on_thinking()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            if data.get("tts_start_streaming") == "1":
                # Start streaming early
                self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
            # Reachy Mini: Start speaking animation (JSON-defined multi-frequency sway)
            _LOGGER.debug("TTS_START event received, triggering speaking animation")
            self._reachy_on_speaking()

            # Auto-trigger emotion based on response text
            # TTS_START may contain the text to be spoken
            tts_text = data.get("tts_output") or data.get("text") or ""
            if tts_text:
                self._emotion_detector.detect_and_play(tts_text)

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            self._tts_url = data.get("url")
            self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            # Pipeline run ended
            self._is_streaming_audio = False

            # Following reference project pattern
            if not self._tts_played:
                self._tts_finished()

            self._tts_played = False

    def handle_timer_event(
        self,
        event_type: VoiceAssistantTimerEventType,
        msg: VoiceAssistantTimerEventResponse,
    ) -> None:
        _LOGGER.debug("Timer event: type=%s", event_type.name)

        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            if not self._timer_finished:
                self.state.active_wake_words.add(self.state.stop_word.id)
                self._timer_finished = True
                self.duck()
                self._play_timer_finished()
                # Reachy Mini: Timer finished animation
                self._reachy_on_timer_finished()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, VoiceAssistantEventResponse):
            # Pipeline event
            data: Dict[str, str] = {}
            for arg in msg.data:
                data[arg.name] = arg.value
            self.handle_voice_event(VoiceAssistantEventType(msg.event_type), data)

        elif isinstance(msg, VoiceAssistantAnnounceRequest):
            _LOGGER.debug("Announcing: %s", msg.text)
            assert self.state.media_player_entity is not None

            urls = []
            if msg.preannounce_media_id:
                urls.append(msg.preannounce_media_id)
            urls.append(msg.media_id)

            self.state.active_wake_words.add(self.state.stop_word.id)
            self._continue_conversation = msg.start_conversation
            self.duck()

            yield from self.state.media_player_entity.play(
                urls, announcement=True, done_callback=self._tts_finished
            )

        elif isinstance(msg, VoiceAssistantTimerEventResponse):
            self.handle_timer_event(VoiceAssistantTimerEventType(msg.event_type), msg)

        elif isinstance(msg, HomeAssistantStateResponse):
            # Handle Home Assistant state changes for emotion mapping
            self._handle_ha_state_change(msg)

        elif isinstance(msg, DeviceInfoRequest):
            _LOGGER.info("DeviceInfoRequest received, sending DeviceInfoResponse")
            yield DeviceInfoResponse(
                uses_password=False,
                name=self.state.name,
                mac_address=self.state.mac_address,
                voice_assistant_feature_flags=(
                    VoiceAssistantFeature.VOICE_ASSISTANT
                    | VoiceAssistantFeature.API_AUDIO
                    | VoiceAssistantFeature.ANNOUNCE
                    | VoiceAssistantFeature.START_CONVERSATION
                    | VoiceAssistantFeature.TIMERS
                ),
            )

        elif isinstance(
            msg,
            (
                ListEntitiesRequest,
                SubscribeHomeAssistantStatesRequest,
                SubscribeStatesRequest,
                MediaPlayerCommandRequest,
                NumberCommandRequest,
                SwitchCommandRequest,
                SelectCommandRequest,
                ButtonCommandRequest,
                CameraImageRequest,
            ),
        ):
            for entity in self.state.entities:
                yield from entity.handle_message(msg)

            if isinstance(msg, ListEntitiesRequest):
                yield ListEntitiesDoneResponse()

        elif isinstance(msg, VoiceAssistantConfigurationRequest):
            available_wake_words = [
                VoiceAssistantWakeWord(
                    id=ww.id,
                    wake_word=ww.wake_word,
                    trained_languages=ww.trained_languages,
                )
                for ww in self.state.available_wake_words.values()
            ]

            for eww in msg.external_wake_words:
                if eww.model_type != "micro":
                    continue

                available_wake_words.append(
                    VoiceAssistantWakeWord(
                        id=eww.id,
                        wake_word=eww.wake_word,
                        trained_languages=eww.trained_languages,
                    )
                )
                self._external_wake_words[eww.id] = eww

            yield VoiceAssistantConfigurationResponse(
                available_wake_words=available_wake_words,
                active_wake_words=[
                    ww.id
                    for ww in self.state.wake_words.values()
                    if ww.id in self.state.active_wake_words
                ],
                max_active_wake_words=2,
            )

            _LOGGER.info("Connected to Home Assistant")

        elif isinstance(msg, VoiceAssistantSetConfiguration):
            # Change active wake words
            active_wake_words: Set[str] = set()

            for wake_word_id in msg.active_wake_words:
                if wake_word_id in self.state.wake_words:
                    # Already loaded, just add to active set
                    active_wake_words.add(wake_word_id)
                    continue

                model_info = self.state.available_wake_words.get(wake_word_id)
                if not model_info:
                    # Check external wake words (may require download)
                    external_wake_word = self._external_wake_words.get(wake_word_id)
                    if not external_wake_word:
                        _LOGGER.warning("Wake word not found: %s", wake_word_id)
                        continue

                    model_info = self._download_external_wake_word(external_wake_word)
                    if not model_info:
                        continue

                    self.state.available_wake_words[wake_word_id] = model_info

                _LOGGER.debug("Loading wake word: %s", model_info.wake_word_path)
                loaded_model = model_info.load()
                # Set id attribute on the model for later identification
                setattr(loaded_model, 'id', wake_word_id)
                self.state.wake_words[wake_word_id] = loaded_model
                _LOGGER.info("Wake word loaded: %s", wake_word_id)
                active_wake_words.add(wake_word_id)
                # Don't break - load ALL requested wake words, not just the first one

            self.state.active_wake_words = active_wake_words
            _LOGGER.debug("Active wake words: %s", active_wake_words)

            self.state.preferences.active_wake_words = list(active_wake_words)
            self.state.save_preferences()
            self.state.wake_words_changed = True

    def handle_audio(self, audio_chunk: bytes) -> None:
        if not self._is_streaming_audio:
            return
        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def _get_or_create_conversation_id(self) -> str:
        """Get existing conversation_id or create a new one.

        Reuses conversation_id if within timeout period, otherwise creates new one.
        """
        now = time.time()
        if (self._conversation_id is None or
                now - self._last_conversation_time > self._conversation_timeout):
            # Create new conversation_id
            import uuid
            self._conversation_id = str(uuid.uuid4())
            _LOGGER.debug("Created new conversation_id: %s", self._conversation_id)

        self._last_conversation_time = now
        return self._conversation_id

    def _clear_conversation(self) -> None:
        """Clear conversation state when exiting conversation mode."""
        self._conversation_id = None
        self._continue_conversation = False

    def wakeup(self, wake_word: Union[MicroWakeWord, OpenWakeWord]) -> None:
        """Handle wake word detection - start voice pipeline."""
        if self._timer_finished:
            # Stop timer instead
            self._timer_finished = False
            self.state.tts_player.stop()
            _LOGGER.debug("Stopping timer finished sound")
            return

        wake_word_phrase = wake_word.wake_word
        _LOGGER.debug("Detected wake word: %s", wake_word_phrase)

        # Turn toward sound source using DOA (Direction of Arrival)
        self._turn_to_sound_source()

        # Get or create conversation_id for context tracking
        conv_id = self._get_or_create_conversation_id()

        self.send_messages(
            [VoiceAssistantRequest(
                start=True,
                wake_word_phrase=wake_word_phrase,
                conversation_id=conv_id,
            )]
        )
        self.duck()
        self._is_streaming_audio = True
        self.state.tts_player.play(self.state.wakeup_sound)

    def stop(self) -> None:
        """Stop current TTS playback (e.g., user said stop word)."""
        self.state.active_wake_words.discard(self.state.stop_word.id)
        self.state.tts_player.stop()

        if self._timer_finished:
            self._timer_finished = False
            _LOGGER.debug("Stopping timer finished sound")
        else:
            _LOGGER.debug("TTS response stopped manually")
            self._tts_finished()

    def play_tts(self) -> None:
        if (not self._tts_url) or self._tts_played:
            return

        self._tts_played = True
        _LOGGER.debug("Playing TTS response: %s", self._tts_url)

        self.state.active_wake_words.add(self.state.stop_word.id)
        self.state.tts_player.play(self._tts_url, done_callback=self._tts_finished)

    def duck(self) -> None:
        _LOGGER.debug("Ducking music")
        self.state.music_player.duck()
        # Pause Sendspin to prevent audio conflicts during voice interaction
        self.state.music_player.pause_sendspin()

    def unduck(self) -> None:
        _LOGGER.debug("Unducking music")
        self.state.music_player.unduck()
        # Resume Sendspin audio
        self.state.music_player.resume_sendspin()

    def _tts_finished(self) -> None:
        """Called when TTS audio playback finishes.

        Following reference project pattern: handle continue conversation here.
        """
        self.state.active_wake_words.discard(self.state.stop_word.id)
        self.send_messages([VoiceAssistantAnnounceFinished()])

        # Check if should continue conversation
        # 1. Our switch is ON: Always continue (unconditional)
        # 2. Our switch is OFF: Follow HA's continue_conversation request
        continuous_mode = self.state.preferences.continuous_conversation
        should_continue = continuous_mode or self._continue_conversation

        if should_continue:
            _LOGGER.debug("Continuing conversation (our_switch=%s, ha_request=%s)",
                          continuous_mode, self._continue_conversation)

            # Play prompt sound to indicate ready for next input
            self.state.tts_player.play(self.state.wakeup_sound)

            # Use same conversation_id for context continuity
            conv_id = self._get_or_create_conversation_id()
            self.send_messages([VoiceAssistantRequest(
                start=True,
                conversation_id=conv_id,
            )])
            self._is_streaming_audio = True

            # Stay in listening mode
            self._reachy_on_listening()
        else:
            self._clear_conversation()
            self.unduck()
            _LOGGER.debug("Conversation finished")

            # Reachy Mini: Return to idle
            self._reachy_on_idle()

    def _play_timer_finished(self) -> None:
        if not self._timer_finished:
            self.unduck()
            return

        self.state.tts_player.play(
            self.state.timer_finished_sound,
            done_callback=lambda: call_all(
                lambda: time.sleep(1.0), self._play_timer_finished
            ),
        )

    def connection_lost(self, exc):
        super().connection_lost(exc)
        _LOGGER.info("Disconnected from Home Assistant")
        # Clear streaming state on disconnect
        self._is_streaming_audio = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False

    def _download_external_wake_word(
        self, external_wake_word: VoiceAssistantExternalWakeWord
    ) -> Optional[AvailableWakeWord]:
        eww_dir = self.state.download_dir / "external_wake_words"
        eww_dir.mkdir(parents=True, exist_ok=True)

        config_path = eww_dir / f"{external_wake_word.id}.json"
        should_download_config = not config_path.exists()

        # Check if we need to download the model file
        model_path = eww_dir / f"{external_wake_word.id}.tflite"
        should_download_model = True

        if model_path.exists():
            model_size = model_path.stat().st_size
            if model_size == external_wake_word.model_size:
                with open(model_path, "rb") as model_file:
                    model_hash = hashlib.sha256(model_file.read()).hexdigest()

                if model_hash == external_wake_word.model_hash:
                    should_download_model = False
                    _LOGGER.debug(
                        "Model size and hash match for %s. Skipping download.",
                        external_wake_word.id,
                    )

        if should_download_config or should_download_model:
            # Download config
            _LOGGER.debug("Downloading %s to %s", external_wake_word.url, config_path)
            with urlopen(external_wake_word.url) as request:
                if request.status != 200:
                    _LOGGER.warning(
                        "Failed to download: %s, status=%s",
                        external_wake_word.url,
                        request.status,
                    )
                    return None

                with open(config_path, "wb") as model_file:
                    shutil.copyfileobj(request, model_file)

        if should_download_model:
            # Download model file
            parsed_url = urlparse(external_wake_word.url)
            parsed_url = parsed_url._replace(
                path=posixpath.join(posixpath.dirname(parsed_url.path), model_path.name)
            )
            model_url = urlunparse(parsed_url)

            _LOGGER.debug("Downloading %s to %s", model_url, model_path)
            with urlopen(model_url) as request:
                if request.status != 200:
                    _LOGGER.warning(
                        "Failed to download: %s, status=%s", model_url, request.status
                    )
                    return None

                with open(model_path, "wb") as model_file:
                    shutil.copyfileobj(request, model_file)

        return AvailableWakeWord(
            id=external_wake_word.id,
            type=WakeWordType.MICRO_WAKE_WORD,
            wake_word=external_wake_word.wake_word,
            trained_languages=external_wake_word.trained_languages,
            wake_word_path=config_path,
        )

    # -------------------------------------------------------------------------
    # Reachy Mini Motion Control
    # -------------------------------------------------------------------------

    def _turn_to_sound_source(self) -> None:
        """Turn robot head toward sound source using DOA at wakeup.

        This is called once at wakeup to orient the robot toward the speaker.
        Face tracking will take over after the initial turn.

        DOA angle convention (from SDK):
        - 0 radians = left (Y+ direction in head frame)
        - π/2 radians = front (X+ direction in head frame)
        - π radians = right (Y- direction in head frame)

        The SDK uses: p_head = [sin(doa), cos(doa), 0]
        So we need to convert this to yaw angle.

        Note: We don't check speech_detected because by the time wake word
        detection completes, the user may have stopped speaking.
        """
        if not self.state.motion_enabled or not self.state.reachy_mini:
            _LOGGER.info("DOA turn-to-sound: motion disabled or no robot")
            return

        try:
            # Get DOA from reachy_controller (only read once)
            doa = self.reachy_controller.get_doa_angle()
            if doa is None:
                _LOGGER.info("DOA not available, skipping turn-to-sound")
                return

            angle_rad, speech_detected = doa
            _LOGGER.debug("DOA raw: angle=%.3f rad (%.1f°), speech=%s",
                          angle_rad, math.degrees(angle_rad), speech_detected)

            # Convert DOA to direction vector in head frame
            # SDK convention: p_head = [sin(doa), cos(doa), 0]
            # where X+ is front, Y+ is left
            dir_x = math.sin(angle_rad)  # Front component
            dir_y = math.cos(angle_rad)  # Left component

            # Calculate yaw angle from direction vector
            # DOA convention: 0 = left, π/2 = front, π = right
            # Robot yaw: positive = turn right, negative = turn left
            # Invert the sign: left(0) → +90° (turn right toward left sound)
            #                  right(π) → -90° (turn left toward right sound)
            yaw_rad = -(angle_rad - math.pi / 2)
            yaw_deg = math.degrees(yaw_rad)

            _LOGGER.debug("DOA direction: x=%.2f, y=%.2f, yaw=%.1f°",
                          dir_x, dir_y, yaw_deg)

            # Only turn if angle is significant (> 10°) to avoid noise
            DOA_THRESHOLD_DEG = 10.0
            if abs(yaw_deg) < DOA_THRESHOLD_DEG:
                _LOGGER.debug("DOA angle %.1f° below threshold (%.1f°), skipping turn",
                              yaw_deg, DOA_THRESHOLD_DEG)
                return

            # Apply 80% of DOA angle as conservative strategy
            # This accounts for potential DOA inaccuracy
            DOA_SCALE = 0.8
            target_yaw_deg = yaw_deg * DOA_SCALE

            _LOGGER.info("Turning toward sound source: DOA=%.1f°, target=%.1f°",
                         yaw_deg, target_yaw_deg)

            # Use MovementManager to turn (non-blocking)
            if self.state.motion and self.state.motion.movement_manager:
                self.state.motion.movement_manager.turn_to_angle(
                    target_yaw_deg,
                    duration=0.5  # Quick turn
                )
        except Exception as e:
            _LOGGER.error("Error in turn-to-sound: %s", e)

    def _reachy_on_listening(self) -> None:
        """Called when listening for speech (HA state: Listening)."""
        # Enable high-frequency face tracking during listening
        self._set_conversation_mode(True)

        # Resume face tracking (may have been paused during speaking)
        if self.camera_server is not None:
            try:
                self.camera_server.set_face_tracking_enabled(True)
            except Exception as e:
                _LOGGER.debug("Failed to resume face tracking: %s", e)

        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Listening animation")
            if self.state.motion:
                self.state.motion.on_listening()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_thinking(self) -> None:
        """Called when processing speech (HA state: Processing)."""
        # Resume face tracking (may have been paused during speaking)
        if self.camera_server is not None:
            try:
                self.camera_server.set_face_tracking_enabled(True)
            except Exception as e:
                _LOGGER.debug("Failed to resume face tracking: %s", e)

        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Thinking animation")
            if self.state.motion:
                self.state.motion.on_thinking()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_speaking(self) -> None:
        """Called when TTS is playing (HA state: Responding)."""
        # Pause face tracking during speaking - robot will use speaking animation instead
        if self.camera_server is not None:
            try:
                self.camera_server.set_face_tracking_enabled(False)
                _LOGGER.debug("Face tracking paused during speaking")
            except Exception as e:
                _LOGGER.debug("Failed to pause face tracking: %s", e)

        if not self.state.motion_enabled:
            _LOGGER.warning("Motion disabled, skipping speaking animation")
            return
        if not self.state.reachy_mini:
            _LOGGER.warning("No reachy_mini instance, skipping speaking animation")
            return
        if not self.state.motion:
            _LOGGER.warning("No motion controller, skipping speaking animation")
            return

        try:
            _LOGGER.debug("Reachy Mini: Starting speaking animation")
            self.state.motion.on_speaking_start()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_idle(self) -> None:
        """Called when returning to idle state (HA state: Idle)."""
        # Disable high-frequency face tracking, switch to adaptive mode
        self._set_conversation_mode(False)

        # Resume face tracking (may have been paused during speaking)
        if self.camera_server is not None:
            try:
                self.camera_server.set_face_tracking_enabled(True)
            except Exception as e:
                _LOGGER.debug("Failed to resume face tracking: %s", e)

        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Idle animation")
            if self.state.motion:
                self.state.motion.on_idle()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _set_conversation_mode(self, in_conversation: bool) -> None:
        """Set conversation mode for adaptive face tracking.

        When in conversation, face tracking runs at high frequency.
        When idle, face tracking uses adaptive rate to save CPU.
        """
        if self.camera_server is not None:
            try:
                self.camera_server.set_conversation_mode(in_conversation)
            except Exception as e:
                _LOGGER.debug("Failed to set conversation mode: %s", e)

    def _reachy_on_timer_finished(self) -> None:
        """Called when a timer finishes."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Timer finished animation")
            if self.state.motion:
                self.state.motion.on_timer_finished()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _play_emotion(self, emotion_name: str) -> None:
        """Play an emotion/expression from the emotions library.

        Uses the MovementManager's queue_emotion_move() method which samples
        poses via RecordedMoves.evaluate(t) in the control loop. This avoids
        "a move is currently running" warnings from the SDK daemon.

        Args:
            emotion_name: Name of the emotion (e.g., "happy1", "sad1", etc.)
        """
        try:
            # Use MovementManager to play emotion (non-blocking, integrated with control loop)
            if self.state.motion and self.state.motion.movement_manager:
                movement_manager = self.state.motion.movement_manager
                if movement_manager.queue_emotion_move(emotion_name):
                    _LOGGER.info(f"Queued emotion move: {emotion_name}")
                else:
                    _LOGGER.warning(f"Failed to queue emotion: {emotion_name}")
            else:
                _LOGGER.warning("Cannot play emotion: no movement manager available")

        except Exception as e:
            _LOGGER.error(f"Error playing emotion {emotion_name}: {e}")

    def _trigger_wake_word(self) -> None:
        """Trigger wake word detection (simulate hearing the wake word).

        This is called by GestureActionMapper when a "call" gesture is detected,
        allowing users to activate the voice assistant with a hand gesture.
        """
        try:
            # The wake word detected event triggers the voice pipeline
            _LOGGER.info("Gesture triggered wake word - starting voice assistant")
            # Set the wake word event to simulate detection
            if hasattr(self.state, 'last_wake_word'):
                self.state.last_wake_word = "gesture"
            # Trigger the run_voice_assistant logic
            self.start_voice_assistant()
        except Exception as e:
            _LOGGER.error(f"Error triggering wake word from gesture: {e}")

    def _stop_current_tts(self) -> None:
        """Stop current TTS playback.

        Called by GestureActionMapper when a "stop" gesture is detected,
        allowing users to interrupt the robot's speech.
        """
        try:
            _LOGGER.info("Gesture triggered TTS stop")
            if self.state.tts_player:
                self.state.tts_player.stop()
            if self.state.music_player:
                self.state.music_player.stop()
        except Exception as e:
            _LOGGER.error(f"Error stopping TTS from gesture: {e}")

    def _send_gesture_event_to_ha(self, event_name: str) -> None:
        """Send a gesture event to Home Assistant.

        This allows HA automations to react to gestures like "one", "two", etc.

        Args:
            event_name: Name of the gesture event (e.g., "gesture_one")
        """
        try:
            _LOGGER.info(f"Sending gesture event to HA: {event_name}")
            # Fire an event to Home Assistant via the satellite protocol
            # This uses the VoiceAssistantEventResponse mechanism
            # For now, we can use the timer event mechanism or a custom event
            # Home Assistant can subscribe to these events via ESPHome integration
        except Exception as e:
            _LOGGER.error(f"Error sending gesture event to HA: {e}")

    def _handle_ha_state_change(self, msg: HomeAssistantStateResponse) -> None:
        """Handle Home Assistant state change via ESPHome bidirectional communication.

        This method is called when Home Assistant sends state updates through
        the ESPHome protocol. It uses EventEmotionMapper to trigger robot
        emotions based on configured entity state changes.

        Args:
            msg: HomeAssistantStateResponse containing entity_id and state
        """
        try:
            entity_id = msg.entity_id
            new_state = msg.state

            # Track old state for proper event handling
            old_state = self._ha_entity_states.get(entity_id, "unknown")
            self._ha_entity_states[entity_id] = new_state

            _LOGGER.debug("HA state change: %s: %s -> %s", entity_id, old_state, new_state)

            # Let EventEmotionMapper handle the state change
            emotion = self._event_emotion_mapper.handle_state_change(
                entity_id, old_state, new_state
            )
            if emotion:
                _LOGGER.info("HA event triggered emotion: %s from %s", emotion, entity_id)

        except Exception as e:
            _LOGGER.error("Error handling HA state change: %s", e)

    def handle_detected_gesture(self, gesture_name: str, confidence: float) -> bool:
        """Handle a detected gesture by triggering mapped actions.

        This should be called when a gesture is detected to trigger local actions
        (emotions, TTS control, HA events) based on the gesture mappings.

        Args:
            gesture_name: Name of the detected gesture
            confidence: Detection confidence (0-1)

        Returns:
            True if an action was triggered, False otherwise
        """
        return self._gesture_action_mapper.handle_gesture(gesture_name, confidence)

    def suspend(self) -> None:
        """Suspend the satellite for sleep mode.

        Stops any current playback and releases resources.
        """
        _LOGGER.info("Suspending VoiceSatellite for sleep...")

        # Stop any current TTS/music
        if self.state.tts_player:
            self.state.tts_player.stop()
        if self.state.music_player:
            self.state.music_player.stop()

        # Clear active wake words to prevent false triggers
        self.state.active_wake_words.clear()

        # Reset conversation state
        self._tts_url = None
        self._tts_played = True
        self._continue_conversation = False
        self._is_streaming_audio = False

        _LOGGER.info("VoiceSatellite suspended")

    def resume(self) -> None:
        """Resume the satellite after sleep."""
        _LOGGER.info("Resuming VoiceSatellite from sleep...")

        # Wake words are preserved in state.active_wake_words, no need to restore

        _LOGGER.info("VoiceSatellite resumed")
