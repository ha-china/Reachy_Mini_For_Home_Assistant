"""Voice satellite protocol for Reachy Mini."""

import hashlib
import logging
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
        
        # Tap-to-talk continuous conversation mode
        self._tap_conversation_mode = False  # When True, auto-continue after TTS

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        # Initialize entity registry (tap_detector from state if available)
        tap_detector = getattr(state, 'tap_detector', None)
        self._entity_registry = EntityRegistry(
            server=self,
            reachy_controller=self.reachy_controller,
            camera_server=camera_server,
            play_emotion_callback=self._play_emotion,
            tap_detector=tap_detector,
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
            self._reachy_on_speaking()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            self._tts_url = data.get("url")
            self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            self._is_streaming_audio = False
            if not self._tts_played:
                self._tts_finished()
            self._tts_played = False
            # Reachy Mini: Return to idle
            self._reachy_on_idle()

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
                    # Already active
                    active_wake_words.add(wake_word_id)
                    continue

                model_info = self.state.available_wake_words.get(wake_word_id)
                if not model_info:
                    # Check external wake words (may require download)
                    external_wake_word = self._external_wake_words.get(wake_word_id)
                    if not external_wake_word:
                        continue

                    model_info = self._download_external_wake_word(external_wake_word)
                    if not model_info:
                        continue

                    self.state.available_wake_words[wake_word_id] = model_info

                _LOGGER.debug("Loading wake word: %s", model_info.wake_word_path)
                self.state.wake_words[wake_word_id] = model_info.load()
                _LOGGER.info("Wake word set: %s", wake_word_id)
                active_wake_words.add(wake_word_id)
                break

            self.state.active_wake_words = active_wake_words
            _LOGGER.debug("Active wake words: %s", active_wake_words)

            self.state.preferences.active_wake_words = list(active_wake_words)
            self.state.save_preferences()
            self.state.wake_words_changed = True

    def handle_audio(self, audio_chunk: bytes) -> None:
        if not self._is_streaming_audio:
            return
        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def wakeup(self, wake_word: Union[MicroWakeWord, OpenWakeWord]) -> None:
        if self._timer_finished:
            # Stop timer instead
            self._timer_finished = False
            self.state.tts_player.stop()
            _LOGGER.debug("Stopping timer finished sound")
            return

        wake_word_phrase = wake_word.wake_word
        _LOGGER.debug("Detected wake word: %s", wake_word_phrase)

        self.send_messages(
            [VoiceAssistantRequest(start=True, wake_word_phrase=wake_word_phrase)]
        )
        self.duck()
        self._is_streaming_audio = True
        self.state.tts_player.play(self.state.wakeup_sound)

    def wakeup_from_tap(self) -> None:
        """Trigger wake-up from tap detection (no wake word).
        
        First tap: Enter continuous conversation mode
        Second tap (while in conversation): Exit continuous conversation mode
        """
        # If already in tap conversation mode, exit it
        if self._tap_conversation_mode:
            _LOGGER.info("Tap detected - exiting continuous conversation mode")
            self._tap_conversation_mode = False
            self._is_streaming_audio = False
            self._continue_conversation = False  # Also clear HA continue flag
            # Send stop request to Home Assistant
            self.send_messages([VoiceAssistantRequest(start=False)])
            # Stop any ongoing TTS
            self.state.tts_player.stop()
            self.unduck()
            self._reachy_on_idle()
            return
        
        if self._timer_finished:
            # Stop timer instead
            self._timer_finished = False
            self.state.tts_player.stop()
            _LOGGER.debug("Stopping timer finished sound")
            return

        _LOGGER.info("Tap detected - entering continuous conversation mode")
        self._tap_conversation_mode = True

        self.send_messages(
            [VoiceAssistantRequest(start=True, wake_word_phrase="tap")]
        )
        self.duck()
        self._is_streaming_audio = True
        self.state.tts_player.play(self.state.wakeup_sound)

    def is_tap_conversation_active(self) -> bool:
        """Check if tap-triggered continuous conversation is active."""
        return self._tap_conversation_mode

    def stop(self) -> None:
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
        self.state.active_wake_words.discard(self.state.stop_word.id)
        self.send_messages([VoiceAssistantAnnounceFinished()])

        # Check if should continue conversation
        # 1. HA requested continue (intent not matched)
        # 2. Tap conversation mode is active
        should_continue = self._continue_conversation or self._tap_conversation_mode

        if should_continue:
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True
            
            if self._tap_conversation_mode:
                _LOGGER.debug("Continuing tap conversation mode")
                # Provide feedback for continuous conversation mode
                self._tap_continue_feedback()
            else:
                _LOGGER.debug("Continuing conversation (HA requested)")
        else:
            self.unduck()
            _LOGGER.debug("TTS response finished")
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

    def _reachy_on_listening(self) -> None:
        """Called when listening for speech (HA state: Listening)."""
        # Enable high-frequency face tracking during conversation
        self._set_conversation_mode(True)
        
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
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Speaking animation")
            if self.state.motion:
                self.state.motion.on_speaking_start()
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_idle(self) -> None:
        """Called when returning to idle state (HA state: Idle)."""
        # Disable high-frequency face tracking, switch to adaptive mode
        self._set_conversation_mode(False)
        
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

    def _tap_continue_feedback(self) -> None:
        """Provide feedback when continuing conversation in tap mode.
        
        Triggers a nod to indicate ready for next input.
        Sound is NOT played here to avoid blocking audio streaming.
        """
        try:
            # NOTE: Do NOT play sound here - it blocks audio streaming
            # The wakeup sound is already played by the main wakeup flow
            
            # Trigger a small nod to indicate ready for input
            if self.state.motion_enabled and self.state.motion:
                self.state.motion.on_continue_listening()
                _LOGGER.debug("Tap continue feedback: continue listening pose")
        except Exception as e:
            _LOGGER.error("Tap continue feedback error: %s", e)

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
            url = f"http://{wlan_ip}:8000/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/{emotion_name}"

            response = requests.post(url, timeout=5)
            if response.status_code == 200:
                _LOGGER.info(f"Playing emotion: {emotion_name}")
            else:
                _LOGGER.warning(f"Failed to play emotion {emotion_name}: HTTP {response.status_code}")

        except Exception as e:
            _LOGGER.error(f"Error playing emotion {emotion_name}: {e}")
