"""Reachy Mini controller wrapper for ESPHome entities."""

import logging
import math
import time
from typing import TYPE_CHECKING, Any

import numpy as np
import requests
from scipy.spatial.transform import Rotation as R

from .audio.microphone import MicrophoneOptimizer, MicrophonePreferences
from .core.config import Config

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)


class _ReSpeakerContext:
    """Context manager for thread-safe ReSpeaker access."""

    def __init__(self, respeaker, lock):
        self._respeaker = respeaker
        self._lock = lock

    def __enter__(self):
        self._lock.acquire()
        return self._respeaker

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False


class ReachyController:
    """
    Wrapper class for Reachy Mini control operations.

    Provides safe access to Reachy Mini SDK functions with error handling.
    """

    def __init__(self, reachy_mini: "ReachyMini"):
        """
        Initialize the controller.

        Args:
            reachy_mini: ReachyMini instance (required)
        """
        self.reachy = reachy_mini
        self._speaker_volume = 100  # Default volume
        self._microphone_volume = 50.0  # Default mic volume
        self._movement_manager = None  # Set later via set_movement_manager()

        # Volume caching to reduce daemon HTTP load
        self._volume_cache_ttl = Config.daemon.volume_cache_ttl  # seconds
        self._speaker_volume_cache_ts = 0.0
        self._microphone_volume_cache_ts = 0.0

        # Shared session to reduce per-request overhead
        self._http_session = requests.Session()
        self._http_timeout = 5.0  # seconds
        self._cache_ttl = Config.daemon.status_cache_ttl
        self._daemon_base_url = "http://127.0.0.1:8000"

        # Callback for sleep/wake to notify VoiceAssistant
        self._on_sleep_callback = None
        self._on_wake_callback = None

        # Status caching - only for get_status() which may trigger I/O
        # Note: get_current_head_pose() and get_current_joint_positions() are
        # non-blocking in the SDK (they return cached Zenoh data), so no caching needed
        self._state_cache: dict[str, Any] = {}
        self._last_status_query = 0.0

        # Thread lock for ReSpeaker USB access to prevent conflicts with GStreamer audio pipeline
        self._respeaker_lock = __import__("threading").Lock()

    def set_sleep_callback(self, callback) -> None:
        """Set callback to be called when go_to_sleep is triggered."""
        self._on_sleep_callback = callback

    def set_wake_callback(self, callback) -> None:
        """Set callback to be called when wake_up is triggered."""
        self._on_wake_callback = callback

    def set_movement_manager(self, movement_manager) -> None:
        """Set the MovementManager instance for pose control.

        Args:
            movement_manager: MovementManager instance
        """
        self._movement_manager = movement_manager
        logger.info("MovementManager set for ReachyController")

    @property
    def is_available(self) -> bool:
        """Check if robot is available."""
        return self.reachy is not None

    def get_idle_motion_enabled(self) -> bool:
        """Get whether idle look-around behavior is enabled."""
        if self._movement_manager is None:
            return False
        try:
            return bool(self._movement_manager.get_idle_motion_enabled())
        except Exception as e:
            logger.debug("Error getting idle motion state: %s", e)
            return False

    def get_idle_behavior_enabled(self) -> bool:
        """Get whether any idle behavior subsystem is enabled."""
        if self._movement_manager is None:
            return False
        try:
            return bool(self._movement_manager.get_idle_behavior_enabled())
        except Exception as e:
            logger.debug("Error getting idle behavior state: %s", e)
            return False

    def set_idle_behavior_enabled(self, enabled: bool) -> None:
        """Enable or disable all idle behavior subsystems together."""
        if self._movement_manager is None:
            logger.warning("set_idle_behavior_enabled failed - MovementManager not set")
            return
        self._movement_manager.set_idle_behavior_enabled(enabled)

    def set_idle_motion_enabled(self, enabled: bool) -> None:
        """Enable or disable idle look-around behavior."""
        if self._movement_manager is None:
            logger.warning("set_idle_motion_enabled failed - MovementManager not set")
            return
        self._movement_manager.set_idle_motion_enabled(enabled)

    def get_idle_antenna_enabled(self) -> bool:
        """Get whether idle antenna animation is enabled."""
        if self._movement_manager is None:
            return False
        try:
            return bool(self._movement_manager.get_idle_antenna_enabled())
        except Exception as e:
            logger.debug("Error getting idle antenna state: %s", e)
            return False

    def set_idle_antenna_enabled(self, enabled: bool) -> None:
        """Enable or disable idle antenna animation."""
        if self._movement_manager is None:
            logger.warning("set_idle_antenna_enabled failed - MovementManager not set")
            return
        self._movement_manager.set_idle_antenna_enabled(enabled)

    def get_idle_random_actions_enabled(self) -> bool:
        """Get whether idle random actions are enabled."""
        if self._movement_manager is None:
            return False
        try:
            return bool(self._movement_manager.get_idle_random_actions_enabled())
        except Exception as e:
            logger.debug("Error getting idle random actions state: %s", e)
            return False

    def set_idle_random_actions_enabled(self, enabled: bool) -> None:
        """Enable or disable idle random actions (no audio)."""
        if self._movement_manager is None:
            logger.warning("set_idle_random_actions_enabled failed - MovementManager not set")
            return
        self._movement_manager.set_idle_random_actions_enabled(enabled)

    # ========== Phase 1: Basic Status & Volume ==========

    @staticmethod
    def _status_value(status: Any, key: str, default: Any = None) -> Any:
        if status is None:
            return default
        if isinstance(status, dict):
            return status.get(key, default)
        return getattr(status, key, default)

    @classmethod
    def _nested_status_value(cls, status: Any, parent_key: str, child_key: str, default: Any = None) -> Any:
        parent = cls._status_value(status, parent_key, None)
        if parent is None:
            return default
        if isinstance(parent, dict):
            return parent.get(child_key, default)
        return getattr(parent, child_key, default)

    def _get_cached_status(self) -> Any:
        """Get cached daemon status to reduce query frequency.

        Note: get_status() may trigger I/O, so we cache it.
        Unlike get_current_head_pose() and get_current_joint_positions()
        which are non-blocking in the SDK.
        """
        now = time.time()
        if now - self._last_status_query < self._cache_ttl:
            return self._state_cache.get("status")

        if not self.is_available:
            return None

        try:
            status = self.reachy.client.get_status(wait=False)
            self._state_cache["status"] = status
            self._last_status_query = now
            return status
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return self._state_cache.get("status")  # Return stale cache on error

    def get_daemon_state(self) -> str:
        """Get daemon state with caching."""
        status = self._get_cached_status()
        if status is None:
            return "not_available"
        return str(self._status_value(status, "state", "unknown"))

    def get_backend_ready(self) -> bool:
        """Check if backend is ready with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return self._status_value(status, "state") == "running"

    def get_error_message(self) -> str:
        """Get current error message with caching."""
        status = self._get_cached_status()
        if status is None:
            return "Robot not available"
        return str(self._status_value(status, "error", "") or "")

    def _get_volume_via_api(self, path: str, cached_value: float, label: str) -> float:
        """Fetch a volume value from the daemon API, falling back to the cached value."""
        try:
            resp = self._http_session.get(
                f"{self._daemon_base_url}{path}",
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "volume" in data:
                return float(data["volume"])
        except Exception as e:
            logger.warning("Failed to get %s volume via daemon API: %s", label, e)

        return cached_value

    def _set_volume_via_api(self, path: str, volume: float, label: str) -> float:
        """Write a volume value through the daemon API and return the confirmed level."""
        try:
            resp = self._http_session.post(
                f"{self._daemon_base_url}{path}",
                json={"volume": int(volume)},
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "volume" in data:
                return float(data["volume"])
            return volume
        except Exception as e:
            logger.error("Failed to set %s volume via daemon API: %s", label, e)
            return volume

    def get_speaker_volume(self) -> float:
        """Get speaker volume (0-100) from the daemon volume API."""
        self._speaker_volume = self._get_volume_via_api("/api/volume/current", self._speaker_volume, "speaker")
        return self._speaker_volume

    def set_speaker_volume(self, volume: float) -> None:
        """Set speaker volume (0-100) through the daemon volume API."""
        volume = max(0.0, min(100.0, volume))
        self._speaker_volume = self._set_volume_via_api("/api/volume/set", volume, "speaker")
        logger.info("Speaker volume set to %.1f%% via daemon API", self._speaker_volume)

    def get_microphone_volume(self) -> float:
        """Get microphone volume (0-100), preferring daemon volume API."""
        self._microphone_volume = self._get_volume_via_api(
            "/api/volume/microphone/current",
            self._microphone_volume,
            "microphone",
        )
        return self._microphone_volume

    def set_microphone_volume(self, volume: float) -> None:
        """
        Set microphone volume (0-100), preferring daemon volume API.

        Args:
            volume: Volume level 0-100
        """
        volume = max(0.0, min(100.0, volume))
        self._microphone_volume = self._set_volume_via_api(
            "/api/volume/microphone/set",
            volume,
            "microphone",
        )
        logger.info("Microphone volume set to %.1f%% via daemon API", self._microphone_volume)

    # ========== Phase 2: Motor Control ==========

    def get_motors_enabled(self) -> bool:
        """Check if motors are enabled with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        try:
            motor_mode = self._nested_status_value(status, "backend_status", "motor_control_mode", None)
            if motor_mode is not None:
                return motor_mode == "enabled"
            return self._status_value(status, "state") == "running"
        except Exception as e:
            logger.error(f"Error getting motor state: {e}")
            return False

    def set_motors_enabled(self, enabled: bool) -> None:
        """
        Enable or disable motors.

        Args:
            enabled: True to enable, False to disable
        """
        if not self.is_available:
            logger.warning("Cannot control motors: robot not available")
            return

        try:
            if enabled:
                self.reachy.enable_motors()
                logger.info("Motors enabled")
            else:
                self.reachy.disable_motors()
                logger.info("Motors disabled")
        except Exception as e:
            logger.error(f"Error setting motor state: {e}")

    def get_motor_mode(self) -> str:
        """Get current motor control mode with caching."""
        status = self._get_cached_status()
        if status is None:
            return "disabled"
        try:
            motor_mode = self._nested_status_value(status, "backend_status", "motor_control_mode", None)
            if motor_mode is not None:
                return str(motor_mode)
            if self._status_value(status, "state") == "running":
                return "enabled"
            return "disabled"
        except Exception as e:
            logger.error(f"Error getting motor mode: {e}")
            return "error"

    def set_motor_mode(self, mode: str) -> None:
        """
        Set motor control mode.

        Args:
            mode: One of "enabled", "disabled", "gravity_compensation"
        """
        if not self.is_available:
            logger.warning("Cannot set motor mode: robot not available")
            return

        try:
            if mode == "enabled":
                self.reachy.enable_motors()
            elif mode == "disabled":
                self.reachy.disable_motors()
            elif mode == "gravity_compensation":
                self.reachy.enable_gravity_compensation()
            else:
                logger.warning(f"Invalid motor mode: {mode}")
                return
            logger.info(f"Motor mode set to {mode}")
        except Exception as e:
            logger.error(f"Error setting motor mode: {e}")

    def wake_up(self) -> None:
        """Execute wake up animation."""
        if not self.is_available:
            logger.warning("Cannot wake up: robot not available")
            return

        try:
            # SDK v1.5 sleep/wake is managed at daemon level.
            # Start daemon with wake_up=true so /api/daemon/status reflects awake state.
            self._daemon_command("/api/daemon/start", params={"wake_up": "true"})
            logger.info("Wake-up requested via daemon API")

            # Invalidate cached status after transition request
            self._last_status_query = 0.0

            # Notify callback (VoiceAssistant will resume services)
            if self._on_wake_callback is not None:
                try:
                    self._on_wake_callback()
                except Exception as e:
                    logger.error(f"Error in wake callback: {e}")
        except Exception as e:
            logger.error(f"Error executing wake up: {e}")

    def go_to_sleep(self) -> None:
        """Execute sleep animation.

        The order is important:
        1. First suspend all services via callback (so they release robot resources)
        2. Then send the robot to sleep

        This prevents errors from services trying to access a sleeping robot.
        """
        if not self.is_available:
            logger.warning("Cannot sleep: robot not available")
            return

        try:
            # First, notify callback to suspend all services
            # This must happen BEFORE the robot goes to sleep
            logger.info("Suspending services before sleep...")
            if self._on_sleep_callback is not None:
                try:
                    self._on_sleep_callback()
                except Exception as e:
                    logger.error(f"Error in sleep callback: {e}")

            # Give services time to fully suspend
            time.sleep(0.5)

            # SDK v1.5 sleep/wake is managed at daemon level.
            # Stop daemon with goto_sleep=true so /api/daemon/status reflects sleep state.
            self._daemon_command("/api/daemon/stop", params={"goto_sleep": "true"})
            logger.info("Sleep requested via daemon API")

            # Invalidate cached status after transition request
            self._last_status_query = 0.0

        except Exception as e:
            logger.error(f"Error executing sleep: {e}")

    def _daemon_command(self, path: str, params: dict[str, str] | None = None) -> None:
        """Send a daemon command request and wait for the daemon state to settle."""
        url = f"{self._daemon_base_url}{path}"
        resp = self._http_session.post(url, params=params or {}, timeout=self._http_timeout)
        resp.raise_for_status()

        desired_state = None
        if path.endswith("/start"):
            desired_state = "running"
        elif path.endswith("/stop"):
            desired_state = "stopped"

        if desired_state is not None:
            self._wait_for_daemon_state(desired_state)

    def _wait_for_daemon_state(self, desired_state: str, timeout: float = 10.0) -> None:
        """Poll daemon status until the requested state is reached."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = self._http_session.get(
                    f"{self._daemon_base_url}/api/daemon/status",
                    timeout=self._http_timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                current_state = str(data.get("state", "")).lower()
                if current_state == desired_state:
                    self._last_status_query = 0.0
                    return
            except Exception as e:
                logger.debug("Waiting for daemon state %s failed: %s", desired_state, e)
            time.sleep(0.2)

        logger.warning("Timed out waiting for daemon state '%s'", desired_state)

    # ========== Phase 3: Pose Control ==========

    def _get_head_pose(self) -> np.ndarray | None:
        """Get current head pose from SDK.

        Note: SDK's get_current_head_pose() is non-blocking - it returns
        cached data from Zenoh subscriptions, so no throttling needed.
        """
        if not self.is_available:
            return None

        try:
            return self.reachy.get_current_head_pose()
        except Exception as e:
            logger.error(f"Error getting head pose: {e}")
            return None

    def _get_joint_positions(self) -> tuple | None:
        """Get current joint positions from SDK.

        Note: SDK's get_current_joint_positions() is non-blocking - it returns
        cached data from Zenoh subscriptions, so no throttling needed.
        """
        if not self.is_available:
            return None

        try:
            return self.reachy.get_current_joint_positions()
        except Exception as e:
            logger.error(f"Error getting joint positions: {e}")
            return None

    def _extract_pose_from_matrix(self, pose_matrix: np.ndarray) -> tuple:
        """
        Extract position (x, y, z) and rotation (roll, pitch, yaw) from 4x4 pose matrix.

        Args:
            pose_matrix: 4x4 homogeneous transformation matrix

        Returns:
            tuple: (x, y, z, roll, pitch, yaw) where position is in meters and angles in radians
        """
        # Extract position from the last column
        x = pose_matrix[0, 3]
        y = pose_matrix[1, 3]
        z = pose_matrix[2, 3]

        # Extract rotation matrix and convert to euler angles
        rotation_matrix = pose_matrix[:3, :3]
        rotation = R.from_matrix(rotation_matrix)
        # Use 'xyz' convention for roll, pitch, yaw
        roll, pitch, yaw = rotation.as_euler("xyz")

        return x, y, z, roll, pitch, yaw

    def _get_head_pose_component(self, component: str) -> float:
        """Get a specific component from head pose.

        Args:
            component: One of 'x', 'y', 'z' (mm), 'roll', 'pitch', 'yaw' (degrees)

        Returns:
            The component value, or 0.0 on error
        """
        pose = self._get_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            components = {
                "x": x * 1000,  # m to mm
                "y": y * 1000,
                "z": z * 1000,
                "roll": math.degrees(roll),
                "pitch": math.degrees(pitch),
                "yaw": math.degrees(yaw),
            }
            return components.get(component, 0.0)
        except Exception as e:
            logger.error(f"Error getting head {component}: {e}")
            return 0.0

    def _disabled_pose_setter(self, name: str) -> None:
        """Log warning when MovementManager is not available."""
        logger.warning(f"set_{name} failed - MovementManager not set")

    def _set_pose_via_manager(self, **kwargs) -> bool:
        """Set pose via MovementManager if available.

        Returns True if successful, False if MovementManager not available.
        """
        if self._movement_manager is None:
            return False
        self._movement_manager.set_target_pose(**kwargs)
        return True

    # Head position getters and setters
    def get_head_x(self) -> float:
        """Get head X position in mm."""
        return self._get_head_pose_component("x")

    def set_head_x(self, x_mm: float) -> None:
        """Set head X position in mm via MovementManager."""
        if not self._set_pose_via_manager(x=x_mm / 1000.0):  # mm to m
            self._disabled_pose_setter("head_x")

    def get_head_y(self) -> float:
        """Get head Y position in mm."""
        return self._get_head_pose_component("y")

    def set_head_y(self, y_mm: float) -> None:
        """Set head Y position in mm via MovementManager."""
        if not self._set_pose_via_manager(y=y_mm / 1000.0):  # mm to m
            self._disabled_pose_setter("head_y")

    def get_head_z(self) -> float:
        """Get head Z position in mm."""
        return self._get_head_pose_component("z")

    def set_head_z(self, z_mm: float) -> None:
        """Set head Z position in mm via MovementManager."""
        if not self._set_pose_via_manager(z=z_mm / 1000.0):  # mm to m
            self._disabled_pose_setter("head_z")

    # Head orientation getters and setters
    def get_head_roll(self) -> float:
        """Get head roll angle in degrees."""
        return self._get_head_pose_component("roll")

    def set_head_roll(self, roll_deg: float) -> None:
        """Set head roll angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(roll=math.radians(roll_deg)):
            self._disabled_pose_setter("head_roll")

    def get_head_pitch(self) -> float:
        """Get head pitch angle in degrees."""
        return self._get_head_pose_component("pitch")

    def set_head_pitch(self, pitch_deg: float) -> None:
        """Set head pitch angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(pitch=math.radians(pitch_deg)):
            self._disabled_pose_setter("head_pitch")

    def get_head_yaw(self) -> float:
        """Get head yaw angle in degrees."""
        return self._get_head_pose_component("yaw")

    def set_head_yaw(self, yaw_deg: float) -> None:
        """Set head yaw angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(yaw=math.radians(yaw_deg)):
            self._disabled_pose_setter("head_yaw")

    def get_body_yaw(self) -> float:
        """Get body yaw angle in degrees."""
        joints = self._get_joint_positions()
        if joints is None:
            return 0.0
        try:
            head_joints, _ = joints
            return math.degrees(head_joints[0])
        except Exception as e:
            logger.error(f"Error getting body yaw: {e}")
            return 0.0

    def set_body_yaw(self, yaw_deg: float) -> None:
        """Set body yaw angle in degrees.

        Note: This directly calls SDK's set_target_body_yaw since automatic body yaw
        is enabled. Manual control will temporarily override automatic mode.
        """
        if self.reachy is None:
            self._disabled_pose_setter("body_yaw")
            return
        try:
            self.reachy.set_target_body_yaw(math.radians(yaw_deg))
        except Exception as e:
            logger.error(f"Error setting body yaw: {e}")

    def get_antenna_left(self) -> float:
        """Get left antenna angle in degrees."""
        joints = self._get_joint_positions()
        if joints is None:
            return 0.0
        try:
            _, antennas = joints
            return math.degrees(antennas[1])  # left is index 1
        except Exception as e:
            logger.error(f"Error getting left antenna: {e}")
            return 0.0

    def set_antenna_left(self, angle_deg: float) -> None:
        """Set left antenna angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(antenna_left=math.radians(angle_deg)):
            self._disabled_pose_setter("antenna_left")

    def get_antenna_right(self) -> float:
        """Get right antenna angle in degrees."""
        joints = self._get_joint_positions()
        if joints is None:
            return 0.0
        try:
            _, antennas = joints
            return math.degrees(antennas[0])  # right is index 0
        except Exception as e:
            logger.error(f"Error getting right antenna: {e}")
            return 0.0

    def set_antenna_right(self, angle_deg: float) -> None:
        """Set right antenna angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(antenna_right=math.radians(angle_deg)):
            self._disabled_pose_setter("antenna_right")

    # ========== Phase 4: Look At Control ==========

    def get_look_at_x(self) -> float:
        """Get look at target X coordinate in world frame (meters)."""
        # This is a target position, not a current state
        # We'll store it internally
        return getattr(self, "_look_at_x", 0.0)

    def set_look_at_x(self, x: float) -> None:
        """Set look at target X coordinate."""
        self._look_at_x = x
        self._update_look_at()

    def get_look_at_y(self) -> float:
        """Get look at target Y coordinate in world frame (meters)."""
        return getattr(self, "_look_at_y", 0.0)

    def set_look_at_y(self, y: float) -> None:
        """Set look at target Y coordinate."""
        self._look_at_y = y
        self._update_look_at()

    def get_look_at_z(self) -> float:
        """Get look at target Z coordinate in world frame (meters)."""
        return getattr(self, "_look_at_z", 0.0)

    def set_look_at_z(self, z: float) -> None:
        """Set look at target Z coordinate."""
        self._look_at_z = z
        self._update_look_at()

    def _update_look_at(self) -> None:
        """Update robot to look at the target coordinates.

        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("_update_look_at is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     x = getattr(self, '_look_at_x', 0.0)
        #     y = getattr(self, '_look_at_y', 0.0)
        #     z = getattr(self, '_look_at_z', 0.0)
        #     self.reachy.look_at_world(x, y, z)
        #     logger.info(f"Looking at world coordinates: ({x}, {y}, {z})")
        # except Exception as e:
        #     logger.error(f"Error updating look at: {e}")

    # ========== Phase 6: Diagnostic Information ==========

    def get_control_loop_frequency(self) -> float:
        """Get control loop frequency in Hz with caching."""
        status = self._get_cached_status()
        if status is None:
            return 0.0
        try:
            control_loop_stats = self._nested_status_value(status, "backend_status", "control_loop_stats", None)
            if isinstance(control_loop_stats, dict):
                return float(control_loop_stats.get("mean_control_loop_frequency", 0.0))
            if control_loop_stats is not None:
                return float(getattr(control_loop_stats, "mean_control_loop_frequency", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"Error getting control loop frequency: {e}")
            return 0.0

    def get_sdk_version(self) -> str:
        """Get SDK version with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return str(self._status_value(status, "version", "unknown") or "unknown")

    def get_robot_name(self) -> str:
        """Get robot name with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return str(self._status_value(status, "robot_name", "unknown") or "unknown")

    def get_wireless_version(self) -> bool:
        """Check if this is a wireless version with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return bool(self._status_value(status, "wireless_version", False))

    def get_simulation_mode(self) -> bool:
        """Check if simulation mode is enabled with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return bool(self._status_value(status, "simulation_enabled", False))

    def get_wlan_ip(self) -> str:
        """Get WLAN IP address with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return str(self._status_value(status, "wlan_ip", "N/A") or "N/A")

    # ========== Phase 7: IMU Sensors (Wireless only) ==========

    def _get_imu_value(self, sensor_type: str, index: int) -> float:
        """Get a specific IMU sensor value.

        Args:
            sensor_type: 'accelerometer', 'gyroscope', or 'temperature'
            index: Array index (0=x, 1=y, 2=z) or -1 for scalar values

        Returns:
            The sensor value, or 0.0 on error
        """
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is None or sensor_type not in imu_data:
                return 0.0
            value = imu_data[sensor_type]
            return float(value[index]) if index >= 0 else float(value)
        except Exception as e:
            logger.debug(f"Error getting IMU {sensor_type}: {e}")
            return 0.0

    def get_imu_accel_x(self) -> float:
        """Get IMU X-axis acceleration in m/s²."""
        return self._get_imu_value("accelerometer", 0)

    def get_imu_accel_y(self) -> float:
        """Get IMU Y-axis acceleration in m/s²."""
        return self._get_imu_value("accelerometer", 1)

    def get_imu_accel_z(self) -> float:
        """Get IMU Z-axis acceleration in m/s²."""
        return self._get_imu_value("accelerometer", 2)

    def get_imu_gyro_x(self) -> float:
        """Get IMU X-axis angular velocity in rad/s."""
        return self._get_imu_value("gyroscope", 0)

    def get_imu_gyro_y(self) -> float:
        """Get IMU Y-axis angular velocity in rad/s."""
        return self._get_imu_value("gyroscope", 1)

    def get_imu_gyro_z(self) -> float:
        """Get IMU Z-axis angular velocity in rad/s."""
        return self._get_imu_value("gyroscope", 2)

    def get_imu_temperature(self) -> float:
        """Get IMU temperature in °C."""
        return self._get_imu_value("temperature", -1)

    # ========== Phase 11: LED Control (DISABLED) ==========
    # LED control is disabled because LEDs are hidden inside the robot.
    # See PROJECT_PLAN.md principle 8.

    def _get_respeaker(self):
        """Get ReSpeaker device from media manager with thread-safe access.

        Returns a context manager that holds the lock during ReSpeaker operations.
        Usage:
            with self._get_respeaker() as respeaker:
                if respeaker:
                    respeaker.read("...")

        Note: This accesses the private _respeaker attribute from the SDK.
        TODO: Check if SDK provides a public API for ReSpeaker access in future versions.
        This is a known compatibility risk and should be reviewed on SDK updates.
        """
        if not self.is_available:
            return _ReSpeakerContext(None, self._respeaker_lock)
        try:
            if not self.reachy.media or not self.reachy.media.audio:
                return _ReSpeakerContext(None, self._respeaker_lock)
            # WARNING: Accessing private attribute _respeaker
            # TODO: Replace with public API when available
            respeaker = self.reachy.media.audio._respeaker
            return _ReSpeakerContext(respeaker, self._respeaker_lock)
        except Exception:
            return _ReSpeakerContext(None, self._respeaker_lock)

    def optimize_microphone_settings(self, preferences: MicrophonePreferences) -> None:
        """Apply microphone optimization through the centralized ReSpeaker adapter."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                logger.debug("ReSpeaker not available for optimization")
                return
            optimizer = MicrophoneOptimizer()
            optimizer.optimize(respeaker, preferences)

    # ========== Phase 12: Audio Processing (via local SDK with thread-safe access) ==========

    def get_agc_enabled(self) -> bool:
        """Get AGC (Automatic Gain Control) enabled status."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, "_agc_enabled", True)  # Default to enabled
            try:
                result = respeaker.read("PP_AGCONOFF")
                if result is not None:
                    self._agc_enabled = bool(result[1])
                    return self._agc_enabled
            except Exception as e:
                logger.debug(f"Error getting AGC status: {e}")
        return getattr(self, "_agc_enabled", True)

    def set_agc_enabled(self, enabled: bool) -> None:
        """Set AGC (Automatic Gain Control) enabled status."""
        self._agc_enabled = enabled
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return
            try:
                respeaker.write("PP_AGCONOFF", [1 if enabled else 0])
                logger.info(f"AGC {'enabled' if enabled else 'disabled'}")
            except Exception as e:
                logger.error(f"Error setting AGC status: {e}")

    def get_agc_max_gain(self) -> float:
        """Get AGC maximum gain in dB (0-40 dB range)."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, "_agc_max_gain", 30.0)  # Default matches MicrophoneDefaults
            try:
                result = respeaker.read("PP_AGCMAXGAIN")
                if result is not None:
                    self._agc_max_gain = float(result[0])
                    return self._agc_max_gain
            except Exception as e:
                logger.debug(f"Error getting AGC max gain: {e}")
        return getattr(self, "_agc_max_gain", 30.0)

    def set_agc_max_gain(self, gain: float) -> None:
        """Set AGC maximum gain in dB (0-40 dB range)."""
        gain = max(0.0, min(40.0, gain))  # XVF3800 supports up to 40dB
        self._agc_max_gain = gain
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return
            try:
                respeaker.write("PP_AGCMAXGAIN", [gain])
                logger.info(f"AGC max gain set to {gain} dB")
            except Exception as e:
                logger.error(f"Error setting AGC max gain: {e}")

    def get_noise_suppression(self) -> float:
        """Get noise suppression level (0-100%).

        PP_MIN_NS represents "minimum signal preservation ratio":
        - PP_MIN_NS = 0.85 means "keep at least 85% of signal" = 15% suppression
        - PP_MIN_NS = 0.15 means "keep at least 15% of signal" = 85% suppression

        We display "noise suppression strength" to user, so:
        - suppression_percent = (1.0 - PP_MIN_NS) * 100
        """
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, "_noise_suppression", 15.0)
            try:
                result = respeaker.read("PP_MIN_NS")
                if result is not None:
                    raw_value = result[0]
                    # Convert: PP_MIN_NS=0.85 -> 15% suppression, PP_MIN_NS=0.15 -> 85% suppression
                    self._noise_suppression = max(0.0, min(100.0, (1.0 - raw_value) * 100.0))
                    logger.debug(f"Noise suppression: PP_MIN_NS={raw_value:.2f} -> {self._noise_suppression:.1f}%")
                    return self._noise_suppression
            except Exception as e:
                logger.debug(f"Error getting noise suppression: {e}")
        return getattr(self, "_noise_suppression", 15.0)

    def set_noise_suppression(self, level: float) -> None:
        """Set noise suppression level (0-100%)."""
        level = max(0.0, min(100.0, level))
        self._noise_suppression = level
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return
            try:
                # Convert percentage to PP_MIN_NS value (inverted)
                value = 1.0 - (level / 100.0)
                respeaker.write("PP_MIN_NS", [value])
                logger.info(f"Noise suppression set to {level}%")
            except Exception as e:
                logger.error(f"Error setting noise suppression: {e}")

    def get_echo_cancellation_converged(self) -> bool:
        """Check if echo cancellation has converged."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return False
            try:
                result = respeaker.read("AEC_AECCONVERGED")
                if result is not None:
                    return bool(result[1])
            except Exception as e:
                logger.debug(f"Error getting AEC converged status: {e}")
        return False

    # ========== DOA (Direction of Arrival) ==========

    def get_doa_angle(self) -> tuple[float, bool] | None:
        """Get Direction of Arrival angle from microphone array.

        The DOA angle indicates the direction of the sound source relative to the robot.
        Angle is in radians: 0 = left, π/2 = front/back, π = right.

        Returns:
            Tuple of (angle_radians, speech_detected), or None if unavailable.
            - angle_radians: Sound source direction in radians
            - speech_detected: Whether speech is currently detected
        """
        if not self.is_available:
            return None
        try:
            if self.reachy.media and hasattr(self.reachy.media, "get_DoA"):
                return self.reachy.media.get_DoA()
        except Exception as e:
            logger.debug(f"Error getting DOA: {e}")
        return None

    def get_doa_angle_degrees(self) -> float:
        """Get DOA angle in degrees for Home Assistant entity.

        Returns the raw DOA angle in degrees (0-180°).
        SDK convention: 0° = left, 90° = front, 180° = right
        """
        doa = self.get_doa_angle()
        if doa is None:
            return 0.0
        angle_rad, _ = doa
        # Return raw angle in degrees (0-180°)
        angle_deg = math.degrees(angle_rad)
        return angle_deg

    def get_speech_detected(self) -> bool:
        """Get speech detection status from DOA.

        Returns True if speech is currently detected.
        """
        doa = self.get_doa_angle()
        if doa is None:
            return False
        _, speech_detected = doa
        return speech_detected
