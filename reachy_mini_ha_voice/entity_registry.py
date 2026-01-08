"""Entity registry for ESPHome entities.

This module handles the registration and management of all ESPHome entities
for the Reachy Mini voice assistant.
"""

import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from .entity import BinarySensorEntity, CameraEntity, MediaPlayerEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SensorEntity, SwitchEntity, SelectEntity, ButtonEntity

if TYPE_CHECKING:
    from .reachy_controller import ReachyController
    from .camera_server import MJPEGCameraServer
    from .tap_detector import TapDetector

_LOGGER = logging.getLogger(__name__)


# Fixed entity key mapping - ensures consistent keys across restarts
# Keys are based on object_id hash to ensure uniqueness and consistency
ENTITY_KEYS: Dict[str, int] = {
    # Media player (key 0 reserved)
    "reachy_mini_media_player": 0,
    # Phase 1: Basic status and volume
    "daemon_state": 100,
    "backend_ready": 101,
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
    # Phase 6: Diagnostic information
    "control_loop_frequency": 600,
    "sdk_version": 601,
    "robot_name": 602,
    "wireless_version": 603,
    "simulation_mode": 604,
    "wlan_ip": 605,
    "error_message": 606,  # Moved to diagnostic
    # Phase 7: IMU sensors
    "imu_accel_x": 700,
    "imu_accel_y": 701,
    "imu_accel_z": 702,
    "imu_gyro_x": 703,
    "imu_gyro_y": 704,
    "imu_gyro_z": 705,
    "imu_temperature": 706,
    # Phase 8: Emotion selector
    "emotion": 800,
    # Phase 9: Audio controls
    "microphone_volume": 900,
    # Phase 10: Camera
    "camera_url": 1000,  # Keep for backward compatibility
    "camera": 1001,      # New camera entity
    # Phase 11: LED control (disabled - not visible)
    # "led_brightness": 1100,
    # "led_effect": 1101,
    # "led_color_r": 1102,
    # "led_color_g": 1103,
    # "led_color_b": 1104,
    # Phase 12: Audio processing
    "agc_enabled": 1200,
    "agc_max_gain": 1201,
    "noise_suppression": 1202,
    "echo_cancellation_converged": 1203,
    # Phase 13: Sendspin - auto-enabled via mDNS, no user entities needed
    # Phase 20: Tap detection
    "tap_sensitivity": 1400,
}


def get_entity_key(object_id: str) -> int:
    """Get a consistent entity key for the given object_id."""
    if object_id in ENTITY_KEYS:
        return ENTITY_KEYS[object_id]
    # Fallback: generate key from hash (should not happen if all entities are registered)
    _LOGGER.warning(f"Entity key not found for {object_id}, generating from hash")
    return abs(hash(object_id)) % 10000 + 2000


class EntityRegistry:
    """Registry for managing ESPHome entities."""

    def __init__(
        self,
        server,
        reachy_controller: "ReachyController",
        camera_server: Optional["MJPEGCameraServer"] = None,
        play_emotion_callback: Optional[Callable[[str], None]] = None,
        tap_detector: Optional["TapDetector"] = None,
    ):
        """Initialize the entity registry.

        Args:
            server: The VoiceSatelliteProtocol server instance
            reachy_controller: The ReachyController instance
            camera_server: Optional camera server for camera entity
            play_emotion_callback: Optional callback for playing emotions
            tap_detector: Optional tap detector for sensitivity control
        """
        self.server = server
        self.reachy_controller = reachy_controller
        self.camera_server = camera_server
        self._play_emotion_callback = play_emotion_callback
        self.tap_detector = tap_detector

        # Emotion state
        self._current_emotion = "None"
        self._emotion_map = {
            "None": None,
            "Happy": "happy1",
            "Sad": "sad1",
            "Angry": "angry1",
            "Fear": "fear1",
            "Surprise": "surprise1",
            "Disgust": "disgust1",
        }

    def setup_all_entities(self, entities: List) -> None:
        """Setup all entity phases.

        Args:
            entities: The list to append entities to
        """
        self._setup_phase1_entities(entities)
        self._setup_phase2_entities(entities)
        self._setup_phase3_entities(entities)
        self._setup_phase4_entities(entities)
        # Phase 5 (DOA/speech detection) removed - replaced by face tracking
        self._setup_phase6_entities(entities)
        self._setup_phase7_entities(entities)
        self._setup_phase8_entities(entities)
        self._setup_phase9_entities(entities)
        self._setup_phase10_entities(entities)
        # Phase 11 (LED control) disabled - LEDs are inside the robot and not visible
        self._setup_phase12_entities(entities)
        # Phase 13 (Sendspin) - auto-enabled via mDNS discovery, no user entities
        # Phase 14 (head_joints, passive_joints) removed - not needed
        self._setup_phase20_entities(entities)

        _LOGGER.info("All entities registered: %d total", len(entities))

    def _setup_phase1_entities(self, entities: List) -> None:
        """Setup Phase 1 entities: Basic status and volume control."""
        rc = self.reachy_controller

        entities.append(TextSensorEntity(
            server=self.server,
            key=get_entity_key("daemon_state"),
            name="Daemon State",
            object_id="daemon_state",
            icon="mdi:robot",
            value_getter=rc.get_daemon_state,
        ))

        entities.append(BinarySensorEntity(
            server=self.server,
            key=get_entity_key("backend_ready"),
            name="Backend Ready",
            object_id="backend_ready",
            icon="mdi:check-circle",
            device_class="connectivity",
            value_getter=rc.get_backend_ready,
        ))

        entities.append(NumberEntity(
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
        ))

        _LOGGER.debug("Phase 1 entities registered: daemon_state, backend_ready, speaker_volume")

    def _setup_phase2_entities(self, entities: List) -> None:
        """Setup Phase 2 entities: Motor control."""
        rc = self.reachy_controller

        entities.append(SwitchEntity(
            server=self.server,
            key=get_entity_key("motors_enabled"),
            name="Motors Enabled",
            object_id="motors_enabled",
            icon="mdi:engine",
            device_class="switch",
            value_getter=rc.get_motors_enabled,
            value_setter=rc.set_motors_enabled,
        ))

        entities.append(ButtonEntity(
            server=self.server,
            key=get_entity_key("wake_up"),
            name="Wake Up",
            object_id="wake_up",
            icon="mdi:alarm",
            device_class="restart",
            on_press=rc.wake_up,
        ))

        entities.append(ButtonEntity(
            server=self.server,
            key=get_entity_key("go_to_sleep"),
            name="Go to Sleep",
            object_id="go_to_sleep",
            icon="mdi:sleep",
            device_class="restart",
            on_press=rc.go_to_sleep,
        ))

        _LOGGER.debug("Phase 2 entities registered: motors_enabled, wake_up, go_to_sleep")

    def _setup_phase3_entities(self, entities: List) -> None:
        """Setup Phase 3 entities: Pose control."""
        rc = self.reachy_controller

        # Head position controls (X, Y, Z in mm)
        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_x"),
            name="Head X Position",
            object_id="head_x",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-x-arrow",
            unit_of_measurement="mm",
            mode=2,
            value_getter=rc.get_head_x,
            value_setter=rc.set_head_x,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_y"),
            name="Head Y Position",
            object_id="head_y",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-y-arrow",
            unit_of_measurement="mm",
            mode=2,
            value_getter=rc.get_head_y,
            value_setter=rc.set_head_y,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_z"),
            name="Head Z Position",
            object_id="head_z",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            icon="mdi:axis-z-arrow",
            unit_of_measurement="mm",
            mode=2,
            value_getter=rc.get_head_z,
            value_setter=rc.set_head_z,
        ))

        # Head orientation controls (Roll, Pitch, Yaw in degrees)
        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_roll"),
            name="Head Roll",
            object_id="head_roll",
            min_value=-40.0,
            max_value=40.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_head_roll,
            value_setter=rc.set_head_roll,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_pitch"),
            name="Head Pitch",
            object_id="head_pitch",
            min_value=-40.0,
            max_value=40.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_head_pitch,
            value_setter=rc.set_head_pitch,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("head_yaw"),
            name="Head Yaw",
            object_id="head_yaw",
            min_value=-180.0,
            max_value=180.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_head_yaw,
            value_setter=rc.set_head_yaw,
        ))

        # Body yaw control
        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("body_yaw"),
            name="Body Yaw",
            object_id="body_yaw",
            min_value=-160.0,
            max_value=160.0,
            step=1.0,
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_body_yaw,
            value_setter=rc.set_body_yaw,
        ))

        # Antenna controls
        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("antenna_left"),
            name="Antenna(L)",
            object_id="antenna_left",
            min_value=-90.0,
            max_value=90.0,
            step=1.0,
            icon="mdi:antenna",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_antenna_left,
            value_setter=rc.set_antenna_left,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("antenna_right"),
            name="Antenna(R)",
            object_id="antenna_right",
            min_value=-90.0,
            max_value=90.0,
            step=1.0,
            icon="mdi:antenna",
            unit_of_measurement="°",
            mode=2,
            value_getter=rc.get_antenna_right,
            value_setter=rc.set_antenna_right,
        ))

        _LOGGER.debug("Phase 3 entities registered: head position/orientation, body_yaw, antennas")

    def _setup_phase4_entities(self, entities: List) -> None:
        """Setup Phase 4 entities: Look at control."""
        rc = self.reachy_controller

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("look_at_x"),
            name="Look At X",
            object_id="look_at_x",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,  # Box mode for precise input
            value_getter=rc.get_look_at_x,
            value_setter=rc.set_look_at_x,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("look_at_y"),
            name="Look At Y",
            object_id="look_at_y",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,
            value_getter=rc.get_look_at_y,
            value_setter=rc.set_look_at_y,
        ))

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("look_at_z"),
            name="Look At Z",
            object_id="look_at_z",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            icon="mdi:crosshairs-gps",
            unit_of_measurement="m",
            mode=1,
            value_getter=rc.get_look_at_z,
            value_setter=rc.set_look_at_z,
        ))

        _LOGGER.debug("Phase 4 entities registered: look_at_x/y/z")

    def _setup_phase6_entities(self, entities: List) -> None:
        """Setup Phase 6 entities: Diagnostic information."""
        rc = self.reachy_controller

        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("control_loop_frequency"),
            name="Control Loop Frequency",
            object_id="control_loop_frequency",
            icon="mdi:speedometer",
            unit_of_measurement="Hz",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,  # diagnostic
            value_getter=rc.get_control_loop_frequency,
        ))

        entities.append(TextSensorEntity(
            server=self.server,
            key=get_entity_key("sdk_version"),
            name="SDK Version",
            object_id="sdk_version",
            icon="mdi:information",
            entity_category=2,  # diagnostic
            value_getter=rc.get_sdk_version,
        ))

        entities.append(TextSensorEntity(
            server=self.server,
            key=get_entity_key("robot_name"),
            name="Robot Name",
            object_id="robot_name",
            icon="mdi:robot",
            entity_category=2,  # diagnostic
            value_getter=rc.get_robot_name,
        ))

        entities.append(BinarySensorEntity(
            server=self.server,
            key=get_entity_key("wireless_version"),
            name="Wireless Version",
            object_id="wireless_version",
            icon="mdi:wifi",
            device_class="connectivity",
            entity_category=2,  # diagnostic
            value_getter=rc.get_wireless_version,
        ))

        entities.append(BinarySensorEntity(
            server=self.server,
            key=get_entity_key("simulation_mode"),
            name="Simulation Mode",
            object_id="simulation_mode",
            icon="mdi:virtual-reality",
            entity_category=2,  # diagnostic
            value_getter=rc.get_simulation_mode,
        ))

        entities.append(TextSensorEntity(
            server=self.server,
            key=get_entity_key("wlan_ip"),
            name="WLAN IP",
            object_id="wlan_ip",
            icon="mdi:ip-network",
            entity_category=2,  # diagnostic
            value_getter=rc.get_wlan_ip,
        ))

        entities.append(TextSensorEntity(
            server=self.server,
            key=get_entity_key("error_message"),
            name="Error Message",
            object_id="error_message",
            icon="mdi:alert-circle",
            entity_category=2,  # diagnostic
            value_getter=rc.get_error_message,
        ))

        _LOGGER.debug("Phase 6 entities registered: control_loop_frequency, sdk_version, robot_name, wireless_version, simulation_mode, wlan_ip, error_message")

    def _setup_phase7_entities(self, entities: List) -> None:
        """Setup Phase 7 entities: IMU sensors (wireless only)."""
        rc = self.reachy_controller

        # IMU Accelerometer
        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_accel_x"),
            name="IMU Accel X",
            object_id="imu_accel_x",
            icon="mdi:axis-x-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_accel_x,
        ))

        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_accel_y"),
            name="IMU Accel Y",
            object_id="imu_accel_y",
            icon="mdi:axis-y-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_accel_y,
        ))

        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_accel_z"),
            name="IMU Accel Z",
            object_id="imu_accel_z",
            icon="mdi:axis-z-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_accel_z,
        ))

        # IMU Gyroscope
        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_gyro_x"),
            name="IMU Gyro X",
            object_id="imu_gyro_x",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_gyro_x,
        ))

        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_gyro_y"),
            name="IMU Gyro Y",
            object_id="imu_gyro_y",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_gyro_y,
        ))

        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_gyro_z"),
            name="IMU Gyro Z",
            object_id="imu_gyro_z",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
            value_getter=rc.get_imu_gyro_z,
        ))

        # IMU Temperature
        entities.append(SensorEntity(
            server=self.server,
            key=get_entity_key("imu_temperature"),
            name="IMU Temperature",
            object_id="imu_temperature",
            icon="mdi:thermometer",
            unit_of_measurement="°C",
            accuracy_decimals=1,
            device_class="temperature",
            state_class="measurement",
            value_getter=rc.get_imu_temperature,
        ))

        _LOGGER.debug("Phase 7 entities registered: IMU accelerometer, gyroscope, temperature")

    def _setup_phase8_entities(self, entities: List) -> None:
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

        entities.append(SelectEntity(
            server=self.server,
            key=get_entity_key("emotion"),
            name="Emotion",
            object_id="emotion",
            options=list(self._emotion_map.keys()),
            icon="mdi:emoticon",
            value_getter=get_emotion,
            value_setter=set_emotion,
        ))

        _LOGGER.debug("Phase 8 entities registered: emotion selector")

    def _setup_phase9_entities(self, entities: List) -> None:
        """Setup Phase 9 entities: Audio controls."""
        rc = self.reachy_controller

        entities.append(NumberEntity(
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
        ))

        _LOGGER.debug("Phase 9 entities registered: microphone_volume")

    def _setup_phase10_entities(self, entities: List) -> None:
        """Setup Phase 10 entities: Camera for Home Assistant integration."""

        def get_camera_image() -> Optional[bytes]:
            """Get camera snapshot as JPEG bytes."""
            if self.camera_server:
                return self.camera_server.get_snapshot()
            return None

        entities.append(CameraEntity(
            server=self.server,
            key=get_entity_key("camera"),
            name="Camera",
            object_id="camera",
            icon="mdi:camera",
            image_getter=get_camera_image,
        ))

        _LOGGER.debug("Phase 10 entities registered: camera (ESPHome Camera entity)")

    def _setup_phase12_entities(self, entities: List) -> None:
        """Setup Phase 12 entities: Audio processing parameters (via local SDK)."""
        rc = self.reachy_controller

        entities.append(SwitchEntity(
            server=self.server,
            key=get_entity_key("agc_enabled"),
            name="AGC Enabled",
            object_id="agc_enabled",
            icon="mdi:tune-vertical",
            device_class="switch",
            entity_category=1,  # config
            value_getter=rc.get_agc_enabled,
            value_setter=rc.set_agc_enabled,
        ))

        entities.append(NumberEntity(
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
            value_setter=rc.set_agc_max_gain,
        ))

        entities.append(NumberEntity(
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
            value_setter=rc.set_noise_suppression,
        ))

        entities.append(BinarySensorEntity(
            server=self.server,
            key=get_entity_key("echo_cancellation_converged"),
            name="Echo Cancellation Converged",
            object_id="echo_cancellation_converged",
            icon="mdi:waveform",
            device_class="running",
            entity_category=2,  # diagnostic
            value_getter=rc.get_echo_cancellation_converged,
        ))

        _LOGGER.debug("Phase 12 entities registered: agc_enabled, agc_max_gain, noise_suppression, echo_cancellation_converged")

    def _setup_phase20_entities(self, entities: List) -> None:
        """Setup Phase 20 entities: Tap detection settings (Wireless only)."""
        from .tap_detector import TAP_THRESHOLD_G_MIN, TAP_THRESHOLD_G_MAX, TAP_THRESHOLD_G_DEFAULT

        def get_tap_sensitivity() -> float:
            """Get current tap sensitivity threshold in g."""
            if self.tap_detector:
                return self.tap_detector.threshold_g
            return TAP_THRESHOLD_G_DEFAULT

        def set_tap_sensitivity(value: float) -> None:
            """Set tap sensitivity threshold in g and save to preferences."""
            if self.tap_detector:
                self.tap_detector.threshold_g = value
                _LOGGER.info("Tap sensitivity set to %.2fg", value)
            # Save to preferences for persistence across restarts
            if self.state:
                self.state.preferences.tap_sensitivity = value
                self.state.save_preferences()
                _LOGGER.debug("Tap sensitivity saved to preferences")

        entities.append(NumberEntity(
            server=self.server,
            key=get_entity_key("tap_sensitivity"),
            name="Tap Sensitivity",
            object_id="tap_sensitivity",
            min_value=TAP_THRESHOLD_G_MIN,
            max_value=TAP_THRESHOLD_G_MAX,
            step=0.1,
            icon="mdi:gesture-tap",
            unit_of_measurement="g",
            mode=2,  # Slider mode
            entity_category=1,  # config
            value_getter=get_tap_sensitivity,
            value_setter=set_tap_sensitivity,
        ))

        _LOGGER.debug("Phase 20 entities registered: tap_sensitivity")

    def find_entity_references(self, entities: List) -> None:
        """Find and store references to special entities from existing list.

        Args:
            entities: The list of existing entities to search
        """
        # No special entity references needed after DOA removal
        pass
