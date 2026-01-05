"""Reachy Mini motion control integration.

This module provides a high-level motion API that delegates to the
MovementManager for unified 100Hz control.
"""

import logging
import math
from typing import Optional

from .movement_manager import MovementManager, RobotState, PendingAction
from .emotion_moves import create_emotion_move

_LOGGER = logging.getLogger(__name__)


class ReachyMiniMotion:
    """Reachy Mini motion controller for voice assistant.

    All public motion methods (on_*) are non-blocking. They send commands
    to the MovementManager which handles them in its 100Hz control loop.
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

    def start(self):
        """Start the movement manager control loop."""
        if self._movement_manager is not None:
            self._movement_manager.start()
            _LOGGER.info("Motion control started")

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

    def on_wakeup(self, doa_angle_deg: Optional[float] = None):
        """Called when wake word is detected - turn to sound source and nod.

        Non-blocking: command sent to MovementManager.

        Args:
            doa_angle_deg: Direction of arrival angle in degrees
                          (0=front, positive=right, negative=left)
        """
        _LOGGER.debug("on_wakeup called with doa_angle_deg=%s", doa_angle_deg)
        if self._movement_manager is None:
            _LOGGER.warning("on_wakeup: movement_manager is None, skipping motion")
            return

        # Turn to sound source if DOA available
        if doa_angle_deg is not None:
            # Clamp to reasonable head rotation limits
            yaw_deg = max(-60, min(60, doa_angle_deg))
            self._movement_manager.turn_to_angle(yaw_deg, duration=0.8)
            _LOGGER.info("Turning to sound source at %.1f degrees", yaw_deg)
        else:
            # Look forward
            self._movement_manager.reset_to_neutral(duration=0.3)
            _LOGGER.debug("DOA angle is None, looking forward")

        # Add nod confirmation gesture after turning
        # Enhanced: More visible nod with longer duration
        nod_action = PendingAction(
            name="wakeup_nod",
            target_pitch=math.radians(18),  # Nod down 18 degrees (increased from 10)
            duration=0.5,  # Longer duration for visibility (increased from 0.3)
        )
        self._movement_manager.queue_action(nod_action)

        # Return to neutral pitch after nod
        return_action = PendingAction(
            name="wakeup_return",
            target_pitch=math.radians(0),  # Return to neutral
            duration=0.3,  # Slightly longer return (increased from 0.2)
        )
        self._movement_manager.queue_action(return_action)

        # Set listening state
        self._movement_manager.set_state(RobotState.LISTENING)

        _LOGGER.info("Reachy Mini: Wake word detected - turning to %.1f° and nodding",
                     doa_angle_deg if doa_angle_deg is not None else 0.0)

    def on_listening(self):
        """Called when listening for speech - attentive pose.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.LISTENING)

        # Use a subtle attentive gesture instead of full emotion move
        # Slight head tilt to show attention
        attention_action = PendingAction(
            name="listening_attention",
            target_pitch=math.radians(-5),  # Slight look up
            target_roll=math.radians(3),    # Slight tilt
            duration=0.4,
        )
        self._movement_manager.queue_action(attention_action)

        _LOGGER.debug("Reachy Mini: Listening pose - attentive gesture")

    def on_thinking(self):
        """Called when processing speech - thinking pose.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._movement_manager.set_state(RobotState.THINKING)

        # Use a subtle thinking gesture instead of full emotion move
        # Look up slightly as if thinking
        thinking_action = PendingAction(
            name="thinking",
            target_pitch=math.radians(-8),  # Look up
            target_yaw=math.radians(5),     # Slight turn
            duration=0.4,
        )
        self._movement_manager.queue_action(thinking_action)

        _LOGGER.debug("Reachy Mini: Thinking pose - subtle gesture")

    def on_speaking_start(self):
        """Called when TTS starts - start speech-reactive motion.

        Non-blocking: command sent to MovementManager.
        """
        if self._movement_manager is None:
            return

        self._is_speaking = True
        self._movement_manager.set_state(RobotState.SPEAKING)

        # Don't queue emotion moves during conversation - let SpeechSway handle natural motion
        # Emotion moves can still be triggered manually via ESPHome entity
        _LOGGER.debug("Reachy Mini: Speaking started with speech sway")

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

        # Return to neutral position smoothly
        # Don't queue emotion moves - let breathing animation take over naturally
        self._movement_manager.reset_to_neutral(duration=0.8)

        _LOGGER.debug("Reachy Mini: Returning to idle - neutral pose")

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
