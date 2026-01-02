"""Voice satellite protocol for Reachy Mini."""

import hashlib
import logging
import posixpath
import shutil
import time
from collections.abc import Iterable
from typing import Dict, Optional, Set, Union
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    DeviceInfoRequest,
    DeviceInfoResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    SubscribeHomeAssistantStatesRequest,
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
from .entity import BinarySensorEntity, MediaPlayerEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SensorEntity, SwitchEntity, SelectEntity, ButtonEntity
from .models import AvailableWakeWord, ServerState, WakeWordType
from .util import call_all
from .reachy_controller import ReachyController

_LOGGER = logging.getLogger(__name__)


class VoiceSatelliteProtocol(APIServer):
    """Voice satellite protocol handler for ESPHome."""

    def __init__(self, state: ServerState) -> None:
        super().__init__(state.name)
        self.state = state
        self.state.satellite = self

        # Initialize Reachy controller
        self.reachy_controller = ReachyController(state.reachy_mini)

        if self.state.media_player_entity is None:
            self.state.media_player_entity = MediaPlayerEntity(
                server=self,
                key=len(state.entities),
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
                MediaPlayerCommandRequest,
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

    # -------------------------------------------------------------------------
    # Entity Setup Methods
    # -------------------------------------------------------------------------

    def _setup_phase1_entities(self) -> None:
        """Setup Phase 1 entities: Basic status and volume control."""

        # Daemon state sensor
        daemon_state_sensor = TextSensorEntity(
            server=self,
            key=len(self.state.entities),
            name="Daemon State",
            object_id="daemon_state",
            icon="mdi:robot",
            value_getter=self.reachy_controller.get_daemon_state,
        )
        self.state.entities.append(daemon_state_sensor)

        # Backend ready sensor
        backend_ready_sensor = BinarySensorEntity(
            server=self,
            key=len(self.state.entities),
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
            key=len(self.state.entities),
            name="Error Message",
            object_id="error_message",
            icon="mdi:alert-circle",
            value_getter=self.reachy_controller.get_error_message,
        )
        self.state.entities.append(error_message_sensor)

        # Speaker volume control
        speaker_volume = NumberEntity(
            server=self,
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
            key=len(self.state.entities),
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
