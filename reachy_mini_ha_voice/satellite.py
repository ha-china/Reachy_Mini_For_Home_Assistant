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

_LOGGER = logging.getLogger(__name__)


class VoiceSatelliteProtocol(APIServer):
    """Voice satellite protocol handler for ESPHome."""

    def __init__(self, state: ServerState, camera_server: Optional["MJPEGCameraServer"] = None) -> None:
        super().__init__(state.name)
        self.state = state
        self.state.satellite = self
        self.camera_server = camera_server

        # Initialize streaming state early (before entity setup)
        # This is needed because audio processing thread checks this attribute
        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._external_wake_words: Dict[str, VoiceAssistantExternalWakeWord] = {}

        # Tap-to-talk continuous conversation mode (REMOVED - too many false triggers)
        # Continuous conversation is now controlled via Home Assistant switch
        # self._tap_conversation_mode = False

        # Conversation tracking for continuous conversation
        self._conversation_id: Optional[str] = None
        self._conversation_timeout = 300.0  # 5 minutes, same as ESPHome default
        self._last_conversation_time = 0.0

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        # Connect MovementManager to ReachyController for pose control from HA
        if state.motion is not None and state.motion.movement_manager is not None:
            self.reachy_controller.set_movement_manager(state.motion.movement_manager)

        # Initialize entity registry
        self._entity_registry = EntityRegistry(
            server=self,
            reachy_controller=self.reachy_controller,
            camera_server=camera_server,
            play_emotion_callback=self._play_emotion,
        )

        # Only setup entities once (check if already initialized)
        # This prevents duplicate entity registration on reconnection
        if not getattr(self.state, '_entities_initialized', False):
            if self.state.media_player_entity is None:
                self.state.media_player_entity = MediaPlayerEntity(
                    server=self,
                    key=get_entity_key("reachy_mini_media_player"),
                    name="Media Player",
                    object_id="reachy_mini_media_player",
                    music_player=state.music_player,
                    announce_player=state.tts_player,
                )
                self.state.entities.append(self.state.media_player_entity)

            # Setup all entities using the registry
            self._entity_registry.setup_all_entities(self.state.entities)

            # Mark entities as initialized
            self.state._entities_initialized = True
            _LOGGER.info("Entities initialized: %d total", len(self.state.entities))
        else:
            _LOGGER.debug("Entities already initialized, skipping setup")
            # Update server reference in existing entities
            for entity in self.state.entities:
                entity.server = self

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
            # Reachy Mini: Start speaking animation
            _LOGGER.info("TTS_START event received, triggering speaking animation")
            self._reachy_on_speaking()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            self._tts_url = data.get("url")
            self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            # Pipeline run ended
            self._tts_played = False
            self._is_streaming_audio = False

            # Check if should continue conversation
            self._handle_run_end()

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

        elif isinstance(msg, DeviceInfoRequest):
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
        """Handle wake word detection - start voice pipeline.

        Following reference project pattern: no pipeline state check here.
        Refractory period in audio processing prevents duplicate triggers.
        """
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

    def wakeup_from_tap(self) -> None:
        """Trigger wake-up from tap detection.

        NOTE: This method is DISABLED. Tap-to-wake caused too many false triggers.
        Continuous conversation is now controlled via Home Assistant switch.
        """
        _LOGGER.warning("wakeup_from_tap() called but tap wake is disabled")
        return

    def is_tap_conversation_active(self) -> bool:
        """Check if tap-triggered continuous conversation is active.

        NOTE: Tap wake is DISABLED. This always returns False.
        """
        return False

    def stop(self) -> None:
        """Stop current TTS playback (e.g., user said stop word)."""
        self.state.active_wake_words.discard(self.state.stop_word.id)
        self.state.tts_player.stop()

        if self._timer_finished:
            self._timer_finished = False
            _LOGGER.debug("Stopping timer finished sound")
        else:
            _LOGGER.debug("TTS response stopped manually")

        # Send announce finished to HA
        self.send_messages([VoiceAssistantAnnounceFinished()])
        # Note: RUN_END event will handle the rest

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
            _LOGGER.info("Continuing conversation (our_switch=%s, ha_request=%s)",
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

    def _handle_run_end(self) -> None:
        """Handle pipeline RUN_END event.

        Following reference project pattern: call _tts_finished if TTS wasn't played.
        """
        if not self._tts_played:
            self._tts_finished()

        self._tts_played = False

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
            _LOGGER.info("DOA raw: angle=%.3f rad (%.1f°), speech=%s",
                         angle_rad, math.degrees(angle_rad), speech_detected)

            # Convert DOA to direction vector in head frame
            # SDK convention: p_head = [sin(doa), cos(doa), 0]
            # where X+ is front, Y+ is left
            dir_x = math.sin(angle_rad)  # Front component
            dir_y = math.cos(angle_rad)  # Left component

            # Calculate yaw angle from direction vector
            # yaw = atan2(y, x), but we want: positive yaw = turn right
            # In robot frame: Y+ is left, so yaw = -atan2(dir_y, dir_x)
            # But since dir_x = sin(doa), dir_y = cos(doa):
            # yaw = -atan2(cos(doa), sin(doa)) = -(π/2 - doa) = doa - π/2
            #
            # CORRECTION: The above was inverted. Testing shows:
            # - Sound on left → robot turns right (wrong)
            # - Sound on right → robot turns left (wrong)
            # So we need to negate the yaw: yaw = π/2 - doa
            yaw_rad = math.pi / 2 - angle_rad
            yaw_deg = math.degrees(yaw_rad)

            _LOGGER.info("DOA direction: x=%.2f, y=%.2f, yaw=%.1f°",
                         dir_x, dir_y, yaw_deg)

            # Only turn if angle is significant (> 10°) to avoid noise
            DOA_THRESHOLD_DEG = 10.0
            if abs(yaw_deg) < DOA_THRESHOLD_DEG:
                _LOGGER.info("DOA angle %.1f° below threshold (%.1f°), skipping turn",
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
            _LOGGER.info("Reachy Mini: Starting speaking animation")
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

        Args:
            emotion_name: Name of the emotion (e.g., "happy1", "sad1", etc.)
        """
        try:
            import requests

            # Get WLAN IP from daemon status
            wlan_ip = "localhost"
            if self.state.reachy_mini is not None:
                try:
                    status = self.state.reachy_mini.client.get_status(wait=False)
                    wlan_ip = status.get('wlan_ip', 'localhost')
                except Exception:
                    wlan_ip = "localhost"

            # Call the emotion playback API
            # Dataset: pollen-robotics/reachy-mini-emotions-library
            base_url = f"http://{wlan_ip}:8000/api/move/play/recorded-move-dataset"
            dataset = "pollen-robotics/reachy-mini-emotions-library"
            url = f"{base_url}/{dataset}/{emotion_name}"

            response = requests.post(url, timeout=5)
            if response.status_code == 200:
                result = response.json()
                move_uuid = result.get('uuid')
                _LOGGER.info(f"Playing emotion: {emotion_name} (uuid={move_uuid})")
            else:
                _LOGGER.warning(f"Failed to play emotion {emotion_name}: HTTP {response.status_code}")

        except Exception as e:
            _LOGGER.error(f"Error playing emotion {emotion_name}: {e}")
