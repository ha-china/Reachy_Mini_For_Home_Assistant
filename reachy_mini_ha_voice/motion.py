"""Reachy Mini motion control integration.

This module provides a high-level motion API that delegates to the
MovementManager for unified 5Hz control with face tracking.
"""

import logging
import math
from typing import Optional

from .movement_manager import MovementManager, RobotState, PendingAction

_LOGGER = logging.getLogger(__name__)


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant.

    All public motion methods (on_*) are non-blocking. They send commands
    to the MovementManager which handles them in its 5Hz control loop.
    """

    def __init__(self, reachy_mini=None):
        self.reachy_mini = reachy_mini
        self._movement_manager: Optional[MovementManager] = None
        self._is_speaking = False

        # Initialize movement manager if robot is available
        if reachy_mini is not None:
            self._movement_manager = MovementManager(reachy_mini)

    def set_reachy_mini(self, reachy_mini):
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini
        if reachy_mini is not None and self._movement_manager is None:
            self._movement_manager = MovementManager(reachy_mini)
        elif reachy_mini is not None and self._movement_manager is not None:
            self._movement_manager.robot = reachy_mini

    def set_camera_server(self, camera_server):
        """Set the camera server for face tracking.
        
        Args:
            camera_server: MJPEGCameraServer instance with face tracking enabled
        """
        if self._movement_manager is not None:
            self._movement_manager.set_camera_server(camera_server)
            _LOGGER.info("Camera server connected for face tracking")

    def start(self):
        """Start the movement manager control loop."""
        if self._movement_manager is not None:
            self._movement_manager.start()
            _LOGGER.info("Motion control started")
        else:
            _LOGGER.warning("Motion control not started: movement_manager is None (reachy_mini=%s)", self.reachy_mini)

    def shutdown(self):
        """Shutdown the motion controller."""
        if self._movement_manager is not None:
            self._movement_manager.stop()
            _LOGGER.info("Motion control stopped")

    @property
    def movement_manager(self) -> Optional[MovementManager]:
        """Get the movement manager instance."""
        return self._movement_manager

    # -------------------------------------------------------------------------
    # Public non-blocking motion methods
    # -------------------------------------------------------------------------

    def on_wakeup(self):
        """Called when wake word is detected.

        Non-blocking: command sent to MovementManager.
        Face tracking will handle looking at the user automatically.
        """
        _LOGGER.debug("on_wakeup called")
        if self._movement_manager is None:
            _LOGGER.warning("on_wakeup: movement_manager is None, skipping motion")
            return

        # Set listening state - face tracking will handle looking at user
        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.info("Wake word detected, entering listening state")

    def on_listening(self):
        """Called when listening for speech - attentive pose.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.debug("Reachy Mini: Listening pose")

    def on_thinking(self):
        """Called when processing speech - thinking pose.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.THINKING)

        # Look up slightly (thinking gesture)
        action = PendingAction(
            name="thinking",
            target_pitch=math.radians(-10),  # Look up
            target_yaw=math.radians(5),      # Slight turn
            duration=0.4,
        )
        self._movement_manager.queue_action(action)
        _LOGGER.debug("Reachy Mini: Thinking pose")

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = True
        self._movement_manager.set_state(RobotState.SPEAKING)

        # Gentle nod to indicate speaking
        action = PendingAction(
            name="speaking_start",
            target_pitch=math.radians(5),  # Slight nod down
            duration=0.3,
        )
        self._movement_manager.queue_action(action)
        _LOGGER.debug("Reachy Mini: Speaking started")

    def on_speaking_end(self):
        """Called when TTS ends - stop speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = False
        # Don't change state yet - let on_idle handle that
        _LOGGER.debug("Reachy Mini: Speaking ended")

    def on_idle(self):
        """Called when returning to idle state.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = False
        self._movement_manager.set_state(RobotState.IDLE)
        self._movement_manager.reset_to_neutral(duration=0.5)
        _LOGGER.debug("Reachy Mini: Idle pose")

    def on_timer_finished(self):
        """Called when a timer finishes - alert animation.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        # Quick shake to alert
        self._movement_manager.shake(amplitude_deg=15, duration=0.4)
        _LOGGER.debug("Reachy Mini: Timer finished animation")

    def on_error(self):
        """Called on error - shake head.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.shake(amplitude_deg=10, duration=0.3)
        _LOGGER.debug("Reachy Mini: Error animation")

    def wiggle_antennas(self, happy: bool = True):
        """Wiggle antennas to show emotion.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        # Queue antenna wiggle action
        if happy:
            action = PendingAction(
                name="antenna_happy",
                duration=0.2,
            )
            # Note: antenna control is handled in MovementManager state
        else:
            action = PendingAction(
                name="antenna_sad",
                duration=0.2,
            )

        self._movement_manager.queue_action(action)
        _LOGGER.debug("Reachy Mini: Antenna wiggle (%s)", "happy" if happy else "sad")

    def update_audio_loudness(self, loudness_db: float):
        """Update audio loudness for speech-driven sway.

        Call this periodically during TTS playback to enable
        natural head movements synchronized with speech.

        Args:
            loudness_db: Audio loudness in dBFS (typically -60 to 0)
        """
        if self._movement_manager is not None:
            self._movement_manager.update_audio_loudness(loudness_db)

    # -------------------------------------------------------------------------
    # Legacy compatibility methods (deprecated, use MovementManager directly)
    # -------------------------------------------------------------------------

    def _nod(self, count: int = 1, amplitude: float = 15, duration: float = 0.5):
        """Nod head up and down (legacy)."""
        if self._movement_manager is None:
            return
        for _ in range(count):
            self._movement_manager.nod(amplitude_deg=amplitude, duration=duration)

    def _shake(self, count: int = 1, amplitude: float = 20, duration: float = 0.5):
        """Shake head left and right (legacy)."""
        if self._movement_manager is None:
            return
        for _ in range(count):
            self._movement_manager.shake(amplitude_deg=amplitude, duration=duration)

    def _look_at_user(self):
        """Look at user (legacy)."""
        if self._movement_manager is None:
            return
        self._movement_manager.reset_to_neutral(duration=0.3)

    def _return_to_neutral(self):
        """Return to neutral position (legacy)."""
        if self._movement_manager is None:
            return
        self._movement_manager.reset_to_neutral(duration=0.5)
