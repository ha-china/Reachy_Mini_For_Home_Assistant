"""Reachy Mini motion control integration.

This module provides a high-level motion API that delegates to the
MovementManager for unified 5Hz control with face tracking.
"""

import logging

from .movement_manager import MovementManager, RobotState

_LOGGER = logging.getLogger(__name__)


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant.

    All public motion methods (on_*) are non-blocking. They send commands
    to the MovementManager which handles them in its 5Hz control loop.
    """

    def __init__(self, reachy_mini):
        self.reachy_mini = reachy_mini
        self._movement_manager: MovementManager | None = None
        self._camera_server = None  # Reference to camera server for face tracking control
        self._is_speaking = False

        _LOGGER.debug("ReachyMiniMotion.__init__ called with reachy_mini=%s", reachy_mini)

        # Initialize movement manager
        try:
            self._movement_manager = MovementManager(reachy_mini)
            _LOGGER.debug("MovementManager created successfully")
        except Exception as e:
            _LOGGER.error("Failed to create MovementManager: %s", e, exc_info=True)
            self._movement_manager = None

    def set_reachy_mini(self, reachy_mini):
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini
        if self._movement_manager is None:
            self._movement_manager = MovementManager(reachy_mini)
        else:
            self._movement_manager.robot = reachy_mini

    def set_camera_server(self, camera_server):
        """Set the camera server for face tracking.

        Args:
            camera_server: MJPEGCameraServer instance with face tracking enabled
        """
        self._camera_server = camera_server
        if self._movement_manager is not None:
            self._movement_manager.set_camera_server(camera_server)
            _LOGGER.info("Camera server connected for face tracking")

    def start(self):
        """Start the movement manager control loop."""
        if self._movement_manager is not None:
            self._movement_manager.start()
            _LOGGER.info("Motion control started")
        else:
            _LOGGER.warning("Motion control not started: movement_manager is None")

    def shutdown(self):
        """Shutdown the motion controller."""
        if self._movement_manager is not None:
            self._movement_manager.stop()
            _LOGGER.info("Motion control stopped")

    @property
    def movement_manager(self) -> MovementManager | None:
        """Get the movement manager instance."""
        return self._movement_manager

    # -------------------------------------------------------------------------
    # Public non-blocking motion methods
    # -------------------------------------------------------------------------

    def on_wakeup(self):
        """Called when wake word is detected.

        Non-blocking: command sent to MovementManager.
        Face tracking is always enabled, so robot will look at user automatically.
        """
        _LOGGER.debug("on_wakeup called")
        if self._movement_manager is None:
            _LOGGER.warning("on_wakeup: movement_manager is None, skipping motion")
            return

        # Face tracking is always enabled, no need to enable it here

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

    def on_continue_listening(self):
        """Called when continuing to listen in tap conversation mode.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.LISTENING)
        _LOGGER.debug("Reachy Mini: Continue listening")

    def on_thinking(self):
        """Called when processing speech - thinking pose.

        Non-blocking: command sent to MovementManager.
        Animation offsets are defined in conversation_animations.json.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.THINKING)
        _LOGGER.debug("Reachy Mini: Thinking pose")

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        Animation is defined in conversation_animations.json.
        """
        if self._movement_manager is None:
            _LOGGER.warning("MovementManager not initialized, skipping speaking animation")
            return

        self._is_speaking = True
        self._movement_manager.set_state(RobotState.SPEAKING)
        _LOGGER.info("Reachy Mini: Speaking animation started")

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
        Face tracking remains enabled for continuous tracking.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = False
        self._movement_manager.set_state(RobotState.IDLE)
        self._movement_manager.reset_to_neutral(duration=0.5)

        # Note: Face tracking remains enabled for continuous tracking
        # This allows the robot to always look at the user when they approach

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

        Non-blocking: antenna movement is handled by animation system.
        """
        if self._movement_manager is None:
            return

        # Antenna movement is handled by animation system
        # Set appropriate animation state
        if happy:
            self._movement_manager.set_state(RobotState.SPEAKING)
        _LOGGER.debug("Reachy Mini: Antenna wiggle (%s)", "happy" if happy else "sad")
