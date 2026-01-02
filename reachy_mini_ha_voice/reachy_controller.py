"""Reachy Mini controller wrapper for ESPHome entities."""

import logging
from typing import Optional, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

logger = logging.getLogger(__name__)


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

    @property
    def is_available(self) -> bool:
        """Check if robot is available."""
        return self.reachy is not None

    # ========== Phase 1: Basic Status & Volume ==========

    def get_daemon_state(self) -> str:
        """Get daemon state."""
        if not self.is_available:
            return "not_available"
        try:
            status = self.reachy.get_daemon_status()
            return status.state.value if hasattr(status, 'state') else "unknown"
        except Exception as e:
            logger.error(f"Error getting daemon state: {e}")
            return "error"

    def get_backend_ready(self) -> bool:
        """Check if backend is ready."""
        if not self.is_available:
            return False
        try:
            status = self.reachy.get_backend_status()
            return status.ready if hasattr(status, 'ready') else False
        except Exception as e:
            logger.error(f"Error getting backend status: {e}")
            return False

    def get_error_message(self) -> str:
        """Get current error message."""
        if not self.is_available:
            return "Robot not available"
        try:
            status = self.reachy.get_daemon_status()
            return status.error if hasattr(status, 'error') else ""
        except Exception as e:
            logger.error(f"Error getting error message: {e}")
            return str(e)

    def get_speaker_volume(self) -> float:
        """Get speaker volume (0-100)."""
        return self._speaker_volume

    def set_speaker_volume(self, volume: float) -> None:
        """
        Set speaker volume (0-100).

        Args:
            volume: Volume level 0-100
        """
        self._speaker_volume = max(0.0, min(100.0, volume))
        logger.info(f"Speaker volume set to {self._speaker_volume}%")
        # Note: Actual volume control is handled by AudioPlayer

    # ========== Phase 2: Motor Control ==========

    def get_motors_enabled(self) -> bool:
        """Check if motors are enabled."""
        if not self.is_available:
            return False
        try:
            state = self.reachy.get_full_state()
            return state.control_mode.value == "enabled"
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
        """Get current motor control mode."""
        if not self.is_available:
            return "disabled"
        try:
            state = self.reachy.get_full_state()
            return state.control_mode.value
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
                self.reachy.set_motor_control_mode("gravity_compensation")
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

    def get_head_x(self) -> float:
        """Get head X position in mm."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return pose.x * 1000  # Convert m to mm
        except Exception as e:
            logger.error(f"Error getting head X: {e}")
            return 0.0

    def set_head_x(self, x_mm: float) -> None:
        """Set head X position in mm."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(x_mm / 1000, current.y, current.z, current.roll, current.pitch, current.yaw)
            )
        except Exception as e:
            logger.error(f"Error setting head X: {e}")

    def get_head_y(self) -> float:
        """Get head Y position in mm."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return pose.y * 1000
        except Exception as e:
            logger.error(f"Error getting head Y: {e}")
            return 0.0

    def set_head_y(self, y_mm: float) -> None:
        """Set head Y position in mm."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(current.x, y_mm / 1000, current.z, current.roll, current.pitch, current.yaw)
            )
        except Exception as e:
            logger.error(f"Error setting head Y: {e}")

    def get_head_z(self) -> float:
        """Get head Z position in mm."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return pose.z * 1000
        except Exception as e:
            logger.error(f"Error getting head Z: {e}")
            return 0.0

    def set_head_z(self, z_mm: float) -> None:
        """Set head Z position in mm."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(current.x, current.y, z_mm / 1000, current.roll, current.pitch, current.yaw)
            )
        except Exception as e:
            logger.error(f"Error setting head Z: {e}")

    def get_head_roll(self) -> float:
        """Get head roll angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return math.degrees(pose.roll)
        except Exception as e:
            logger.error(f"Error getting head roll: {e}")
            return 0.0

    def set_head_roll(self, roll_deg: float) -> None:
        """Set head roll angle in degrees."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(current.x, current.y, current.z, math.radians(roll_deg), current.pitch, current.yaw)
            )
        except Exception as e:
            logger.error(f"Error setting head roll: {e}")

    def get_head_pitch(self) -> float:
        """Get head pitch angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return math.degrees(pose.pitch)
        except Exception as e:
            logger.error(f"Error getting head pitch: {e}")
            return 0.0

    def set_head_pitch(self, pitch_deg: float) -> None:
        """Set head pitch angle in degrees."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(current.x, current.y, current.z, current.roll, math.radians(pitch_deg), current.yaw)
            )
        except Exception as e:
            logger.error(f"Error setting head pitch: {e}")

    def get_head_yaw(self) -> float:
        """Get head yaw angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            pose = self.reachy.get_current_head_pose()
            return math.degrees(pose.yaw)
        except Exception as e:
            logger.error(f"Error getting head yaw: {e}")
            return 0.0

    def set_head_yaw(self, yaw_deg: float) -> None:
        """Set head yaw angle in degrees."""
        if not self.is_available:
            return
        try:
            current = self.reachy.get_current_head_pose()
            self.reachy.goto_target(
                head=(current.x, current.y, current.z, current.roll, current.pitch, math.radians(yaw_deg))
            )
        except Exception as e:
            logger.error(f"Error setting head yaw: {e}")

    def get_body_yaw(self) -> float:
        """Get body yaw angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            state = self.reachy.get_full_state()
            return math.degrees(state.body_yaw)
        except Exception as e:
            logger.error(f"Error getting body yaw: {e}")
            return 0.0

    def set_body_yaw(self, yaw_deg: float) -> None:
        """Set body yaw angle in degrees."""
        if not self.is_available:
            return
        try:
            self.reachy.goto_target(body_yaw=math.radians(yaw_deg))
        except Exception as e:
            logger.error(f"Error setting body yaw: {e}")

    def get_antenna_left(self) -> float:
        """Get left antenna angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            state = self.reachy.get_full_state()
            # antennas_position is [right, left]
            return math.degrees(state.antennas_position[1])
        except Exception as e:
            logger.error(f"Error getting left antenna: {e}")
            return 0.0

    def set_antenna_left(self, angle_deg: float) -> None:
        """Set left antenna angle in degrees."""
        if not self.is_available:
            return
        try:
            state = self.reachy.get_full_state()
            right = state.antennas_position[0]
            self.reachy.goto_target(antennas=(right, math.radians(angle_deg)))
        except Exception as e:
            logger.error(f"Error setting left antenna: {e}")

    def get_antenna_right(self) -> float:
        """Get right antenna angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            state = self.reachy.get_full_state()
            return math.degrees(state.antennas_position[0])
        except Exception as e:
            logger.error(f"Error getting right antenna: {e}")
            return 0.0

    def set_antenna_right(self, angle_deg: float) -> None:
        """Set right antenna angle in degrees."""
        if not self.is_available:
            return
        try:
            state = self.reachy.get_full_state()
            left = state.antennas_position[1]
            self.reachy.goto_target(antennas=(math.radians(angle_deg), left))
        except Exception as e:
            logger.error(f"Error setting right antenna: {e}")

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
        """Update robot to look at the target coordinates."""
        if not self.is_available:
            return
        try:
            x = getattr(self, '_look_at_x', 0.0)
            y = getattr(self, '_look_at_y', 0.0)
            z = getattr(self, '_look_at_z', 0.0)
            self.reachy.look_at_world(x, y, z)
            logger.info(f"Looking at world coordinates: ({x}, {y}, {z})")
        except Exception as e:
            logger.error(f"Error updating look at: {e}")

    # ========== Phase 5: Audio Sensors ==========

    def get_doa_angle(self) -> float:
        """Get direction of arrival angle in degrees."""
        if not self.is_available:
            return 0.0
        try:
            state = self.reachy.get_full_state()
            if hasattr(state, 'doa') and hasattr(state.doa, 'angle'):
                return math.degrees(state.doa.angle)
            return 0.0
        except Exception as e:
            logger.error(f"Error getting DOA angle: {e}")
            return 0.0

    def get_speech_detected(self) -> bool:
        """Check if speech is detected."""
        if not self.is_available:
            return False
        try:
            state = self.reachy.get_full_state()
            if hasattr(state, 'doa') and hasattr(state.doa, 'speech_detected'):
                return state.doa.speech_detected
            return False
        except Exception as e:
            logger.error(f"Error getting speech detection: {e}")
            return False

    # ========== Phase 6: Diagnostic Information ==========

    def get_control_loop_frequency(self) -> float:
        """Get control loop frequency in Hz."""
        if not self.is_available:
            return 0.0
        try:
            # This would require access to control loop stats
            # Placeholder implementation
            return 0.0
        except Exception as e:
            logger.error(f"Error getting control loop frequency: {e}")
            return 0.0

    def get_sdk_version(self) -> str:
        """Get SDK version."""
        if not self.is_available:
            return "N/A"
        try:
            status = self.reachy.get_daemon_status()
            if hasattr(status, 'version'):
                return status.version
            return "unknown"
        except Exception as e:
            logger.error(f"Error getting SDK version: {e}")
            return "error"

    def get_robot_name(self) -> str:
        """Get robot name."""
        if not self.is_available:
            return "N/A"
        try:
            status = self.reachy.get_daemon_status()
            if hasattr(status, 'robot_name'):
                return status.robot_name
            return "unknown"
        except Exception as e:
            logger.error(f"Error getting robot name: {e}")
            return "error"

    def get_wireless_version(self) -> bool:
        """Check if this is a wireless version."""
        if not self.is_available:
            return False
        try:
            status = self.reachy.get_daemon_status()
            if hasattr(status, 'wireless_version'):
                return status.wireless_version
            return False
        except Exception as e:
            logger.error(f"Error getting wireless version: {e}")
            return False

    def get_simulation_mode(self) -> bool:
        """Check if simulation mode is enabled."""
        if not self.is_available:
            return False
        try:
            status = self.reachy.get_daemon_status()
            if hasattr(status, 'simulation_enabled'):
                return status.simulation_enabled
            return False
        except Exception as e:
            logger.error(f"Error getting simulation mode: {e}")
            return False

    def get_wlan_ip(self) -> str:
        """Get WLAN IP address."""
        if not self.is_available:
            return "N/A"
        try:
            status = self.reachy.get_daemon_status()
            if hasattr(status, 'wlan_ip'):
                return status.wlan_ip
            return "N/A"
        except Exception as e:
            logger.error(f"Error getting WLAN IP: {e}")
            return "error"

    # ========== Phase 7: IMU Sensors (Wireless only) ==========

    def get_imu_accel_x(self) -> float:
        """Get IMU X-axis acceleration in m/s²."""
        if not self.is_available:
            return 0.0
        try:
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'accelerometer' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'accelerometer' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'accelerometer' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'gyroscope' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'gyroscope' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'gyroscope' in imu_data:
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
            if hasattr(self.reachy, 'imu'):
                imu_data = self.reachy.imu
                if 'temperature' in imu_data:
                    return float(imu_data['temperature'])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting IMU temperature: {e}")
            return 0.0
