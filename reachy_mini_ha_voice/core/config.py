"""Centralized configuration for Reachy Mini HA Voice.

This module provides a single source of truth for all configurable values,
organized by subsystem. Values can be overridden via environment variables
or a configuration file.

Usage:
    from core.config import Config

    # Access configuration
    port = Config.ESPHOME_PORT
    fps = Config.CAMERA_FPS

    # Or use grouped access
    camera_cfg = Config.camera
    fps = camera_cfg.fps
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable."""
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _env_float(key: str, default: float) -> float:
    """Get float from environment variable."""
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    """Get int from environment variable."""
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


@dataclass
class DaemonConfig:
    """Configuration for daemon monitoring."""

    url: str = "http://127.0.0.1:8000"
    check_interval_active: float = 2.0  # seconds
    check_interval_sleep: float = 8.0  # seconds
    check_interval_error: float = 6.0  # seconds
    max_backoff_interval: float = 15.0  # seconds
    backoff_multiplier: float = 1.5
    backoff_error_threshold: int = 2
    status_cache_ttl: float = 2.0  # seconds
    volume_cache_ttl: float = 3.0  # seconds


@dataclass
class ESPHomeConfig:
    """Configuration for ESPHome protocol server."""

    port: int = 6053
    device_name: str = "reachy-mini"
    friendly_name: str = "Reachy Mini"


@dataclass
class CameraConfig:
    """Configuration for camera and video streaming."""

    # HTTP server
    port: int = 8081

    # Frame capture
    fps_high: int = 25  # Active mode: smooth face tracking
    fps_low: int = 10  # Low power: periodic face check
    fps_idle: float = 5  # Ultra-low power: minimal CPU

    # JPEG encoding
    quality: int = 80

    # Face tracking
    face_tracking_enabled: bool = True
    face_confidence_threshold: float = 0.5  # Min confidence for face detection (0.3 too low, causes false positives)
    face_lost_delay: float = 2.0  # Wait before returning to neutral
    interpolation_duration: float = 1.0  # Time to return to neutral
    offset_scale: float = 0.6  # Face offset multiplier

    # Power management
    low_power_threshold: float = 5.0  # Seconds without face -> low power
    idle_threshold: float = 30.0  # Seconds without face -> idle

    # Gesture detection
    gesture_detection_enabled: bool = True
    gesture_detection_interval: int = 2  # Run every N frames


@dataclass
class MotionConfig:
    """Configuration for motion control."""

    # Control loop
    control_rate_hz: float = 100.0
    control_interval: float = 0.01  # 1 / control_rate_hz

    # Face tracking
    face_detected_threshold: float = 0.001  # Min offset to consider face detected

    # Idle behavior
    idle_look_around_min_interval: float = 8.0  # Min seconds between look-arounds
    idle_look_around_max_interval: float = 20.0  # Max seconds between look-arounds
    idle_inactivity_threshold: float = 5.0  # Seconds before look-around starts

    # Animation
    animation_fps: float = 30.0

    # Smoothing
    default_transition_duration: float = 0.3  # seconds
    body_yaw_max_rate_deg_s: float = 60.0  # Max body yaw speed when tracking
    body_yaw_deadband_rad: float = 0.003  # Ignore tiny yaw changes (~0.17°)
    body_yaw_min_send_interval_s: float = 0.05  # Min interval for yaw updates


@dataclass
class AudioConfig:
    """Configuration for audio processing."""

    # Audio format
    sample_rate: int = 16000
    channels: int = 1

    # Buffering
    block_size: int = 1024  # samples
    max_buffer_size: int = 10240  # samples (10 blocks)

    # Idle pacing
    idle_sleep_active: float = 0.01  # seconds
    idle_sleep_sleeping: float = 0.1  # seconds


@dataclass
class DOAConfig:
    """Configuration for Direction of Arrival (DOA) sound tracking."""

    # Enable/disable DOA tracking
    enabled: bool = True

    # Threshold settings
    energy_threshold: float = 0.3  # Min energy to consider sound significant
    angle_threshold_deg: float = 15.0  # Min angle change to trigger turn

    # Cooldown timing
    direction_cooldown: float = 5.0  # Seconds before responding to same direction
    min_turn_interval: float = 2.0  # Min seconds between any turns

    # Turn behavior
    turn_duration: float = 1.5  # Duration of turn animation
    max_turn_angle_deg: float = 60.0  # Maximum turn angle

    # Zone tracking
    num_zones: int = 8  # Number of direction zones for cooldown


@dataclass
class SleepConfig:
    """Configuration for sleep/wake management."""

    # Resume delay after wake
    resume_delay: float = 30.0  # seconds

    # Services to keep running during sleep
    keep_alive_services: list = field(
        default_factory=lambda: [
            "esphome_server",
            "entity_registry",
        ]
    )


@dataclass
class ShutdownConfig:
    """Configuration for shutdown behavior."""

    audio_thread_join_timeout: float = 1.0  # seconds
    camera_stop_timeout: float = 3.0  # seconds
    server_close_timeout: float = 3.0  # seconds
    sendspin_stop_timeout: float = 3.0  # seconds
    sleep_manager_stop_timeout: float = 3.0  # seconds


@dataclass
class RobotStateConfig:
    """Configuration for robot state monitoring."""

    check_interval_active: float = 3.0  # seconds
    check_interval_sleep: float = 8.0  # seconds
    check_interval_error: float = 6.0  # seconds


@dataclass
class APIConfig:
    """Configuration for the HTTP API server."""

    port: int = 8080
    host: str = "0.0.0.0"


class Config:
    """Centralized configuration access.

    All configuration values are accessible as class attributes.
    Grouped configs are available via nested dataclasses.
    """

    # Subsystem configurations
    daemon: DaemonConfig = DaemonConfig()
    esphome: ESPHomeConfig = ESPHomeConfig()
    camera: CameraConfig = CameraConfig()
    motion: MotionConfig = MotionConfig()
    audio: AudioConfig = AudioConfig()
    doa: DOAConfig = DOAConfig()
    sleep: SleepConfig = SleepConfig()
    robot_state: RobotStateConfig = RobotStateConfig()
    shutdown: ShutdownConfig = ShutdownConfig()
    api: APIConfig = APIConfig()

    _initialized = False
    _config_file: Path | None = None

    @classmethod
    def load_from_file(cls, path: Path) -> None:
        """Load configuration overrides from a JSON file.

        Args:
            path: Path to the JSON configuration file
        """
        if not path.exists():
            logger.debug(f"Config file not found: {path}")
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            cls._apply_overrides(data)
            cls._config_file = path
            logger.info(f"Loaded configuration from {path}")
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")

    @classmethod
    def load_from_env(cls) -> None:
        """Load configuration overrides from environment variables.

        Environment variables follow the pattern: REACHY_<SECTION>_<KEY>
        Example: REACHY_CAMERA_FPS=30
        """
        # Daemon
        cls.daemon.url = os.environ.get("REACHY_DAEMON_URL", cls.daemon.url)
        cls.daemon.check_interval_active = _env_float(
            "REACHY_DAEMON_CHECK_INTERVAL_ACTIVE", cls.daemon.check_interval_active
        )
        cls.daemon.check_interval_sleep = _env_float(
            "REACHY_DAEMON_CHECK_INTERVAL_SLEEP", cls.daemon.check_interval_sleep
        )
        cls.daemon.check_interval_error = _env_float(
            "REACHY_DAEMON_CHECK_INTERVAL_ERROR", cls.daemon.check_interval_error
        )
        cls.daemon.max_backoff_interval = _env_float(
            "REACHY_DAEMON_MAX_BACKOFF_INTERVAL", cls.daemon.max_backoff_interval
        )
        cls.daemon.backoff_multiplier = _env_float("REACHY_DAEMON_BACKOFF_MULTIPLIER", cls.daemon.backoff_multiplier)
        cls.daemon.backoff_error_threshold = _env_int(
            "REACHY_DAEMON_BACKOFF_ERROR_THRESHOLD", cls.daemon.backoff_error_threshold
        )
        cls.daemon.status_cache_ttl = _env_float("REACHY_DAEMON_STATUS_CACHE_TTL", cls.daemon.status_cache_ttl)
        cls.daemon.volume_cache_ttl = _env_float("REACHY_DAEMON_VOLUME_CACHE_TTL", cls.daemon.volume_cache_ttl)

        # ESPHome
        cls.esphome.port = _env_int("REACHY_ESPHOME_PORT", cls.esphome.port)
        cls.esphome.device_name = os.environ.get("REACHY_ESPHOME_DEVICE_NAME", cls.esphome.device_name)

        # Camera
        cls.camera.port = _env_int("REACHY_CAMERA_PORT", cls.camera.port)
        cls.camera.fps_high = _env_int("REACHY_CAMERA_FPS", cls.camera.fps_high)
        cls.camera.quality = _env_int("REACHY_CAMERA_QUALITY", cls.camera.quality)

        # Motion
        cls.motion.control_rate_hz = _env_float("REACHY_MOTION_CONTROL_RATE", cls.motion.control_rate_hz)

        # Audio
        cls.audio.idle_sleep_active = _env_float("REACHY_AUDIO_IDLE_SLEEP_ACTIVE", cls.audio.idle_sleep_active)
        cls.audio.idle_sleep_sleeping = _env_float("REACHY_AUDIO_IDLE_SLEEP_SLEEPING", cls.audio.idle_sleep_sleeping)

        # Sleep
        cls.sleep.resume_delay = _env_float("REACHY_SLEEP_RESUME_DELAY", cls.sleep.resume_delay)

        # Robot state
        cls.robot_state.check_interval_active = _env_float(
            "REACHY_ROBOT_STATE_CHECK_INTERVAL_ACTIVE", cls.robot_state.check_interval_active
        )
        cls.robot_state.check_interval_sleep = _env_float(
            "REACHY_ROBOT_STATE_CHECK_INTERVAL_SLEEP", cls.robot_state.check_interval_sleep
        )
        cls.robot_state.check_interval_error = _env_float(
            "REACHY_ROBOT_STATE_CHECK_INTERVAL_ERROR", cls.robot_state.check_interval_error
        )

        logger.debug("Loaded configuration from environment")

    @classmethod
    def _apply_overrides(cls, data: dict) -> None:
        """Apply configuration overrides from a dictionary."""
        if "daemon" in data:
            for key, value in data["daemon"].items():
                if hasattr(cls.daemon, key):
                    setattr(cls.daemon, key, value)

        if "esphome" in data:
            for key, value in data["esphome"].items():
                if hasattr(cls.esphome, key):
                    setattr(cls.esphome, key, value)

        if "camera" in data:
            for key, value in data["camera"].items():
                if hasattr(cls.camera, key):
                    setattr(cls.camera, key, value)

        if "motion" in data:
            for key, value in data["motion"].items():
                if hasattr(cls.motion, key):
                    setattr(cls.motion, key, value)

        if "audio" in data:
            for key, value in data["audio"].items():
                if hasattr(cls.audio, key):
                    setattr(cls.audio, key, value)

        if "doa" in data:
            for key, value in data["doa"].items():
                if hasattr(cls.doa, key):
                    setattr(cls.doa, key, value)

        if "sleep" in data:
            for key, value in data["sleep"].items():
                if hasattr(cls.sleep, key):
                    setattr(cls.sleep, key, value)

        if "robot_state" in data:
            for key, value in data["robot_state"].items():
                if hasattr(cls.robot_state, key):
                    setattr(cls.robot_state, key, value)

        if "api" in data:
            for key, value in data["api"].items():
                if hasattr(cls.api, key):
                    setattr(cls.api, key, value)

    @classmethod
    def initialize(cls, config_file: Path | None = None) -> None:
        """Initialize configuration.

        Loads from config file if provided, then applies environment overrides.

        Args:
            config_file: Optional path to JSON configuration file
        """
        if cls._initialized:
            return

        if config_file:
            cls.load_from_file(config_file)

        cls.load_from_env()
        cls._initialized = True

    @classmethod
    def to_dict(cls) -> dict:
        """Export current configuration as a dictionary."""
        return {
            "daemon": {
                "url": cls.daemon.url,
                "check_interval_active": cls.daemon.check_interval_active,
                "check_interval_sleep": cls.daemon.check_interval_sleep,
                "check_interval_error": cls.daemon.check_interval_error,
                "max_backoff_interval": cls.daemon.max_backoff_interval,
                "backoff_multiplier": cls.daemon.backoff_multiplier,
                "backoff_error_threshold": cls.daemon.backoff_error_threshold,
                "status_cache_ttl": cls.daemon.status_cache_ttl,
                "volume_cache_ttl": cls.daemon.volume_cache_ttl,
            },
            "esphome": {
                "port": cls.esphome.port,
                "device_name": cls.esphome.device_name,
                "friendly_name": cls.esphome.friendly_name,
            },
            "camera": {
                "port": cls.camera.port,
                "fps_high": cls.camera.fps_high,
                "fps_low": cls.camera.fps_low,
                "fps_idle": cls.camera.fps_idle,
                "quality": cls.camera.quality,
                "face_tracking_enabled": cls.camera.face_tracking_enabled,
                "gesture_detection_enabled": cls.camera.gesture_detection_enabled,
            },
            "motion": {
                "control_rate_hz": cls.motion.control_rate_hz,
                "animation_fps": cls.motion.animation_fps,
            },
            "audio": {
                "sample_rate": cls.audio.sample_rate,
                "block_size": cls.audio.block_size,
                "idle_sleep_active": cls.audio.idle_sleep_active,
                "idle_sleep_sleeping": cls.audio.idle_sleep_sleeping,
            },
            "doa": {
                "enabled": cls.doa.enabled,
                "energy_threshold": cls.doa.energy_threshold,
                "angle_threshold_deg": cls.doa.angle_threshold_deg,
                "direction_cooldown": cls.doa.direction_cooldown,
                "min_turn_interval": cls.doa.min_turn_interval,
                "turn_duration": cls.doa.turn_duration,
                "max_turn_angle_deg": cls.doa.max_turn_angle_deg,
                "num_zones": cls.doa.num_zones,
            },
            "sleep": {
                "resume_delay": cls.sleep.resume_delay,
                "keep_alive_services": cls.sleep.keep_alive_services,
            },
            "robot_state": {
                "check_interval_active": cls.robot_state.check_interval_active,
                "check_interval_sleep": cls.robot_state.check_interval_sleep,
                "check_interval_error": cls.robot_state.check_interval_error,
            },
            "api": {
                "port": cls.api.port,
                "host": cls.api.host,
            },
        }
