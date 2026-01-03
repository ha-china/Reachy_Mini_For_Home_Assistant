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
from .entity import BinarySensorEntity, CameraEntity, MediaPlayerEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SensorEntity, SwitchEntity, SelectEntity, ButtonEntity
from .models import AvailableWakeWord, ServerState, WakeWordType
from .util import call_all
from .reachy_controller import ReachyController

_LOGGER = logging.getLogger(__name__)


class VoiceSatelliteProtocol(APIServer):
    """Voice satellite protocol handler for ESPHome."""

    # Fixed entity key mapping - ensures consistent keys across restarts
    # Keys are based on object_id hash to ensure uniqueness and consistency
    ENTITY_KEYS = {
        # Media player (key 0 reserved)
        "reachy_mini_media_player": 0,
        # Phase 1: Basic status and volume
        "daemon_state": 100,
        "backend_ready": 101,
        "error_message": 102,
        "speaker_volume": 103,
        # Phase 2: Motor control
        "motors_enabled": 200,
        "motor_mode": 201,
        "wake_up": 202,
        "go_to_sleep": 203,
        # Phase 3: Pose control
        "head_x": 300,
        "head_y": 301,
        "head_z": 302,
        "head_roll": 303,
        "head_pitch": 304,
        "head_yaw": 305,
        "body_yaw": 306,
        "antenna_left": 307,
        "antenna_right": 308,
        # Phase 4: Look at control
        "look_at_x": 400,
        "look_at_y": 401,
        "look_at_z": 402,
        # Phase 5: Audio sensors
        "doa_angle": 500,
        "speech_detected": 501,
        # Phase 6: Diagnostic information
        "control_loop_frequency": 600,
        "sdk_version": 601,
        "robot_name": 602,
        "wireless_version": 603,
        "simulation_mode": 604,
        "wlan_ip": 605,
        # Phase 7: IMU sensors
        "imu_accel_x": 700,
        "imu_accel_y": 701,
        "imu_accel_z": 702,
        "imu_gyro_x": 703,
        "imu_gyro_y": 704,
        "imu_gyro_z": 705,
        "imu_temperature": 706,
        # Phase 8: Emotions
        "emotion_happy": 800,
        "emotion_sad": 801,
        "emotion_angry": 802,
        "emotion_fear": 803,
        "emotion_surprise": 804,
        "emotion_disgust": 805,
        # Phase 9: Audio controls
        "microphone_volume": 900,
        # Phase 10: Camera
        "camera": 1000,
        # Phase 11: LED control
        "led_brightness": 1100,
        "led_effect": 1101,
        "led_color_r": 1102,
        "led_color_g": 1103,
        "led_color_b": 1104,
        # Phase 12: Audio processing
        "agc_enabled": 1200,
        "agc_max_gain": 1201,
        "noise_suppression": 1202,
        "echo_cancellation_converged": 1203,
    }

    def _get_entity_key(self, object_id: str) -> int:
        """Get a consistent entity key for the given object_id."""
        if object_id in self.ENTITY_KEYS:
            return self.ENTITY_KEYS[object_id]
        # Fallback: generate key from hash (should not happen if all entities are registered)
        _LOGGER.warning(f"Entity key not found for {object_id}, generating from hash")
        return abs(hash(object_id)) % 10000 + 2000

    def __init__(self, state: ServerState, camera_server: Optional["MJPEGCameraServer"] = None) -> None:
        super().__init__(state.name)
        self.state = state
        self.state.satellite = self
        self.camera_server = camera_server

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        # Initialize entity references (will be set in setup phases)
        self._doa_angle_entity: Optional[SensorEntity] = None
        self._speech_detected_entity: Optional[BinarySensorEntity] = None

        if self.state.media_player_entity is None:
            self.state.media_player_entity = MediaPlayerEntity(
                server=self,
                key=self._get_entity_key("reachy_mini_media_player"),
                name="Media Player",
                object_id="reachy_mini_media_player",
                music_player=state.music_player,
                announce_player=state.tts_player,
            )
            self.state.entities.append(self.state.media_player_entity)

        # Setup all entity phases
        self._setup_phase1_entities()
        self._setup_phase2_entities()
        self._setup_phase3_entities()
        self._setup_phase4_entities()
        self._setup_phase5_entities()
        self._setup_phase6_entities()
        self._setup_phase7_entities()
        self._setup_phase8_entities()
        self._setup_phase9_entities()
        self._setup_phase10_entities()  # Camera status
        self._setup_phase11_entities()  # LED control
        self._setup_phase12_entities()  # Audio processing

        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._external_wake_words: Dict[str, VoiceAssistantExternalWakeWord] = {}

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

        # Update DOA entity in Home Assistant
        self._update_doa_entities()

        # Reachy Mini: Wake up animation
        self._reachy_on_wakeup()

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

    def unduck(self) -> None:
        _LOGGER.debug("Unducking music")
        self.state.music_player.unduck()

    def _tts_finished(self) -> None:
        self.state.active_wake_words.discard(self.state.stop_word.id)
        self.send_messages([VoiceAssistantAnnounceFinished()])

        if self._continue_conversation:
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True
            _LOGGER.debug("Continuing conversation")
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

    def _update_doa_entities(self) -> None:
        """Update DOA and speech detection entities in Home Assistant."""
        try:
            if self._doa_angle_entity is not None:
                self._doa_angle_entity.update_state()
                _LOGGER.debug("DOA angle entity updated")
            if self._speech_detected_entity is not None:
                self._speech_detected_entity.update_state()
                _LOGGER.debug("Speech detected entity updated")
        except Exception as e:
            _LOGGER.error("Error updating DOA entities: %s", e)

    def _reachy_on_wakeup(self) -> None:
        """Called when wake word is detected."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            # Nod to acknowledge
            _LOGGER.debug("Reachy Mini: Wake up animation")
            # Will be implemented with actual Reachy Mini SDK
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_listening(self) -> None:
        """Called when listening for speech."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Listening animation")
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_thinking(self) -> None:
        """Called when processing speech."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Thinking animation")
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_speaking(self) -> None:
        """Called when TTS is playing."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Speaking animation")
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_idle(self) -> None:
        """Called when returning to idle state."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Idle animation")
        except Exception as e:
            _LOGGER.error("Reachy Mini motion error: %s", e)

    def _reachy_on_timer_finished(self) -> None:
        """Called when a timer finishes."""
        if not self.state.motion_enabled or not self.state.reachy_mini:
            return
        try:
            _LOGGER.debug("Reachy Mini: Timer finished animation")
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

    # -------------------------------------------------------------------------
    # Entity Setup Methods
    # -------------------------------------------------------------------------

    def _setup_phase1_entities(self) -> None:
        """Setup Phase 1 entities: Basic status and volume control."""

        # Daemon state sensor
        daemon_state_sensor = TextSensorEntity(
            server=self,
            key=self._get_entity_key("daemon_state"),
            name="Daemon State",
            object_id="daemon_state",
            icon="mdi:robot",
            value_getter=self.reachy_controller.get_daemon_state,
        )
        self.state.entities.append(daemon_state_sensor)

        # Backend ready sensor
        backend_ready_sensor = BinarySensorEntity(
            server=self,
            key=self._get_entity_key("backend_ready"),
            name="Backend Ready",
            object_id="backend_ready",
            icon="mdi:check-circle",
            device_class="connectivity",
            value_getter=self.reachy_controller.get_backend_ready,
        )
        self.state.entities.append(backend_ready_sensor)

        # Error message sensor
        error_message_sensor = TextSensorEntity(
            server=self,
            key=self._get_entity_key("error_message"),
            name="Error Message",
            object_id="error_message",
            icon="mdi:alert-circle",
            value_getter=self.reachy_controller.get_error_message,
        )
        self.state.entities.append(error_message_sensor)

        # Speaker volume control
        speaker_volume = NumberEntity(
            server=self,
            key=self._get_entity_key("speaker_volume"),
            name="Speaker Volume",
            object_id="speaker_volume",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            icon="mdi:volume-high",
            unit_of_measurement="%",
            mode=2,  # Slider mode
            value_getter=self.reachy_controller.get_speaker_volume,
            value_setter=self.reachy_controller.set_speaker_volume,
        )
        self.state.entities.append(speaker_volume)

        _LOGGER.info("Phase 1 entities registered: daemon_state, backend_ready, error_message, speaker_volume")

    def _setup_phase2_entities(self) -> None:
        """Setup Phase 2 entities: Motor control."""

        # Motors enabled switch
        motors_enabled = SwitchEntity(
            server=self,
            key=self._get_entity_key("motors_enabled"),
            name="Motors Enabled",
            object_id="motors_enabled",
            icon="mdi:engine",
            device_class="switch",
            value_getter=self.reachy_controller.get_motors_enabled,
            value_setter=self.reachy_controller.set_motors_enabled,
        )
        self.state.entities.append(motors_enabled)

        # Motor mode select
        motor_mode = SelectEntity(
            server=self,
            key=self._get_entity_key("motor_mode"),
            name="Motor Mode",
            object_id="motor_mode",
            options=["enabled", "disabled", "gravity_compensation"],
            icon="mdi:cog",
            value_getter=self.reachy_controller.get_motor_mode,
            value_setter=self.reachy_controller.set_motor_mode,
        )
        self.state.entities.append(motor_mode)

        # Wake up button
        wake_up_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("wake_up"),
            name="Wake Up",
            object_id="wake_up",
            icon="mdi:alarm",
            device_class="restart",
            on_press=self.reachy_controller.wake_up,
        )
        self.state.entities.append(wake_up_button)

        # Go to sleep button
        sleep_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("go_to_sleep"),
            name="Go to Sleep",
            object_id="go_to_sleep",
            icon="mdi:sleep",
            device_class="restart",
            on_press=self.reachy_controller.go_to_sleep,
        )
        self.state.entities.append(sleep_button)

        _LOGGER.info("Phase 2 entities registered: motors_enabled, motor_mode, wake_up, go_to_sleep")

    def _setup_phase3_entities(self) -> None:
        """Setup Phase 3 entities: Pose control."""

        # Head position controls (X, Y, Z in mm)
        head_x = NumberEntity(
            server=self,
            key=self._get_entity_key("head_x"),
            name="Head X Position",
            object_id="head_x",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-x-arrow",
            unit_of_measurement="mm",
            mode=2,  # Slider
            value_getter=self.reachy_controller.get_head_x,
            value_setter=self.reachy_controller.set_head_x,
        )
        self.state.entities.append(head_x)

        head_y = NumberEntity(
            server=self,
            key=self._get_entity_key("head_y"),
            name="Head Y Position",
            object_id="head_y",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-y-arrow",
            unit_of_measurement="mm",
            mode=2,
            value_getter=self.reachy_controller.get_head_y,
            value_setter=self.reachy_controller.set_head_y,
        )
        self.state.entities.append(head_y)

        head_z = NumberEntity(
            server=self,
            key=self._get_entity_key("head_z"),
            name="Head Z Position",
            object_id="head_z",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-z-arrow",
            unit_of_measurement="mm",
            mode=2,
            value_getter=self.reachy_controller.get_head_z,
            value_setter=self.reachy_controller.set_head_z,
        )
        self.state.entities.append(head_z)

        # Head orientation controls (Roll, Pitch, Yaw in degrees)
        head_roll = NumberEntity(
            server=self,
            key=self._get_entity_key("head_roll"),
            name="Head Roll",
            object_id="head_roll",
            min_value=-40.0,
            max_value=40.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_head_roll,
            value_setter=self.reachy_controller.set_head_roll,
        )
        self.state.entities.append(head_roll)

        head_pitch = NumberEntity(
            server=self,
            key=self._get_entity_key("head_pitch"),
            name="Head Pitch",
            object_id="head_pitch",
            min_value=-40.0,
            max_value=40.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_head_pitch,
            value_setter=self.reachy_controller.set_head_pitch,
        )
        self.state.entities.append(head_pitch)

        head_yaw = NumberEntity(
            server=self,
            key=self._get_entity_key("head_yaw"),
            name="Head Yaw",
            object_id="head_yaw",
            min_value=-180.0,
            max_value=180.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_head_yaw,
            value_setter=self.reachy_controller.set_head_yaw,
        )
        self.state.entities.append(head_yaw)

        # Body yaw control
        body_yaw = NumberEntity(
            server=self,
            key=self._get_entity_key("body_yaw"),
            name="Body Yaw",
            object_id="body_yaw",
            min_value=-160.0,
            max_value=160.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_body_yaw,
            value_setter=self.reachy_controller.set_body_yaw,
        )
        self.state.entities.append(body_yaw)

        # Antenna controls
        antenna_left = NumberEntity(
            server=self,
            key=self._get_entity_key("antenna_left"),
            name="Left Antenna",
            object_id="antenna_left",
            min_value=-90.0,
            max_value=90.0,
            step=1.0,
            icon="mdi:antenna",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_antenna_left,
            value_setter=self.reachy_controller.set_antenna_left,
        )
        self.state.entities.append(antenna_left)

        antenna_right = NumberEntity(
            server=self,
            key=self._get_entity_key("antenna_right"),
            name="Right Antenna",
            object_id="antenna_right",
            min_value=-90.0,
            max_value=90.0,
            step=1.0,
            icon="mdi:antenna",
            unit_of_measurement="°",
            mode=2,
            value_getter=self.reachy_controller.get_antenna_right,
            value_setter=self.reachy_controller.set_antenna_right,
        )
        self.state.entities.append(antenna_right)

        _LOGGER.info("Phase 3 entities registered: head position/orientation, body_yaw, antennas")

    def _setup_phase4_entities(self) -> None:
        """Setup Phase 4 entities: Look at control."""

        # Look at X coordinate
        look_at_x = NumberEntity(
            server=self,
            key=self._get_entity_key("look_at_x"),
            name="Look At X",
            object_id="look_at_x",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,  # Box mode for precise input
            value_getter=self.reachy_controller.get_look_at_x,
            value_setter=self.reachy_controller.set_look_at_x,
        )
        self.state.entities.append(look_at_x)

        # Look at Y coordinate
        look_at_y = NumberEntity(
            server=self,
            key=self._get_entity_key("look_at_y"),
            name="Look At Y",
            object_id="look_at_y",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,
            value_getter=self.reachy_controller.get_look_at_y,
            value_setter=self.reachy_controller.set_look_at_y,
        )
        self.state.entities.append(look_at_y)

        # Look at Z coordinate
        look_at_z = NumberEntity(
            server=self,
            key=self._get_entity_key("look_at_z"),
            name="Look At Z",
            object_id="look_at_z",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,
            value_getter=self.reachy_controller.get_look_at_z,
            value_setter=self.reachy_controller.set_look_at_z,
        )
        self.state.entities.append(look_at_z)

        _LOGGER.info("Phase 4 entities registered: look_at_x/y/z")

    def _setup_phase5_entities(self) -> None:
        """Setup Phase 5 entities: Audio sensors."""

        # DOA angle sensor
        self._doa_angle_entity = SensorEntity(
            server=self,
            key=self._get_entity_key("doa_angle"),
            name="DOA Angle",
            object_id="doa_angle",
            icon="mdi:compass",
            unit_of_measurement="°",
            accuracy_decimals=1,
            state_class="measurement",
            value_getter=self.reachy_controller.get_doa_angle,
        )
        self.state.entities.append(self._doa_angle_entity)

        # Speech detected sensor
        self._speech_detected_entity = BinarySensorEntity(
            server=self,
            key=self._get_entity_key("speech_detected"),
            name="Speech Detected",
            object_id="speech_detected",
            icon="mdi:microphone",
            device_class="sound",
            value_getter=self.reachy_controller.get_speech_detected,
        )
        self.state.entities.append(self._speech_detected_entity)

        _LOGGER.info("Phase 5 entities registered: doa_angle, speech_detected")

    def _setup_phase6_entities(self) -> None:
        """Setup Phase 6 entities: Diagnostic information."""

        # Control loop frequency
        control_loop_freq = SensorEntity(
            server=self,
            key=self._get_entity_key("control_loop_frequency"),
            name="Control Loop Frequency",
            object_id="control_loop_frequency",
            icon="mdi:speedometer",
            unit_of_measurement="Hz",
            accuracy_decimals=1,
            state_class="measurement",
            value_getter=self.reachy_controller.get_control_loop_frequency,
        )
        self.state.entities.append(control_loop_freq)

        # SDK version
        sdk_version = TextSensorEntity(
            server=self,
            key=self._get_entity_key("sdk_version"),
            name="SDK Version",
            object_id="sdk_version",
            icon="mdi:information",
            value_getter=self.reachy_controller.get_sdk_version,
        )
        self.state.entities.append(sdk_version)

        # Robot name
        robot_name = TextSensorEntity(
            server=self,
            key=self._get_entity_key("robot_name"),
            name="Robot Name",
            object_id="robot_name",
            icon="mdi:robot",
            value_getter=self.reachy_controller.get_robot_name,
        )
        self.state.entities.append(robot_name)

        # Wireless version
        wireless_version = BinarySensorEntity(
            server=self,
            key=self._get_entity_key("wireless_version"),
            name="Wireless Version",
            object_id="wireless_version",
            icon="mdi:wifi",
            device_class="connectivity",
            value_getter=self.reachy_controller.get_wireless_version,
        )
        self.state.entities.append(wireless_version)

        # Simulation mode
        simulation_mode = BinarySensorEntity(
            server=self,
            key=self._get_entity_key("simulation_mode"),
            name="Simulation Mode",
            object_id="simulation_mode",
            icon="mdi:virtual-reality",
            value_getter=self.reachy_controller.get_simulation_mode,
        )
        self.state.entities.append(simulation_mode)

        # WLAN IP
        wlan_ip = TextSensorEntity(
            server=self,
            key=self._get_entity_key("wlan_ip"),
            name="WLAN IP",
            object_id="wlan_ip",
            icon="mdi:ip-network",
            value_getter=self.reachy_controller.get_wlan_ip,
        )
        self.state.entities.append(wlan_ip)

        _LOGGER.info("Phase 6 entities registered: control_loop_frequency, sdk_version, robot_name, wireless_version, simulation_mode, wlan_ip")

    def _setup_phase7_entities(self) -> None:
        """Setup Phase 7 entities: IMU sensors (wireless only)."""

        # IMU Accelerometer
        imu_accel_x = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_accel_x"),
            name="IMU Accel X",
            object_id="imu_accel_x",
            icon="mdi:axis-x-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_accel_x,
        )
        self.state.entities.append(imu_accel_x)

        imu_accel_y = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_accel_y"),
            name="IMU Accel Y",
            object_id="imu_accel_y",
            icon="mdi:axis-y-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_accel_y,
        )
        self.state.entities.append(imu_accel_y)

        imu_accel_z = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_accel_z"),
            name="IMU Accel Z",
            object_id="imu_accel_z",
            icon="mdi:axis-z-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_accel_z,
        )
        self.state.entities.append(imu_accel_z)

        # IMU Gyroscope
        imu_gyro_x = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_gyro_x"),
            name="IMU Gyro X",
            object_id="imu_gyro_x",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_gyro_x,
        )
        self.state.entities.append(imu_gyro_x)

        imu_gyro_y = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_gyro_y"),
            name="IMU Gyro Y",
            object_id="imu_gyro_y",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_gyro_y,
        )
        self.state.entities.append(imu_gyro_y)

        imu_gyro_z = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_gyro_z"),
            name="IMU Gyro Z",
            object_id="imu_gyro_z",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_gyro_z,
        )
        self.state.entities.append(imu_gyro_z)

        # IMU Temperature
        imu_temperature = SensorEntity(
            server=self,
            key=self._get_entity_key("imu_temperature"),
            name="IMU Temperature",
            object_id="imu_temperature",
            icon="mdi:thermometer",
            unit_of_measurement="°C",
            accuracy_decimals=1,
            device_class="temperature",
            state_class="measurement",
            value_getter=self.reachy_controller.get_imu_temperature,
        )
        self.state.entities.append(imu_temperature)

        _LOGGER.info("Phase 7 entities registered: IMU accelerometer, gyroscope, temperature")

    def _setup_phase8_entities(self) -> None:
        """Setup Phase 8 entities: Emotion and expression buttons."""

        # Happy emotion
        happy_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_happy"),
            name="Happy",
            object_id="emotion_happy",
            icon="mdi:emoticon-happy",
            device_class="restart",
            on_press=lambda: self._play_emotion("happy1"),
        )
        self.state.entities.append(happy_button)

        # Sad emotion
        sad_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_sad"),
            name="Sad",
            object_id="emotion_sad",
            icon="mdi:emoticon-sad",
            device_class="restart",
            on_press=lambda: self._play_emotion("sad1"),
        )
        self.state.entities.append(sad_button)

        # Angry emotion
        angry_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_angry"),
            name="Angry",
            object_id="emotion_angry",
            icon="mdi:emoticon-angry",
            device_class="restart",
            on_press=lambda: self._play_emotion("angry1"),
        )
        self.state.entities.append(angry_button)

        # Fear emotion
        fear_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_fear"),
            name="Fear",
            object_id="emotion_fear",
            icon="mdi:emoticon-frown",
            device_class="restart",
            on_press=lambda: self._play_emotion("fear1"),
        )
        self.state.entities.append(fear_button)

        # Surprise emotion
        surprise_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_surprise"),
            name="Surprise",
            object_id="emotion_surprise",
            icon="mdi:emoticon-surprised",
            device_class="restart",
            on_press=lambda: self._play_emotion("surprise1"),
        )
        self.state.entities.append(surprise_button)

        # Disgust emotion
        disgust_button = ButtonEntity(
            server=self,
            key=self._get_entity_key("emotion_disgust"),
            name="Disgust",
            object_id="emotion_disgust",
            icon="mdi:emoticon-poop",
            device_class="restart",
            on_press=lambda: self._play_emotion("disgust1"),
        )
        self.state.entities.append(disgust_button)

        _LOGGER.info("Phase 8 entities registered: emotions (happy, sad, angry, fear, surprise, disgust)")

    def _setup_phase9_entities(self) -> None:
        """Setup Phase 9 entities: Audio controls."""

        # Microphone volume control
        microphone_volume = NumberEntity(
            server=self,
            key=self._get_entity_key("microphone_volume"),
            name="Microphone Volume",
            object_id="microphone_volume",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            icon="mdi:microphone",
            unit_of_measurement="%",
            mode=2,  # Slider mode
            value_getter=self.reachy_controller.get_microphone_volume,
            value_setter=self.reachy_controller.set_microphone_volume,
        )
        self.state.entities.append(microphone_volume)

        _LOGGER.info("Phase 9 entities registered: microphone_volume")

    def _setup_phase10_entities(self) -> None:
        """Setup Phase 10 entities: Camera."""

        # Camera entity - provides actual camera image in Home Assistant
        def get_camera_image() -> bytes:
            """Get camera snapshot from camera server."""
            if self.camera_server:
                image = self.camera_server.get_snapshot()
                if image:
                    return image
            return b""

        camera = CameraEntity(
            server=self,
            key=self._get_entity_key("camera"),
            name="Camera",
            object_id="camera",
            icon="mdi:camera",
            image_getter=get_camera_image,
        )
        self.state.entities.append(camera)

        _LOGGER.info("Phase 10 entities registered: camera")

    def _setup_phase11_entities(self) -> None:
        """Setup Phase 11 entities: LED control (via local SDK)."""

        # LED Brightness
        led_brightness = NumberEntity(
            server=self,
            key=self._get_entity_key("led_brightness"),
            name="LED Brightness",
            object_id="led_brightness",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            icon="mdi:brightness-6",
            unit_of_measurement="%",
            mode=2,  # Slider mode
            value_getter=self.reachy_controller.get_led_brightness,
            value_setter=self.reachy_controller.set_led_brightness,
        )
        self.state.entities.append(led_brightness)

        # LED Effect
        led_effect = SelectEntity(
            server=self,
            key=self._get_entity_key("led_effect"),
            name="LED Effect",
            object_id="led_effect",
            options=["off", "solid", "breathing", "rainbow", "doa"],
            icon="mdi:led-on",
            value_getter=self.reachy_controller.get_led_effect,
            value_setter=self.reachy_controller.set_led_effect,
        )
        self.state.entities.append(led_effect)

        # LED Color R
        led_color_r = NumberEntity(
            server=self,
            key=self._get_entity_key("led_color_r"),
            name="LED Color Red",
            object_id="led_color_r",
            min_value=0.0,
            max_value=255.0,
            step=1.0,
            icon="mdi:palette",
            mode=2,
            value_getter=self.reachy_controller.get_led_color_r,
            value_setter=self.reachy_controller.set_led_color_r,
        )
        self.state.entities.append(led_color_r)

        # LED Color G
        led_color_g = NumberEntity(
            server=self,
            key=self._get_entity_key("led_color_g"),
            name="LED Color Green",
            object_id="led_color_g",
            min_value=0.0,
            max_value=255.0,
            step=1.0,
            icon="mdi:palette",
            mode=2,
            value_getter=self.reachy_controller.get_led_color_g,
            value_setter=self.reachy_controller.set_led_color_g,
        )
        self.state.entities.append(led_color_g)

        # LED Color B
        led_color_b = NumberEntity(
            server=self,
            key=self._get_entity_key("led_color_b"),
            name="LED Color Blue",
            object_id="led_color_b",
            min_value=0.0,
            max_value=255.0,
            step=1.0,
            icon="mdi:palette",
            mode=2,
            value_getter=self.reachy_controller.get_led_color_b,
            value_setter=self.reachy_controller.set_led_color_b,
        )
        self.state.entities.append(led_color_b)

        _LOGGER.info("Phase 11 entities registered: led_brightness, led_effect, led_color_r/g/b")

    def _setup_phase12_entities(self) -> None:
        """Setup Phase 12 entities: Audio processing parameters (via local SDK)."""

        # AGC Enabled
        agc_enabled = SwitchEntity(
            server=self,
            key=self._get_entity_key("agc_enabled"),
            name="AGC Enabled",
            object_id="agc_enabled",
            icon="mdi:tune-vertical",
            device_class="switch",
            value_getter=self.reachy_controller.get_agc_enabled,
            value_setter=self.reachy_controller.set_agc_enabled,
        )
        self.state.entities.append(agc_enabled)

        # AGC Max Gain
        agc_max_gain = NumberEntity(
            server=self,
            key=self._get_entity_key("agc_max_gain"),
            name="AGC Max Gain",
            object_id="agc_max_gain",
            min_value=0.0,
            max_value=30.0,
            step=1.0,
            icon="mdi:volume-plus",
            unit_of_measurement="dB",
            mode=2,
            value_getter=self.reachy_controller.get_agc_max_gain,
            value_setter=self.reachy_controller.set_agc_max_gain,
        )
        self.state.entities.append(agc_max_gain)

        # Noise Suppression Level
        noise_suppression = NumberEntity(
            server=self,
            key=self._get_entity_key("noise_suppression"),
            name="Noise Suppression",
            object_id="noise_suppression",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            icon="mdi:volume-off",
            unit_of_measurement="%",
            mode=2,
            value_getter=self.reachy_controller.get_noise_suppression,
            value_setter=self.reachy_controller.set_noise_suppression,
        )
        self.state.entities.append(noise_suppression)

        # Echo Cancellation Converged
        echo_cancellation_converged = BinarySensorEntity(
            server=self,
            key=self._get_entity_key("echo_cancellation_converged"),
            name="Echo Cancellation Converged",
            object_id="echo_cancellation_converged",
            icon="mdi:waveform",
            device_class="running",
            value_getter=self.reachy_controller.get_echo_cancellation_converged,
        )
        self.state.entities.append(echo_cancellation_converged)

        _LOGGER.info("Phase 12 entities registered: agc_enabled, agc_max_gain, noise_suppression, echo_cancellation_converged")
