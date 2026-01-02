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
