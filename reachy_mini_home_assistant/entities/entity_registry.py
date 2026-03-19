"""Entity registry for ESPHome entities.

This module handles the registration and management of all ESPHome entities
for the Reachy Mini voice assistant.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

from ..core.system_diagnostics import get_system_diagnostics
from ..models import Preferences
from .entity import BinarySensorEntity, CameraEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SelectEntity, SensorEntity, SwitchEntity
from .entity_factory import (
    create_entity,
    get_diagnostic_sensor_definitions,
    get_imu_sensor_definitions,
    get_look_at_definitions,
    get_pose_control_definitions,
    get_robot_info_definitions,
)
from .entity_keys import get_entity_key

if TYPE_CHECKING:
    from ..reachy_controller import ReachyController
    from ..vision.camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


class EntityRegistry:
    """Registry for managing ESPHome entities."""

    def __init__(
        self,
        server,
        reachy_controller: "ReachyController",
        camera_server: Optional["MJPEGCameraServer"] = None,
        play_emotion_callback: Callable[[str], None] | None = None,
    ):
        """Initialize the entity registry.

        Args:
            server: The VoiceSatelliteProtocol server instance
            reachy_controller: The ReachyController instance
            camera_server: Optional camera server for camera entity
            play_emotion_callback: Optional callback for playing emotions
        """
        self.server = server
        self.reachy_controller = reachy_controller
        self.camera_server = camera_server
        self._play_emotion_callback = play_emotion_callback

        # Sleep state entities (will be initialized in _setup_phase2_entities)
        self._sleep_mode_entity: BinarySensorEntity | None = None
        self._services_suspended_entity: BinarySensorEntity | None = None
        self._face_detected_entity: BinarySensorEntity | None = None
        self._gesture_entity: TextSensorEntity | None = None
        self._gesture_confidence_entity: SensorEntity | None = None

        # Gesture detection state
        self._current_gesture = "none"
        self._gesture_confidence = 0.0

        # Emotion state
        self._current_emotion = "None"
        # Map emotion names to available robot emotions
        # Full list of available emotions from robot
        self._emotion_map = {
            "None": None,
            # Basic emotions
            "Happy": "cheerful1",
            "Sad": "sad1",
            "Angry": "rage1",
            "Fear": "fear1",
            "Surprise": "surprised1",
            "Disgust": "disgusted1",
            # Extended emotions
            "Laughing": "laughing1",
            "Loving": "loving1",
            "Proud": "proud1",
            "Grateful": "grateful1",
            "Enthusiastic": "enthusiastic1",
            "Curious": "curious1",
            "Amazed": "amazed1",
            "Shy": "shy1",
            "Confused": "confused1",
            "Thoughtful": "thoughtful1",
            "Anxious": "anxiety1",
            "Scared": "scared1",
            "Frustrated": "frustrated1",
            "Irritated": "irritated1",
            "Furious": "furious1",
            "Contempt": "contempt1",
            "Bored": "boredom1",
            "Tired": "tired1",
            "Exhausted": "exhausted1",
            "Lonely": "lonely1",
            "Downcast": "downcast1",
            "Resigned": "resigned1",
            "Uncertain": "uncertain1",
            "Uncomfortable": "uncomfortable1",
            "Lost": "lost1",
            "Indifferent": "indifferent1",
            # Positive actions
            "Yes": "yes1",
            "No": "no1",
            "Welcoming": "welcoming1",
            "Helpful": "helpful1",
            "Attentive": "attentive1",
            "Understanding": "understanding1",
            "Calming": "calming1",
            "Relief": "relief1",
            "Success": "success1",
            "Serenity": "serenity1",
            # Negative actions
            "Oops": "oops1",
            "Displeased": "displeased1",
            "Impatient": "impatient1",
            "Reprimand": "reprimand1",
            "GoAway": "go_away1",
            # Special
            "Come": "come1",
            "Inquiring": "inquiring1",
            "Sleep": "sleep1",
            "Dance": "dance1",
            "Electric": "electric1",
            "Dying": "dying1",
        }

    def _get_preferences(self) -> Preferences | None:
        return self.server.state.preferences

    def _get_server_state(self):
        return self.server.state

    def _save_preferences(self) -> None:
        self.server.state.save_preferences()

    def _set_preference_and_save(self, key: str, value) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, value)
            self._save_preferences()

    def _idle_behavior_allows_vision(self) -> bool:
        prefs = self._get_preferences()
        return bool(prefs.idle_behavior_enabled) if prefs is not None else False

    def _apply_vision_runtime_state(self) -> None:
        if self.camera_server is None:
            return

        prefs = self._get_preferences()
        if prefs is None:
            self.camera_server.set_face_tracking_enabled(False)
            self.camera_server.set_gesture_detection_enabled(False)
            return

        if not prefs.idle_behavior_enabled:
            self.camera_server.set_face_tracking_enabled(False)
            self.camera_server.set_gesture_detection_enabled(False)
            return

        self.camera_server.set_face_tracking_enabled(bool(prefs.face_tracking_enabled))
        self.camera_server.set_gesture_detection_enabled(bool(prefs.gesture_detection_enabled))

    def _get_pref_bool(self, key: str, default: bool = False) -> bool:
        prefs = self._get_preferences()
        return bool(getattr(prefs, key, default)) if prefs is not None else default

    def _set_pref_bool(self, key: str, enabled: bool) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, bool(enabled))
            self._save_preferences()

    def _get_pref_float(self, key: str, default: float) -> float:
        prefs = self._get_preferences()
        return float(getattr(prefs, key, default)) if prefs is not None else default

    def _set_pref_float(self, key: str, value: float) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, float(value))
            self._save_preferences()

    def _set_idle_behavior_enabled(self, enabled: bool) -> None:
        self.reachy_controller.set_idle_behavior_enabled(enabled)

        prefs = self._get_preferences()
        if prefs is not None:
            prefs.set_idle_behavior_enabled(enabled)
            if not enabled:
                prefs.face_tracking_enabled = False
                prefs.gesture_detection_enabled = False
            self._save_preferences()

        self._apply_vision_runtime_state()

    def _make_preference_switch(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        getter: Callable[[], bool],
        setter: Callable[[bool], None],
    ) -> SwitchEntity:
        """Create a switch entity with the common registry wiring."""
        return SwitchEntity(
            server=self.server,
            key=get_entity_key(key_name),
            name=name,
            object_id=object_id,
            icon=icon,
            entity_category=1,
            value_getter=getter,
            value_setter=setter,
        )

    def _make_stored_switch(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        pref_key: str,
        getter_transform: Callable[[bool], bool] | None = None,
        setter_transform: Callable[[bool], bool] | None = None,
        after_set: Callable[[], None] | None = None,
    ) -> SwitchEntity:
        """Create a switch backed by preferences with optional transforms/hooks."""

        def getter() -> bool:
            value = self._get_pref_bool(pref_key)
            return getter_transform(value) if getter_transform is not None else value

        def setter(enabled: bool) -> None:
            stored = setter_transform(enabled) if setter_transform is not None else enabled
            self._set_pref_bool(pref_key, stored)
            if after_set is not None:
                after_set()

        return self._make_preference_switch(
            key_name=key_name,
            name=name,
            object_id=object_id,
            icon=icon,
            getter=getter,
            setter=setter,
        )

    def _make_preference_number(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        getter: Callable[[], float],
        setter: Callable[[float], None],
        min_value: float,
        max_value: float,
        step: float,
        mode: int = 2,
    ) -> NumberEntity:
        """Create a number entity with the common registry wiring."""
        return NumberEntity(
            server=self.server,
            key=get_entity_key(key_name),
            name=name,
            object_id=object_id,
            min_value=min_value,
            max_value=max_value,
            step=step,
            icon=icon,
            mode=mode,
            entity_category=1,
            value_getter=getter,
            value_setter=setter,
        )

    def _append_defined_entities(
        self,
        entities: list,
        definitions: list,
        callback_map: dict[str, tuple[Callable, Callable] | Callable],
    ) -> None:
        """Bind callbacks to declarative definitions and append created entities."""
        for definition in definitions:
            callbacks = callback_map.get(definition.key_name)
            if isinstance(callbacks, tuple):
                definition.value_getter = callbacks[0]
                definition.command_handler = callbacks[1]
            elif callbacks is not None:
                definition.value_getter = callbacks
            entities.append(create_entity(self.server, definition))

    def setup_all_entities(self, entities: list) -> None:
        """Setup all entity phases."""
        self._setup_phase1_entities(entities)
        self._setup_phase2_entities(entities)
        self._setup_phase3_entities(entities)
        self._setup_phase4_entities(entities)
        self._setup_phase5_entities(entities)  # DOA for wakeup turn-to-sound
        self._setup_phase6_entities(entities)
        self._setup_phase7_entities(entities)
        self._setup_phase8_entities(entities)
        self._setup_phase9_entities(entities)
        self._setup_phase10_entities(entities)
        # Phase 11 (LED control) disabled - LEDs are inside the robot and not visible
        self._setup_phase12_entities(entities)
        # Phase 13 (Sendspin) - auto-enabled via mDNS discovery, no user entities
        # Phase 14 (head_joints, passive_joints) removed - not needed
        # Phase 20 (Tap detection) disabled - too many false triggers
        self._setup_phase21_entities(entities)
        self._setup_phase22_entities(entities)
        self._setup_phase23_entities(entities)
        self._setup_phase24_entities(entities)  # System diagnostics

        _LOGGER.info("All entities registered: %d total", len(entities))

    def _setup_phase1_entities(self, entities: list) -> None:
        """Setup Phase 1 entities: Basic status and volume control."""
        rc = self.reachy_controller

        entities.append(
            TextSensorEntity(
                server=self.server,
                key=get_entity_key("daemon_state"),
                name="Daemon State",
                object_id="daemon_state",
                icon="mdi:robot",
                value_getter=rc.get_daemon_state,
            )
        )

        entities.append(
            BinarySensorEntity(
                server=self.server,
                key=get_entity_key("backend_ready"),
                name="Backend Ready",
                object_id="backend_ready",
                icon="mdi:check-circle",
                device_class="connectivity",
                value_getter=rc.get_backend_ready,
            )
        )

        entities.append(
            NumberEntity(
                server=self.server,
                key=get_entity_key("speaker_volume"),
                name="Speaker Volume",
                object_id="speaker_volume",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                icon="mdi:volume-high",
                unit_of_measurement="%",
                mode=2,  # Slider mode
                entity_category=1,  # config
                value_getter=rc.get_speaker_volume,
                value_setter=rc.set_speaker_volume,
            )
        )

        def get_muted() -> bool:
            state = self._get_server_state()
            return bool(state.is_muted)

        def set_muted(muted: bool) -> None:
            state = self._get_server_state()
            state.is_muted = muted
            voice_assistant = self.server._voice_assistant_service
            if muted:
                voice_assistant._suspend_voice_services(reason="mute")
            else:
                voice_assistant._resume_voice_services(reason="mute")

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("mute"),
                name="Mute",
                object_id="mute",
                icon="mdi:microphone-off",
                entity_category=1,
                value_getter=get_muted,
                value_setter=set_muted,
            )
        )

        def get_camera_disabled() -> bool:
            state = self._get_server_state()
            return not state.camera_enabled if state is not None else False

        def set_camera_disabled(disabled: bool) -> None:
            state = self._get_server_state()
            if state is None:
                return
            state.camera_enabled = not disabled
            if self.camera_server:
                if disabled:
                    self.camera_server.suspend()
                else:
                    self.camera_server.resume_from_suspend()

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("camera_disabled"),
                name="Disable Camera",
                object_id="camera_disabled",
                icon="mdi:camera-off",
                entity_category=1,
                value_getter=get_camera_disabled,
                value_setter=set_camera_disabled,
            )
        )

        def get_idle_behavior_enabled() -> bool:
            prefs = self._get_preferences()
            return bool(prefs.idle_behavior_enabled) if prefs is not None else False

        def set_idle_behavior_enabled(enabled: bool) -> None:
            self._set_idle_behavior_enabled(enabled)

        entities.append(
            self._make_preference_switch(
                key_name="idle_behavior_enabled",
                name="Idle Behavior",
                object_id="idle_behavior_enabled",
                icon="mdi:motion-play",
                getter=get_idle_behavior_enabled,
                setter=set_idle_behavior_enabled,
            )
        )

        def sync_sendspin() -> None:
            self.server._voice_assistant_service.set_sendspin_enabled(self._get_pref_bool("sendspin_enabled"))

        entities.append(
            self._make_stored_switch(
                key_name="sendspin_enabled",
                name="Sendspin",
                object_id="sendspin_enabled",
                icon="mdi:speaker-wireless",
                pref_key="sendspin_enabled",
                after_set=sync_sendspin,
            )
        )

        entities.append(
            self._make_stored_switch(
                key_name="face_tracking_enabled",
                name="Face Tracking",
                object_id="face_tracking_enabled",
                icon="mdi:face-recognition",
                pref_key="face_tracking_enabled",
                getter_transform=lambda value: value and self._idle_behavior_allows_vision(),
                setter_transform=lambda enabled: enabled and self._idle_behavior_allows_vision(),
                after_set=self._apply_vision_runtime_state,
            )
        )

        entities.append(
            self._make_stored_switch(
                key_name="gesture_detection_enabled",
                name="Gesture Detection",
                object_id="gesture_detection_enabled",
                icon="mdi:hand-wave",
                pref_key="gesture_detection_enabled",
                getter_transform=lambda value: value and self._idle_behavior_allows_vision(),
                setter_transform=lambda enabled: enabled and self._idle_behavior_allows_vision(),
                after_set=self._apply_vision_runtime_state,
            )
        )

        def get_face_confidence_threshold() -> float:
            return self._get_pref_float("face_confidence_threshold", 0.5)

        def set_face_confidence_threshold(value: float) -> None:
            value = max(0.0, min(1.0, float(value)))
            self._set_pref_float("face_confidence_threshold", value)
            if self.camera_server is not None:
                self.camera_server.set_face_confidence_threshold(value)

        entities.append(
            self._make_preference_number(
                key_name="face_confidence_threshold",
                name="Face Confidence",
                object_id="face_confidence_threshold",
                icon="mdi:target",
                getter=get_face_confidence_threshold,
                setter=set_face_confidence_threshold,
                min_value=0.0,
                max_value=1.0,
                step=0.01,
            )
        )

        _LOGGER.debug(
            "Phase 1 entities registered: daemon_state, backend_ready, speaker_volume, mute, camera_disabled, "
            "idle_behavior_enabled, sendspin_enabled, "
            "face_tracking_enabled, gesture_detection_enabled, "
            "face_confidence_threshold"
        )

    def _setup_phase2_entities(self, entities: list) -> None:
        """Setup Phase 2 entities: Motor control."""
        rc = self.reachy_controller

        def get_sleep_control() -> bool:
            if self._sleep_mode_entity is not None:
                return not bool(self._sleep_mode_entity.value)
            return False

        def set_sleep_control(sleeping: bool) -> None:
            is_sleeping = get_sleep_control()
            if sleeping == is_sleeping:
                return
            if sleeping:
                rc.go_to_sleep()
            else:
                rc.wake_up()

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("sleep_control"),
                name="Sleep Control",
                object_id="sleep_control",
                icon="mdi:sleep",
                entity_category=1,
                value_getter=get_sleep_control,
                value_setter=set_sleep_control,
            )
        )

        self._sleep_mode_entity = BinarySensorEntity(
            server=self.server,
            key=get_entity_key("sleep_mode"),
            name="Sleep Mode",
            object_id="sleep_mode",
            icon="mdi:sleep",
            device_class="running",  # Shows as "Running/Not Running" which maps well to awake/sleeping
        )
        entities.append(self._sleep_mode_entity)

        self._services_suspended_entity = BinarySensorEntity(
            server=self.server,
            key=get_entity_key("services_suspended"),
            name="Services Suspended",
            object_id="services_suspended",
            icon="mdi:pause-circle",
            device_class="running",
        )
        entities.append(self._services_suspended_entity)

        _LOGGER.debug("Phase 2 entities registered: sleep_control, sleep_mode, services_suspended")

    def _setup_phase3_entities(self, entities: list) -> None:
        """Setup Phase 3 entities: Pose control."""
        rc = self.reachy_controller

        callback_map = {
            "head_x": (rc.get_head_x, rc.set_head_x),
            "head_y": (rc.get_head_y, rc.set_head_y),
            "head_z": (rc.get_head_z, rc.set_head_z),
            "head_roll": (rc.get_head_roll, rc.set_head_roll),
            "head_pitch": (rc.get_head_pitch, rc.set_head_pitch),
            "head_yaw": (rc.get_head_yaw, rc.set_head_yaw),
            "body_yaw": (rc.get_body_yaw, rc.set_body_yaw),
            "antenna_left": (rc.get_antenna_left, rc.set_antenna_left),
            "antenna_right": (rc.get_antenna_right, rc.set_antenna_right),
        }

        self._append_defined_entities(entities, get_pose_control_definitions(), callback_map)

        _LOGGER.debug("Phase 3 entities registered: head position/orientation, body_yaw, antennas")

    def _setup_phase4_entities(self, entities: list) -> None:
        """Setup Phase 4 entities: Look at control."""
        rc = self.reachy_controller

        callback_map = {
            "look_at_x": (rc.get_look_at_x, rc.set_look_at_x),
            "look_at_y": (rc.get_look_at_y, rc.set_look_at_y),
            "look_at_z": (rc.get_look_at_z, rc.set_look_at_z),
        }

        self._append_defined_entities(entities, get_look_at_definitions(), callback_map)

        _LOGGER.debug("Phase 4 entities registered: look_at_x/y/z")

    def _setup_phase5_entities(self, entities: list) -> None:
        """Setup Phase 5 entities: DOA (Direction of Arrival) for wakeup turn-to-sound."""
        rc = self.reachy_controller

        entities.append(
            SensorEntity(
                server=self.server,
                key=get_entity_key("doa_angle"),
                name="DOA Angle",
                object_id="doa_angle",
                icon="mdi:surround-sound",
                unit_of_measurement="°",
                accuracy_decimals=1,
                state_class="measurement",
                value_getter=rc.get_doa_angle_degrees,
            )
        )

        entities.append(
            BinarySensorEntity(
                server=self.server,
                key=get_entity_key("speech_detected"),
                name="Speech Detected",
                object_id="speech_detected",
                icon="mdi:account-voice",
                device_class="sound",
                value_getter=rc.get_speech_detected,
            )
        )

        def get_doa_tracking_state() -> bool:
            if rc._movement_manager is not None:
                return rc._movement_manager._doa_enabled
            return True

        def set_doa_tracking_state(enabled: bool) -> None:
            if rc._movement_manager is not None:
                rc._movement_manager.set_doa_enabled(enabled)
            _LOGGER.info("DOA tracking %s", "enabled" if enabled else "disabled")

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("doa_tracking_enabled"),
                name="DOA Sound Tracking",
                object_id="doa_tracking_enabled",
                icon="mdi:ear-hearing",
                value_getter=get_doa_tracking_state,
                value_setter=set_doa_tracking_state,
            )
        )

        _LOGGER.debug("Phase 5 entities registered: doa_angle, speech_detected, doa_tracking_enabled")

    def _setup_phase6_entities(self, entities: list) -> None:
        """Setup Phase 6 entities: Diagnostic information."""
        rc = self.reachy_controller

        getter_map = {
            "control_loop_frequency": rc.get_control_loop_frequency,
            "sdk_version": rc.get_sdk_version,
            "robot_name": rc.get_robot_name,
            "wireless_version": rc.get_wireless_version,
            "simulation_mode": rc.get_simulation_mode,
            "wlan_ip": rc.get_wlan_ip,
            "error_message": rc.get_error_message,
        }

        definitions = get_robot_info_definitions()
        self._append_defined_entities(entities, definitions, getter_map)

        _LOGGER.debug(
            "Phase 6 entities registered: control_loop_frequency, sdk_version, "
            "robot_name, wireless_version, simulation_mode, wlan_ip, error_message"
        )

    def _setup_phase7_entities(self, entities: list) -> None:
        """Setup Phase 7 entities: IMU sensors (wireless only)."""
        rc = self.reachy_controller

        getter_map = {
            "imu_accel_x": rc.get_imu_accel_x,
            "imu_accel_y": rc.get_imu_accel_y,
            "imu_accel_z": rc.get_imu_accel_z,
            "imu_gyro_x": rc.get_imu_gyro_x,
            "imu_gyro_y": rc.get_imu_gyro_y,
            "imu_gyro_z": rc.get_imu_gyro_z,
            "imu_temperature": rc.get_imu_temperature,
        }

        self._append_defined_entities(entities, get_imu_sensor_definitions(), getter_map)

        _LOGGER.debug("Phase 7 entities registered: IMU accelerometer, gyroscope, temperature")

    def _setup_phase8_entities(self, entities: list) -> None:
        """Setup Phase 8 entities: Emotion selector."""

        def get_emotion() -> str:
            return self._current_emotion

        def set_emotion(emotion: str) -> None:
            self._current_emotion = emotion
            emotion_name = self._emotion_map.get(emotion)
            if emotion_name and self._play_emotion_callback:
                self._play_emotion_callback(emotion_name)
                # Reset to None after playing
                self._current_emotion = "None"

        entities.append(
            SelectEntity(
                server=self.server,
                key=get_entity_key("emotion"),
                name="Emotion",
                object_id="emotion",
                options=list(self._emotion_map.keys()),
                icon="mdi:emoticon",
                value_getter=get_emotion,
                value_setter=set_emotion,
            )
        )

        _LOGGER.debug("Phase 8 entities registered: emotion selector")

    def _setup_phase9_entities(self, entities: list) -> None:
        """Setup Phase 9 entities: Audio controls."""
        rc = self.reachy_controller

        entities.append(
            NumberEntity(
                server=self.server,
                key=get_entity_key("microphone_volume"),
                name="Microphone Volume",
                object_id="microphone_volume",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                icon="mdi:microphone",
                unit_of_measurement="%",
                mode=2,  # Slider mode
                entity_category=1,  # config
                value_getter=rc.get_microphone_volume,
                value_setter=rc.set_microphone_volume,
            )
        )

        _LOGGER.debug("Phase 9 entities registered: microphone_volume")

    def _setup_phase10_entities(self, entities: list) -> None:
        """Setup Phase 10 entities: Camera for Home Assistant integration."""

        def get_camera_image() -> bytes | None:
            if self.camera_server:
                try:
                    return self.camera_server.get_snapshot()
                except Exception as e:
                    _LOGGER.debug("Failed to get camera snapshot: %s", e)
            return None

        entities.append(
            CameraEntity(
                server=self.server,
                key=get_entity_key("camera"),
                name="Camera",
                object_id="camera",
                icon="mdi:camera",
                image_getter=get_camera_image,
            )
        )

        _LOGGER.debug("Phase 10 entities registered: camera (ESPHome Camera entity)")

    def _setup_phase12_entities(self, entities: list) -> None:
        """Setup Phase 12 entities: Audio processing parameters (via local SDK)."""
        rc = self.reachy_controller

        def set_agc_enabled_with_save(enabled: bool) -> None:
            rc.set_agc_enabled(enabled)
            self._set_preference_and_save("agc_enabled", enabled)
            _LOGGER.debug("AGC enabled saved to preferences: %s", enabled)

        def set_agc_max_gain_with_save(gain: float) -> None:
            rc.set_agc_max_gain(gain)
            self._set_preference_and_save("agc_max_gain", gain)
            _LOGGER.debug("AGC max gain saved to preferences: %.1f dB", gain)

        def set_noise_suppression_with_save(level: float) -> None:
            rc.set_noise_suppression(level)
            self._set_preference_and_save("noise_suppression", level)
            _LOGGER.debug("Noise suppression saved to preferences: %.1f%%", level)

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("agc_enabled"),
                name="AGC Enabled",
                object_id="agc_enabled",
                icon="mdi:tune-vertical",
                device_class="switch",
                entity_category=1,  # config
                value_getter=rc.get_agc_enabled,
                value_setter=set_agc_enabled_with_save,
            )
        )

        entities.append(
            NumberEntity(
                server=self.server,
                key=get_entity_key("agc_max_gain"),
                name="AGC Max Gain",
                object_id="agc_max_gain",
                min_value=0.0,
                max_value=40.0,  # XVF3800 supports up to 40dB
                step=1.0,
                icon="mdi:volume-plus",
                unit_of_measurement="dB",
                mode=2,
                entity_category=1,  # config
                value_getter=rc.get_agc_max_gain,
                value_setter=set_agc_max_gain_with_save,
            )
        )

        entities.append(
            NumberEntity(
                server=self.server,
                key=get_entity_key("noise_suppression"),
                name="Noise Suppression",
                object_id="noise_suppression",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                icon="mdi:volume-off",
                unit_of_measurement="%",
                mode=2,
                entity_category=1,  # config
                value_getter=rc.get_noise_suppression,
                value_setter=set_noise_suppression_with_save,
            )
        )

        entities.append(
            BinarySensorEntity(
                server=self.server,
                key=get_entity_key("echo_cancellation_converged"),
                name="Echo Cancellation Converged",
                object_id="echo_cancellation_converged",
                icon="mdi:waveform",
                device_class="running",
                entity_category=2,  # diagnostic
                value_getter=rc.get_echo_cancellation_converged,
            )
        )

        _LOGGER.debug(
            "Phase 12 entities registered: agc_enabled, agc_max_gain, noise_suppression, echo_cancellation_converged"
        )

    def _setup_phase21_entities(self, entities: list) -> None:
        """Setup Phase 21 entities: Continuous conversation mode."""

        def get_continuous_conversation() -> bool:
            return self._get_pref_bool("continuous_conversation")

        def set_continuous_conversation(enabled: bool) -> None:
            self._set_pref_bool("continuous_conversation", enabled)
            _LOGGER.info("Continuous conversation mode %s", "enabled" if enabled else "disabled")

        entities.append(
            SwitchEntity(
                server=self.server,
                key=get_entity_key("continuous_conversation"),
                name="Continuous Conversation",
                object_id="continuous_conversation",
                icon="mdi:message-reply-text",
                device_class="switch",
                entity_category=1,  # config
                value_getter=get_continuous_conversation,
                value_setter=set_continuous_conversation,
            )
        )

        _LOGGER.debug("Phase 21 entities registered: continuous_conversation")

    def _setup_phase22_entities(self, entities: list) -> None:
        """Setup Phase 22 entities: Gesture detection."""

        def get_gesture() -> str:
            """Get current detected gesture."""
            if self.camera_server:
                return self.camera_server.get_current_gesture()
            return "none"

        def get_gesture_confidence() -> float:
            """Get gesture detection confidence."""
            if self.camera_server:
                return self.camera_server.get_gesture_confidence()
            return 0.0

        gesture_entity = TextSensorEntity(
            server=self.server,
            key=get_entity_key("gesture_detected"),
            name="Gesture Detected",
            object_id="gesture_detected",
            icon="mdi:hand-wave",
            value_getter=get_gesture,
        )
        entities.append(gesture_entity)
        self._gesture_entity = gesture_entity

        confidence_entity = SensorEntity(
            server=self.server,
            key=get_entity_key("gesture_confidence"),
            name="Gesture Confidence",
            object_id="gesture_confidence",
            icon="mdi:percent",
            unit_of_measurement="%",
            accuracy_decimals=1,
            state_class="measurement",
            value_getter=get_gesture_confidence,
        )
        entities.append(confidence_entity)
        self._gesture_confidence_entity = confidence_entity

        _LOGGER.debug("Phase 22 entities registered: gesture_detected, gesture_confidence")

    def _setup_phase23_entities(self, entities: list) -> None:
        """Setup Phase 23 entities: Face detection status."""

        def get_face_detected() -> bool:
            """Get current face detection state from camera server."""
            if self.camera_server:
                return self.camera_server.is_face_detected()
            return False

        face_detected_entity = BinarySensorEntity(
            server=self.server,
            key=get_entity_key("face_detected"),
            name="Face Detected",
            object_id="face_detected",
            icon="mdi:face-recognition",
            device_class="occupancy",
            value_getter=get_face_detected,
        )
        entities.append(face_detected_entity)
        self._face_detected_entity = face_detected_entity

        _LOGGER.debug("Phase 23 entities registered: face_detected")

    def update_face_detected_state(self) -> None:
        """Push face_detected state update to Home Assistant."""
        if self._face_detected_entity:
            self._face_detected_entity.update_state()

    def update_gesture_state(self) -> None:
        """Push gesture state update to Home Assistant."""
        if self._gesture_entity:
            self._gesture_entity.update_state()
        if self._gesture_confidence_entity:
            self._gesture_confidence_entity.update_state()

    def set_sleep_mode(self, is_sleeping: bool) -> None:
        """Update the sleep mode state and push to Home Assistant.

        Args:
            is_sleeping: True if robot is in sleep mode, False if awake
        """
        if self._sleep_mode_entity is not None:
            # For "running" device_class, True = running (awake), False = not running (sleeping)
            # So we invert the is_sleeping value
            self._sleep_mode_entity._state = not is_sleeping
            self._sleep_mode_entity.update_state()
            _LOGGER.debug("Sleep mode state updated: sleeping=%s", is_sleeping)

    def set_services_suspended(self, is_suspended: bool) -> None:
        """Update the services suspended state and push to Home Assistant.

        Args:
            is_suspended: True if services are suspended (ML models unloaded)
        """
        if self._services_suspended_entity is not None:
            # For "running" device_class, True = running, False = not running
            # So we invert: suspended means NOT running
            self._services_suspended_entity._state = not is_suspended
            self._services_suspended_entity.update_state()
            _LOGGER.debug("Services suspended state updated: suspended=%s", is_suspended)

    def find_entity_references(self, entities: list) -> None:
        """Find and store references to special entities from existing list.

        Args:
            entities: The list of existing entities to search
        """
        # DOA entities are read-only sensors, no special references needed
        pass

    def _setup_phase24_entities(self, entities: list) -> None:
        """Setup Phase 24 entities: System diagnostics (psutil).

        These sensors provide system health information for the robot's
        computer, useful for monitoring resource usage and debugging.
        """
        diag = get_system_diagnostics()

        definitions = get_diagnostic_sensor_definitions()
        getter_map = {
            "sys_cpu_percent": diag.get_cpu_percent,
            "sys_cpu_temperature": diag.get_cpu_temperature,
            "sys_memory_percent": diag.get_memory_percent,
            "sys_memory_used": diag.get_memory_used_gb,
            "sys_disk_percent": diag.get_disk_percent,
            "sys_disk_free": diag.get_disk_free_gb,
            "sys_uptime": diag.get_uptime_hours,
            "sys_process_cpu": diag.get_process_cpu_percent,
            "sys_process_memory": diag.get_process_memory_mb,
        }

        self._append_defined_entities(entities, definitions, getter_map)

        _LOGGER.debug("Phase 24 entities registered: %d diagnostic sensors", len(definitions))
