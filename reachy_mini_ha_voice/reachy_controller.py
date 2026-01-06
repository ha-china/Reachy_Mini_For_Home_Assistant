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
        
        # State caching to reduce daemon load
        # Increased TTL to 1 second to prevent overwhelming the daemon
        # when Home Assistant subscribes to all entities at once
        self._state_cache: Dict[str, Any] = {}
        self._cache_ttl = 1.0  # 1 second cache TTL (was 100ms)
        self._last_status_query = 0.0
        self._last_pose_query = 0.0
        self._last_joints_query = 0.0
        
        # Request throttling to prevent daemon overload
        self._min_request_interval = 0.1  # Minimum 100ms between SDK requests
        self._last_sdk_request = 0.0
        self._request_lock = __import__('threading').Lock()
        
        # Thread lock for ReSpeaker USB access to prevent conflicts with GStreamer audio pipeline
        self._respeaker_lock = __import__('threading').Lock()

    @property
    def is_available(self) -> bool:
        """Check if robot is available."""
        return self.reachy is not None

    # ========== Phase 1: Basic Status & Volume ==========

    def _get_cached_status(self) -> Optional[Dict]:
        """Get cached daemon status to reduce query frequency."""
        now = time.time()
        if now - self._last_status_query < self._cache_ttl:
            return self._state_cache.get('status')
        
        if not self.is_available:
            return None
        
        # Throttle SDK requests to prevent daemon overload
        with self._request_lock:
            if now - self._last_sdk_request < self._min_request_interval:
                # Return cached value if we're requesting too fast
                return self._state_cache.get('status')
            self._last_sdk_request = now
        
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

    def _get_cached_head_pose(self) -> Optional[np.ndarray]:
        """Get cached head pose to reduce query frequency."""
        now = time.time()
        if now - self._last_pose_query < self._cache_ttl:
            return self._state_cache.get('head_pose')
        
        if not self.is_available:
            return None
        
        # Throttle SDK requests to prevent daemon overload
        with self._request_lock:
            if now - self._last_sdk_request < self._min_request_interval:
                return self._state_cache.get('head_pose')
            self._last_sdk_request = now
        
        try:
            pose = self.reachy.get_current_head_pose()
            self._state_cache['head_pose'] = pose
            self._last_pose_query = now
            return pose
        except Exception as e:
            logger.error(f"Error getting head pose: {e}")
            return self._state_cache.get('head_pose')  # Return stale cache on error

    def _get_cached_joint_positions(self) -> Optional[tuple]:
        """Get cached joint positions to reduce query frequency."""
        now = time.time()
        if now - self._last_joints_query < self._cache_ttl:
            return self._state_cache.get('joint_positions')
        
        if not self.is_available:
            return None
        
        # Throttle SDK requests to prevent daemon overload
        with self._request_lock:
            if now - self._last_sdk_request < self._min_request_interval:
                return self._state_cache.get('joint_positions')
            self._last_sdk_request = now
        
        try:
            joints = self.reachy.get_current_joint_positions()
            self._state_cache['joint_positions'] = joints
            self._last_joints_query = now
            return joints
        except Exception as e:
            logger.error(f"Error getting joint positions: {e}")
            return self._state_cache.get('joint_positions')  # Return stale cache on error

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

    def get_head_x(self) -> float:
        """Get head X position in mm with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return x * 1000  # Convert m to mm
        except Exception as e:
            logger.error(f"Error getting head X: {e}")
            return 0.0

    def set_head_x(self, x_mm: float) -> None:
        """Set head X position in mm.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        The MovementManager handles all head pose control during voice conversations.
        """
        logger.warning("set_head_x is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     # Modify the X position in the matrix
        #     new_pose = pose.copy()
        #     new_pose[0, 3] = x_mm / 1000  # Convert mm to m
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head X: {e}")

    def get_head_y(self) -> float:
        """Get head Y position in mm with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return y * 1000
        except Exception as e:
            logger.error(f"Error getting head Y: {e}")
            return 0.0

    def set_head_y(self, y_mm: float) -> None:
        """Set head Y position in mm.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_head_y is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     new_pose = pose.copy()
        #     new_pose[1, 3] = y_mm / 1000
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head Y: {e}")

    def get_head_z(self) -> float:
        """Get head Z position in mm with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return z * 1000
        except Exception as e:
            logger.error(f"Error getting head Z: {e}")
            return 0.0

    def set_head_z(self, z_mm: float) -> None:
        """Set head Z position in mm.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_head_z is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     new_pose = pose.copy()
        #     new_pose[2, 3] = z_mm / 1000
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head Z: {e}")

    def get_head_roll(self) -> float:
        """Get head roll angle in degrees with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return math.degrees(roll)
        except Exception as e:
            logger.error(f"Error getting head roll: {e}")
            return 0.0

    def set_head_roll(self, roll_deg: float) -> None:
        """Set head roll angle in degrees.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_head_roll is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
        #     # Create new rotation with updated roll
        #     new_rotation = R.from_euler('xyz', [math.radians(roll_deg), pitch, yaw])
        #     new_pose = pose.copy()
        #     new_pose[:3, :3] = new_rotation.as_matrix()
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head roll: {e}")

    def get_head_pitch(self) -> float:
        """Get head pitch angle in degrees with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return math.degrees(pitch)
        except Exception as e:
            logger.error(f"Error getting head pitch: {e}")
            return 0.0

    def set_head_pitch(self, pitch_deg: float) -> None:
        """Set head pitch angle in degrees.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_head_pitch is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
        #     new_rotation = R.from_euler('xyz', [roll, math.radians(pitch_deg), yaw])
        #     new_pose = pose.copy()
        #     new_pose[:3, :3] = new_rotation.as_matrix()
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head pitch: {e}")

    def get_head_yaw(self) -> float:
        """Get head yaw angle in degrees with caching."""
        pose = self._get_cached_head_pose()
        if pose is None:
            return 0.0
        try:
            x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
            return math.degrees(yaw)
        except Exception as e:
            logger.error(f"Error getting head yaw: {e}")
            return 0.0

    def set_head_yaw(self, yaw_deg: float) -> None:
        """Set head yaw angle in degrees.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_head_yaw is disabled - MovementManager controls head pose")
        # if not self.is_available:
        #     return
        # try:
        #     pose = self.reachy.get_current_head_pose()
        #     x, y, z, roll, pitch, yaw = self._extract_pose_from_matrix(pose)
        #     new_rotation = R.from_euler('xyz', [roll, pitch, math.radians(yaw_deg)])
        #     new_pose = pose.copy()
        #     new_pose[:3, :3] = new_rotation.as_matrix()
        #     self.reachy.goto_target(head=new_pose)
        # except Exception as e:
        #     logger.error(f"Error setting head yaw: {e}")

    def get_body_yaw(self) -> float:
        """Get body yaw angle in degrees with caching."""
        joints = self._get_cached_joint_positions()
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
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_body_yaw is disabled - MovementManager controls body pose")
        # if not self.is_available:
        #     return
        # try:
        #     self.reachy.goto_target(body_yaw=math.radians(yaw_deg))
        # except Exception as e:
        #     logger.error(f"Error setting body yaw: {e}")

    def get_antenna_left(self) -> float:
        """Get left antenna angle in degrees with caching."""
        joints = self._get_cached_joint_positions()
        if joints is None:
            return 0.0
        try:
            _, antennas = joints
            return math.degrees(antennas[1])  # left is index 1
        except Exception as e:
            logger.error(f"Error getting left antenna: {e}")
            return 0.0

    def set_antenna_left(self, angle_deg: float) -> None:
        """Set left antenna angle in degrees.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_antenna_left is disabled - MovementManager controls antennas")
        # if not self.is_available:
        #     return
        # try:
        #     _, antennas = self.reachy.get_current_joint_positions()
        #     right = antennas[0]
        #     self.reachy.goto_target(antennas=[right, math.radians(angle_deg)])
        # except Exception as e:
        #     logger.error(f"Error setting left antenna: {e}")

    def get_antenna_right(self) -> float:
        """Get right antenna angle in degrees with caching."""
        joints = self._get_cached_joint_positions()
        if joints is None:
            return 0.0
        try:
            _, antennas = joints
            return math.degrees(antennas[0])  # right is index 0
        except Exception as e:
            logger.error(f"Error getting right antenna: {e}")
            return 0.0

    def set_antenna_right(self, angle_deg: float) -> None:
        """Set right antenna angle in degrees.
        
        NOTE: Disabled to prevent conflict with MovementManager's control loop.
        """
        logger.warning("set_antenna_right is disabled - MovementManager controls antennas")
        # if not self.is_available:
        #     return
        # try:
        #     _, antennas = self.reachy.get_current_joint_positions()
        #     left = antennas[1]
        #     self.reachy.goto_target(antennas=[math.radians(angle_deg), left])
        # except Exception as e:
        #     logger.error(f"Error setting right antenna: {e}")

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

    def get_imu_accel_x(self) -> float:
        """Get IMU X-axis acceleration in m/s²."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'accelerometer' in imu_data:
                return float(imu_data['accelerometer'][0])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU accel X: {e}")
            return 0.0

    def get_imu_accel_y(self) -> float:
        """Get IMU Y-axis acceleration in m/s²."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'accelerometer' in imu_data:
                return float(imu_data['accelerometer'][1])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU accel Y: {e}")
            return 0.0

    def get_imu_accel_z(self) -> float:
        """Get IMU Z-axis acceleration in m/s²."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'accelerometer' in imu_data:
                return float(imu_data['accelerometer'][2])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU accel Z: {e}")
            return 0.0

    def get_imu_gyro_x(self) -> float:
        """Get IMU X-axis angular velocity in rad/s."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'gyroscope' in imu_data:
                return float(imu_data['gyroscope'][0])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU gyro X: {e}")
            return 0.0

    def get_imu_gyro_y(self) -> float:
        """Get IMU Y-axis angular velocity in rad/s."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'gyroscope' in imu_data:
                return float(imu_data['gyroscope'][1])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU gyro Y: {e}")
            return 0.0

    def get_imu_gyro_z(self) -> float:
        """Get IMU Z-axis angular velocity in rad/s."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'gyroscope' in imu_data:
                return float(imu_data['gyroscope'][2])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU gyro Z: {e}")
            return 0.0

    def get_imu_temperature(self) -> float:
        """Get IMU temperature in °C."""
        if not self.is_available:
            return 0.0
        try:
            imu_data = self.reachy.imu
            if imu_data is not None and 'temperature' in imu_data:
                return float(imu_data['temperature'])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU temperature: {e}")
            return 0.0

    # ========== Phase 11: LED Control (via local SDK) ==========

    def _get_respeaker(self):
        """Get ReSpeaker device from media manager with thread-safe access.
        
        Returns a context manager that holds the lock during ReSpeaker operations.
        Usage:
            with self._get_respeaker() as respeaker:
                if respeaker:
                    respeaker.read("...")
        """
        if not self.is_available:
            logger.debug("ReSpeaker not available: robot not connected")
            return _ReSpeakerContext(None, self._respeaker_lock)
        try:
            if not self.reachy.media:
                logger.debug("ReSpeaker not available: media manager is None")
                return _ReSpeakerContext(None, self._respeaker_lock)
            if not self.reachy.media.audio:
                logger.debug("ReSpeaker not available: audio is None")
                return _ReSpeakerContext(None, self._respeaker_lock)
            respeaker = self.reachy.media.audio._respeaker
            if respeaker is None:
                logger.debug("ReSpeaker not available: _respeaker is None (USB device not found)")
            return _ReSpeakerContext(respeaker, self._respeaker_lock)
        except Exception as e:
            logger.debug(f"ReSpeaker not available: {e}")
            return _ReSpeakerContext(None, self._respeaker_lock)

    # ========== Phase 11: LED Control (DISABLED - LEDs are inside the robot and not visible) ==========
    # According to PROJECT_PLAN.md principle 8: "LED都被隐藏在了机器人内部，所有的LED控制全部都忽略"
    # The following LED methods are kept but commented out for reference.
    # They are not registered as entities in entity_registry.py.

    # def get_led_brightness(self) -> float:
    #     """Get LED brightness (0-100)."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return getattr(self, '_led_brightness', 50.0)
    #     try:
    #         result = respeaker.read("LED_BRIGHTNESS")
    #         if result is not None:
    #             self._led_brightness = (result[1] / 255.0) * 100.0
    #             return self._led_brightness
    #     except Exception as e:
    #         logger.debug(f"Error getting LED brightness: {e}")
    #     return getattr(self, '_led_brightness', 50.0)

    # def set_led_brightness(self, brightness: float) -> None:
    #     """Set LED brightness (0-100)."""
    #     brightness = max(0.0, min(100.0, brightness))
    #     self._led_brightness = brightness
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return
    #     try:
    #         value = int((brightness / 100.0) * 255)
    #         respeaker.write("LED_BRIGHTNESS", [value])
    #         logger.info(f"LED brightness set to {brightness}%")
    #     except Exception as e:
    #         logger.error(f"Error setting LED brightness: {e}")

    # def get_led_effect(self) -> str:
    #     """Get current LED effect."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return getattr(self, '_led_effect', 'off')
    #     try:
    #         result = respeaker.read("LED_EFFECT")
    #         if result is not None:
    #             effect_map = {0: 'off', 1: 'solid', 2: 'breathing', 3: 'rainbow', 4: 'doa'}
    #             self._led_effect = effect_map.get(result[1], 'off')
    #             return self._led_effect
    #     except Exception as e:
    #         logger.debug(f"Error getting LED effect: {e}")
    #     return getattr(self, '_led_effect', 'off')

    # def set_led_effect(self, effect: str) -> None:
    #     """Set LED effect."""
    #     self._led_effect = effect
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return
    #     try:
    #         effect_map = {'off': 0, 'solid': 1, 'breathing': 2, 'rainbow': 3, 'doa': 4}
    #         value = effect_map.get(effect, 0)
    #         respeaker.write("LED_EFFECT", [value])
    #         logger.info(f"LED effect set to {effect}")
    #     except Exception as e:
    #         logger.error(f"Error setting LED effect: {e}")

    # def get_led_color_r(self) -> float:
    #     """Get LED red color component (0-255)."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return getattr(self, '_led_color_r', 0.0)
    #     try:
    #         result = respeaker.read("LED_COLOR")
    #         if result is not None:
    #             color = result[1] if len(result) > 1 else 0
    #             self._led_color_r = float((color >> 16) & 0xFF)
    #             return self._led_color_r
    #     except Exception as e:
    #         logger.debug(f"Error getting LED color R: {e}")
    #     return getattr(self, '_led_color_r', 0.0)

    # def set_led_color_r(self, value: float) -> None:
    #     """Set LED red color component (0-255)."""
    #     self._led_color_r = max(0.0, min(255.0, value))
    #     self._update_led_color()

    # def get_led_color_g(self) -> float:
    #     """Get LED green color component (0-255)."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return getattr(self, '_led_color_g', 0.0)
    #     try:
    #         result = respeaker.read("LED_COLOR")
    #         if result is not None:
    #             color = result[1] if len(result) > 1 else 0
    #             self._led_color_g = float((color >> 8) & 0xFF)
    #             return self._led_color_g
    #     except Exception as e:
    #         logger.debug(f"Error getting LED color G: {e}")
    #     return getattr(self, '_led_color_g', 0.0)

    # def set_led_color_g(self, value: float) -> None:
    #     """Set LED green color component (0-255)."""
    #     self._led_color_g = max(0.0, min(255.0, value))
    #     self._update_led_color()

    # def get_led_color_b(self) -> float:
    #     """Get LED blue color component (0-255)."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return getattr(self, '_led_color_b', 0.0)
    #     try:
    #         result = respeaker.read("LED_COLOR")
    #         if result is not None:
    #             color = result[1] if len(result) > 1 else 0
    #             self._led_color_b = float(color & 0xFF)
    #             return self._led_color_b
    #     except Exception as e:
    #         logger.debug(f"Error getting LED color B: {e}")
    #     return getattr(self, '_led_color_b', 0.0)

    # def set_led_color_b(self, value: float) -> None:
    #     """Set LED blue color component (0-255)."""
    #     self._led_color_b = max(0.0, min(255.0, value))
    #     self._update_led_color()

    # def _update_led_color(self) -> None:
    #     """Update LED color from R, G, B components."""
    #     respeaker = self._get_respeaker()
    #     if respeaker is None:
    #         return
    #     try:
    #         r = int(getattr(self, '_led_color_r', 0))
    #         g = int(getattr(self, '_led_color_g', 0))
    #         b = int(getattr(self, '_led_color_b', 0))
    #         color = (r << 16) | (g << 8) | b
    #         respeaker.write("LED_COLOR", [color])
    #         logger.info(f"LED color set to RGB({r}, {g}, {b})")
    #     except Exception as e:
    #         logger.error(f"Error setting LED color: {e}")

    # ========== Phase 12: Audio Processing (via local SDK with thread-safe access) ==========

    def get_agc_enabled(self) -> bool:
        """Get AGC (Automatic Gain Control) enabled status."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, '_agc_enabled', False)
            try:
                result = respeaker.read("PP_AGCONOFF")
                if result is not None:
                    self._agc_enabled = bool(result[1])
                    return self._agc_enabled
            except Exception as e:
                logger.debug(f"Error getting AGC status: {e}")
        return getattr(self, '_agc_enabled', False)

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
        """Get AGC maximum gain in dB."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, '_agc_max_gain', 15.0)
            try:
                result = respeaker.read("PP_AGCMAXGAIN")
                if result is not None:
                    self._agc_max_gain = float(result[0])
                    return self._agc_max_gain
            except Exception as e:
                logger.debug(f"Error getting AGC max gain: {e}")
        return getattr(self, '_agc_max_gain', 15.0)

    def set_agc_max_gain(self, gain: float) -> None:
        """Set AGC maximum gain in dB."""
        gain = max(0.0, min(30.0, gain))
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
        """Get noise suppression level (0-100%)."""
        with self._get_respeaker() as respeaker:
            if respeaker is None:
                return getattr(self, '_noise_suppression', 50.0)
            try:
                result = respeaker.read("PP_MIN_NS")
                if result is not None:
                    # PP_MIN_NS is typically a float value, convert to percentage
                    # Lower values = more suppression
                    self._noise_suppression = max(0.0, min(100.0, (1.0 - result[0]) * 100.0))
                    return self._noise_suppression
            except Exception as e:
                logger.debug(f"Error getting noise suppression: {e}")
        return getattr(self, '_noise_suppression', 50.0)

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
