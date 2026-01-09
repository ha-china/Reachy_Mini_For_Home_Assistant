"""Reachy Mini controller wrapper for ESPHome entities."""

import logging
import time
from typing import Any, Dict, Optional, TYPE_CHECKING
import math
import numpy as np
from scipy.spatial.transform import Rotation as R
import requests

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

    Provides safe access to Reachy Mini SDK functions with error handling
    and fallback for standalone mode (when robot is not available).
    """

    def __init__(self, reachy_mini: Optional["ReachyMini"] = None):
        """
        Initialize the controller.

        Args:
            reachy_mini: ReachyMini instance, or None for standalone mode
        """
        self.reachy = reachy_mini
        self._speaker_volume = 100  # Default volume
        self._movement_manager = None  # Set later via set_movement_manager()
        
        # Status caching - only for get_status() which may trigger I/O
        # Note: get_current_head_pose() and get_current_joint_positions() are
        # non-blocking in the SDK (they return cached Zenoh data), so no caching needed
        self._state_cache: Dict[str, Any] = {}
        self._cache_ttl = 2.0  # 2 second cache TTL for status queries (increased from 1s)
        self._last_status_query = 0.0
        
        # Thread lock for ReSpeaker USB access to prevent conflicts with GStreamer audio pipeline
        self._respeaker_lock = __import__('threading').Lock()

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

    # ========== Phase 1: Basic Status & Volume ==========

    def _get_cached_status(self) -> Optional[Dict]:
        """Get cached daemon status to reduce query frequency.
        
        Note: get_status() may trigger I/O, so we cache it.
        Unlike get_current_head_pose() and get_current_joint_positions()
        which are non-blocking in the SDK.
        """
        now = time.time()
        if now - self._last_status_query < self._cache_ttl:
            return self._state_cache.get('status')
        
        if not self.is_available:
            return None
        
        try:
            status = self.reachy.client.get_status(wait=False)
            self._state_cache['status'] = status
            self._last_status_query = now
            return status
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return self._state_cache.get('status')  # Return stale cache on error

    def get_daemon_state(self) -> str:
        """Get daemon state with caching."""
        status = self._get_cached_status()
        if status is None:
            return "not_available"
        return status.get('state', 'unknown')

    def get_backend_ready(self) -> bool:
        """Check if backend is ready with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return status.get('state') == 'running'

    def get_error_message(self) -> str:
        """Get current error message with caching."""
        status = self._get_cached_status()
        if status is None:
            return "Robot not available"
        return status.get('error') or ""

    def get_speaker_volume(self) -> float:
        """Get speaker volume (0-100) with caching."""
        if not self.is_available:
            return self._speaker_volume
        try:
            # Get volume from daemon API (use cached status for IP)
            status = self._get_cached_status()
            if status is None:
                return self._speaker_volume
            wlan_ip = status.get('wlan_ip', 'localhost')
            response = requests.get(f"http://{wlan_ip}:8000/api/volume/current", timeout=2)
            if response.status_code == 200:
                data = response.json()
                self._speaker_volume = float(data.get('volume', self._speaker_volume))
        except Exception as e:
            logger.debug(f"Could not get volume from API: {e}")
        return self._speaker_volume

    def set_speaker_volume(self, volume: float) -> None:
        """
        Set speaker volume (0-100) with cached status.

        Args:
            volume: Volume level 0-100
        """
        volume = max(0.0, min(100.0, volume))
        self._speaker_volume = volume

        if not self.is_available:
            logger.warning("Cannot set volume: robot not available")
            return

        try:
            # Set volume via daemon API (use cached status for IP)
            status = self._get_cached_status()
            if status is None:
                logger.error("Cannot get daemon status for volume control")
                return
            wlan_ip = status.get('wlan_ip', 'localhost')
            response = requests.post(
                f"http://{wlan_ip}:8000/api/volume/set",
                json={"volume": int(volume)},
                timeout=5
            )
            if response.status_code == 200:
                logger.info(f"Speaker volume set to {volume}%")
            else:
                logger.error(f"Failed to set volume: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error setting speaker volume: {e}")

    def get_microphone_volume(self) -> float:
        """Get microphone volume (0-100) using daemon HTTP API."""
        if not self.is_available:
            return getattr(self, '_microphone_volume', 50.0)
        
        try:
            # Get WLAN IP from cached daemon status
            status = self._get_cached_status()
            if status is None:
                return getattr(self, '_microphone_volume', 50.0)
            wlan_ip = status.get('wlan_ip', 'localhost')
            
            # Call the daemon API to get microphone volume
            response = requests.get(
                f"http://{wlan_ip}:8000/api/volume/microphone/current",
                timeout=2
            )
            if response.status_code == 200:
                data = response.json()
                self._microphone_volume = float(data.get('volume', 50))
                return self._microphone_volume
        except Exception as e:
            logger.debug(f"Could not get microphone volume from API: {e}")
        
        return getattr(self, '_microphone_volume', 50.0)

    def set_microphone_volume(self, volume: float) -> None:
        """
        Set microphone volume (0-100) using daemon HTTP API.

        Args:
            volume: Volume level 0-100
        """
        volume = max(0.0, min(100.0, volume))
        self._microphone_volume = volume

        if not self.is_available:
            logger.warning("Cannot set microphone volume: robot not available")
            return

        try:
            # Get WLAN IP from cached daemon status
            status = self._get_cached_status()
            if status is None:
                logger.error("Cannot get daemon status for microphone volume control")
                return
            wlan_ip = status.get('wlan_ip', 'localhost')
            
            # Call the daemon API to set microphone volume
            response = requests.post(
                f"http://{wlan_ip}:8000/api/volume/microphone/set",
                json={"volume": int(volume)},
                timeout=5
            )
            if response.status_code == 200:
                logger.info(f"Microphone volume set to {volume}%")
            else:
                logger.error(f"Failed to set microphone volume: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error setting microphone volume: {e}")

    # ========== Phase 2: Motor Control ==========

    def get_motors_enabled(self) -> bool:
        """Check if motors are enabled with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        try:
            backend_status = status.get('backend_status')
            if backend_status and isinstance(backend_status, dict):
                motor_mode = backend_status.get('motor_control_mode', 'disabled')
                return motor_mode == 'enabled'
            return status.get('state') == 'running'
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
            backend_status = status.get('backend_status')
            if backend_status and isinstance(backend_status, dict):
                motor_mode = backend_status.get('motor_control_mode', 'disabled')
                return motor_mode
            if status.get('state') == 'running':
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
            self.reachy.wake_up()
            logger.info("Wake up animation executed")
        except Exception as e:
            logger.error(f"Error executing wake up: {e}")

    def go_to_sleep(self) -> None:
        """Execute sleep animation."""
        if not self.is_available:
            logger.warning("Cannot sleep: robot not available")
            return

        try:
            self.reachy.goto_sleep()
            logger.info("Sleep animation executed")
        except Exception as e:
            logger.error(f"Error executing sleep: {e}")

    # ========== Phase 3: Pose Control ==========

    def _get_head_pose(self) -> Optional[np.ndarray]:
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

    def _get_joint_positions(self) -> Optional[tuple]:
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
        roll, pitch, yaw = rotation.as_euler('xyz')

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
                'x': x * 1000,  # m to mm
                'y': y * 1000,
                'z': z * 1000,
                'roll': math.degrees(roll),
                'pitch': math.degrees(pitch),
                'yaw': math.degrees(yaw),
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
        return self._get_head_pose_component('x')

    def set_head_x(self, x_mm: float) -> None:
        """Set head X position in mm via MovementManager."""
        if not self._set_pose_via_manager(x=x_mm / 1000.0):  # mm to m
            self._disabled_pose_setter('head_x')

    def get_head_y(self) -> float:
        """Get head Y position in mm."""
        return self._get_head_pose_component('y')

    def set_head_y(self, y_mm: float) -> None:
        """Set head Y position in mm via MovementManager."""
        if not self._set_pose_via_manager(y=y_mm / 1000.0):  # mm to m
            self._disabled_pose_setter('head_y')

    def get_head_z(self) -> float:
        """Get head Z position in mm."""
        return self._get_head_pose_component('z')

    def set_head_z(self, z_mm: float) -> None:
        """Set head Z position in mm via MovementManager."""
        if not self._set_pose_via_manager(z=z_mm / 1000.0):  # mm to m
            self._disabled_pose_setter('head_z')

    # Head orientation getters and setters
    def get_head_roll(self) -> float:
        """Get head roll angle in degrees."""
        return self._get_head_pose_component('roll')

    def set_head_roll(self, roll_deg: float) -> None:
        """Set head roll angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(roll=math.radians(roll_deg)):
            self._disabled_pose_setter('head_roll')

    def get_head_pitch(self) -> float:
        """Get head pitch angle in degrees."""
        return self._get_head_pose_component('pitch')

    def set_head_pitch(self, pitch_deg: float) -> None:
        """Set head pitch angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(pitch=math.radians(pitch_deg)):
            self._disabled_pose_setter('head_pitch')

    def get_head_yaw(self) -> float:
        """Get head yaw angle in degrees."""
        return self._get_head_pose_component('yaw')

    def set_head_yaw(self, yaw_deg: float) -> None:
        """Set head yaw angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(yaw=math.radians(yaw_deg)):
            self._disabled_pose_setter('head_yaw')

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
        """Set body yaw angle in degrees via MovementManager."""
        if not self._set_pose_via_manager(body_yaw=math.radians(yaw_deg)):
            self._disabled_pose_setter('body_yaw')

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
            self._disabled_pose_setter('antenna_left')

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
            self._disabled_pose_setter('antenna_right')

    # ========== Phase 4: Look At Control ==========

    def get_look_at_x(self) -> float:
        """Get look at target X coordinate in world frame (meters)."""
        # This is a target position, not a current state
        # We'll store it internally
        return getattr(self, '_look_at_x', 0.0)

    def set_look_at_x(self, x: float) -> None:
        """Set look at target X coordinate."""
        self._look_at_x = x
        self._update_look_at()

    def get_look_at_y(self) -> float:
        """Get look at target Y coordinate in world frame (meters)."""
        return getattr(self, '_look_at_y', 0.0)

    def set_look_at_y(self, y: float) -> None:
        """Set look at target Y coordinate."""
        self._look_at_y = y
        self._update_look_at()

    def get_look_at_z(self) -> float:
        """Get look at target Z coordinate in world frame (meters)."""
        return getattr(self, '_look_at_z', 0.0)

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
            backend_status = status.get('backend_status')
            if backend_status and isinstance(backend_status, dict):
                control_loop_stats = backend_status.get('control_loop_stats', {})
                return control_loop_stats.get('mean_control_loop_frequency', 0.0)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting control loop frequency: {e}")
            return 0.0

    def get_sdk_version(self) -> str:
        """Get SDK version with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return status.get('version') or "unknown"

    def get_robot_name(self) -> str:
        """Get robot name with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return status.get('robot_name') or "unknown"

    def get_wireless_version(self) -> bool:
        """Check if this is a wireless version with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return status.get('wireless_version', False)

    def get_simulation_mode(self) -> bool:
        """Check if simulation mode is enabled with caching."""
        status = self._get_cached_status()
        if status is None:
            return False
        return status.get('simulation_enabled', False)

    def get_wlan_ip(self) -> str:
        """Get WLAN IP address with caching."""
        status = self._get_cached_status()
        if status is None:
            return "N/A"
        return status.get('wlan_ip') or "N/A"

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
        return self._get_imu_value('accelerometer', 0)

    def get_imu_accel_y(self) -> float:
        """Get IMU Y-axis acceleration in m/s²."""
        return self._get_imu_value('accelerometer', 1)

    def get_imu_accel_z(self) -> float:
        """Get IMU Z-axis acceleration in m/s²."""
        return self._get_imu_value('accelerometer', 2)

    def get_imu_gyro_x(self) -> float:
        """Get IMU X-axis angular velocity in rad/s."""
        return self._get_imu_value('gyroscope', 0)

    def get_imu_gyro_y(self) -> float:
        """Get IMU Y-axis angular velocity in rad/s."""
        return self._get_imu_value('gyroscope', 1)

    def get_imu_gyro_z(self) -> float:
        """Get IMU Z-axis angular velocity in rad/s."""
        return self._get_imu_value('gyroscope', 2)

    def get_imu_temperature(self) -> float:
        """Get IMU temperature in °C."""
        return self._get_imu_value('temperature', -1)

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
        """
        if not self.is_available:
            return _ReSpeakerContext(None, self._respeaker_lock)
        try:
            if not self.reachy.media or not self.reachy.media.audio:
                return _ReSpeakerContext(None, self._respeaker_lock)
            respeaker = self.reachy.media.audio._respeaker
            return _ReSpeakerContext(respeaker, self._respeaker_lock)
        except Exception:
            return _ReSpeakerContext(None, self._respeaker_lock)

    # ========== Phase 12: Audio Processing (via local SDK with thread-safe access) ==========

    def get_agc_enabled(self) -> bool:
        """Get AGC (Automatic Gain Control) enabled status."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, '_agc_enabled', True)  # Default to enabled
            try:
                result = respeaker.read("PP_AGCONOFF")
                if result is not None:
                    self._agc_enabled = bool(result[1])
                    return self._agc_enabled
            except Exception as e:
                logger.debug(f"Error getting AGC status: {e}")
        return getattr(self, '_agc_enabled', True)

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
                return getattr(self, '_agc_max_gain', 30.0)  # Default to optimized value
            try:
                result = respeaker.read("PP_AGCMAXGAIN")
                if result is not None:
                    self._agc_max_gain = float(result[0])
                    return self._agc_max_gain
            except Exception as e:
                logger.debug(f"Error getting AGC max gain: {e}")
        return getattr(self, '_agc_max_gain', 30.0)

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
                return getattr(self, '_noise_suppression', 15.0)
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
        return getattr(self, '_noise_suppression', 15.0)

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
            if self.reachy.media and self.reachy.media.audio:
                return self.reachy.media.audio.get_DoA()
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
