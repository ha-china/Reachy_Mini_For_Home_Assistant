"""Reachy Mini motion control integration."""

import asyncio
import logging
import threading
from typing import Optional
import numpy as np

_LOGGER = logging.getLogger(__name__)


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant."""

    def __init__(self, reachy_mini=None):
        self.reachy_mini = reachy_mini
        self._is_speaking = False
        self._speech_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

    def set_reachy_mini(self, reachy_mini):
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    def on_wakeup(self, doa_angle_deg: Optional[float] = None):
        """Called when wake word is detected - turn to sound source and nod.

        Args:
            doa_angle_deg: Direction of arrival angle in degrees (0=front, positive=right, negative=left)
        """
        if not self.reachy_mini:
            return

        try:
            # First turn to the sound source if DOA is available
            if doa_angle_deg is not None:
                self._turn_to_sound_source(doa_angle_deg)

            # Quick nod to acknowledge
            self._nod(count=1, amplitude=10, duration=0.3)
            _LOGGER.debug("Reachy Mini: Wake up nod (DOA: %s)", doa_angle_deg)
        except Exception as e:
            _LOGGER.error("Motion error on wakeup: %s", e)

    def on_listening(self):
        """Called when listening for speech - tilt head slightly."""
        if not self.reachy_mini:
            return

        try:
            # Tilt head slightly to show attention
            self._look_at_user()
            _LOGGER.debug("Reachy Mini: Listening pose")
        except Exception as e:
            _LOGGER.error("Motion error on listening: %s", e)

    def on_thinking(self):
        """Called when processing speech - look up slightly."""
        if not self.reachy_mini:
            return

        try:
            # Look up slightly as if thinking
            self._think_pose()
            _LOGGER.debug("Reachy Mini: Thinking pose")
        except Exception as e:
            _LOGGER.error("Motion error on thinking: %s", e)

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion."""
        if not self.reachy_mini:
            return

        try:
            self._is_speaking = True
            # Start subtle head movements during speech
            self._start_speech_motion()
            _LOGGER.debug("Reachy Mini: Speaking started")
        except Exception as e:
            _LOGGER.error("Motion error on speaking start: %s", e)

    def on_speaking_end(self):
        """Called when TTS ends - stop speech-reactive motion."""
        if not self.reachy_mini:
            return

        try:
            self._is_speaking = False
            self._stop_speech_motion()
            _LOGGER.debug("Reachy Mini: Speaking ended")
        except Exception as e:
            _LOGGER.error("Motion error on speaking end: %s", e)

    def on_idle(self):
        """Called when returning to idle state."""
        if not self.reachy_mini:
            return

        try:
            self._is_speaking = False
            self._stop_speech_motion()
            self._return_to_neutral()
            _LOGGER.debug("Reachy Mini: Idle pose")
        except Exception as e:
            _LOGGER.error("Motion error on idle: %s", e)

    def on_timer_finished(self):
        """Called when a timer finishes - alert animation."""
        if not self.reachy_mini:
            return

        try:
            # Shake head to get attention
            self._shake(count=2, amplitude=15, duration=0.4)
            _LOGGER.debug("Reachy Mini: Timer finished animation")
        except Exception as e:
            _LOGGER.error("Motion error on timer finished: %s", e)

    def on_error(self):
        """Called on error - shake head."""
        if not self.reachy_mini:
            return

        try:
            self._shake(count=1, amplitude=10, duration=0.3)
            _LOGGER.debug("Reachy Mini: Error animation")
        except Exception as e:
            _LOGGER.error("Motion error on error: %s", e)

    # -------------------------------------------------------------------------
    # Low-level motion methods
    # -------------------------------------------------------------------------

    def _nod(self, count: int = 1, amplitude: float = 15, duration: float = 0.5):
        """Nod head up and down."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            for _ in range(count):
                # Nod down
                pose_down = np.eye(4)
                pose_down[:3, :3] = R.from_euler('xyz', [amplitude, 0, 0], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_down, duration=duration / 2)

                # Nod up
                pose_up = np.eye(4)
                pose_up[:3, :3] = R.from_euler('xyz', [-amplitude / 2, 0, 0], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_up, duration=duration / 2)

            # Return to neutral
            self._return_to_neutral()
        except Exception as e:
            _LOGGER.error("Nod error: %s", e)

    def _shake(self, count: int = 1, amplitude: float = 20, duration: float = 0.5):
        """Shake head left and right."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            for _ in range(count):
                # Shake left
                pose_left = np.eye(4)
                pose_left[:3, :3] = R.from_euler('xyz', [0, 0, -amplitude], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_left, duration=duration / 2)

                # Shake right
                pose_right = np.eye(4)
                pose_right[:3, :3] = R.from_euler('xyz', [0, 0, amplitude], degrees=True).as_matrix()
                self.reachy_mini.goto_target(head=pose_right, duration=duration / 2)

            # Return to neutral
            self._return_to_neutral()
        except Exception as e:
            _LOGGER.error("Shake error: %s", e)

    def _look_at_user(self):
        """Look at user (neutral forward position)."""
        if not self.reachy_mini:
            return

        try:
            pose = np.eye(4)
            self.reachy_mini.goto_target(head=pose, duration=0.3)
        except Exception as e:
            _LOGGER.error("Look at user error: %s", e)

    def _think_pose(self):
        """Thinking pose - look up slightly."""
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [-10, 0, 5], degrees=True).as_matrix()
            self.reachy_mini.goto_target(head=pose, duration=0.4)
        except Exception as e:
            _LOGGER.error("Think pose error: %s", e)

    def _return_to_neutral(self):
        """Return to neutral position."""
        if not self.reachy_mini:
            return

        try:
            pose = np.eye(4)
            self.reachy_mini.goto_target(head=pose, duration=0.5)
        except Exception as e:
            _LOGGER.error("Return to neutral error: %s", e)

    def _start_speech_motion(self):
        """Start subtle speech-reactive motion."""
        # This would ideally run in a separate thread with subtle movements
        pass

    def _stop_speech_motion(self):
        """Stop speech-reactive motion."""
        pass

    def _turn_to_sound_source(self, doa_angle_deg: float):
        """Turn head to face the sound source based on DOA angle.

        Args:
            doa_angle_deg: Direction of arrival angle in degrees.
                           The DOA from ReSpeaker is in radians where:
                           0 = left, π/2 = front/back, π = right
                           We convert to head yaw where:
                           0 = front, positive = right, negative = left
        """
        if not self.reachy_mini:
            return

        try:
            from scipy.spatial.transform import Rotation as R

            # Clamp the angle to reasonable head rotation limits
            yaw_deg = max(-60, min(60, doa_angle_deg))

            # Create head pose with yaw rotation
            pose = np.eye(4)
            pose[:3, :3] = R.from_euler('xyz', [0, 0, yaw_deg], degrees=True).as_matrix()

            # Turn head to face the sound source
            self.reachy_mini.goto_target(head=pose, duration=0.4)
            _LOGGER.debug("Reachy Mini: Turned to sound source at %s degrees", yaw_deg)
        except Exception as e:
            _LOGGER.error("Turn to sound source error: %s", e)

    def wiggle_antennas(self, happy: bool = True):
        """Wiggle antennas to show emotion."""
        if not self.reachy_mini:
            return

        try:
            import math
            if happy:
                # Happy wiggle - both up (convert degrees to radians)
                self.reachy_mini.goto_target(antennas=[math.radians(-30), math.radians(30)], duration=0.2)
            else:
                # Sad - both down
                self.reachy_mini.goto_target(antennas=[math.radians(20), math.radians(-20)], duration=0.2)
        except Exception as e:
            _LOGGER.error("Antenna wiggle error: %s", e)
