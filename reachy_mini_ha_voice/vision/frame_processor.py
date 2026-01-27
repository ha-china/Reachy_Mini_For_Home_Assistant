"""Frame processing module for Reachy Mini camera.

This module provides utilities for adaptive frame rate management,
AI inference scheduling, and detection processing.

The adaptive frame rate system optimizes CPU usage by:
- High frequency (15fps) when face detected or in conversation
- Low frequency (2fps) when idle and no face for short period
- Ultra-low (0.5fps) when idle for extended period
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FrameRateMode(Enum):
    """Frame rate modes for adaptive processing."""

    HIGH = "high"  # Normal tracking (15fps)
    LOW = "low"  # Low power (2fps)
    IDLE = "idle"  # Minimal CPU (0.5fps)
    SUSPENDED = "suspended"  # AI disabled


@dataclass
class FrameRateConfig:
    """Configuration for adaptive frame rate."""

    fps_high: int = 15
    fps_low: int = 2
    fps_idle: float = 0.5

    # Thresholds for mode switching
    low_power_threshold: float = 5.0  # Switch to low after 5s without face
    idle_threshold: float = 30.0  # Switch to idle after 30s without face

    # Gesture detection interval (every N frames)
    gesture_detection_interval: int = 3


@dataclass
class ProcessingState:
    """State container for frame processing."""

    current_fps: float = 15.0
    mode: FrameRateMode = FrameRateMode.HIGH

    # Timing
    no_face_duration: float = 0.0
    last_face_check_time: float = 0.0
    last_face_detected_time: float | None = None

    # Counters
    gesture_frame_counter: int = 0

    # AI state
    ai_enabled: bool = True
    in_conversation: bool = False


class AdaptiveFrameRateManager:
    """Manages adaptive frame rate for camera processing.

    This class handles the logic for switching between high/low/idle
    frame rates based on face detection and conversation state.

    Usage:
        manager = AdaptiveFrameRateManager()
        manager.update(face_detected=True, in_conversation=False)
        if manager.should_run_inference():
            # Run AI inference
            pass
        sleep_time = manager.get_sleep_interval()
    """

    def __init__(
        self,
        config: FrameRateConfig | None = None,
        time_func: Callable[[], float] | None = None,
    ):
        """Initialize the frame rate manager.

        Args:
            config: Frame rate configuration
            time_func: Function returning current time (e.g., time.time)
        """
        self.config = config or FrameRateConfig()
        self._now = time_func or time.time

        self.state = ProcessingState(current_fps=self.config.fps_high)

        # Last update time for duration tracking
        self._last_update_time = self._now()

    @property
    def current_mode(self) -> FrameRateMode:
        """Get current frame rate mode."""
        return self.state.mode

    @property
    def current_fps(self) -> float:
        """Get current frames per second."""
        return self.state.current_fps

    @property
    def is_ai_enabled(self) -> bool:
        """Check if AI inference is enabled."""
        return self.state.ai_enabled

    def update(
        self,
        face_detected: bool,
        in_conversation: bool = False,
    ) -> None:
        """Update state based on current detection results.

        Args:
            face_detected: Whether a face was detected this frame
            in_conversation: Whether robot is in conversation mode
        """
        now = self._now()
        dt = now - self._last_update_time
        self._last_update_time = now

        self.state.in_conversation = in_conversation

        if face_detected:
            self.state.no_face_duration = 0.0
            self.state.last_face_detected_time = now
            self._switch_to_high()
        else:
            self.state.no_face_duration += dt
            self._check_power_mode()

    def _switch_to_high(self) -> None:
        """Switch to high frame rate mode."""
        if self.state.mode != FrameRateMode.HIGH:
            logger.debug("Switching to HIGH frame rate mode")
        self.state.mode = FrameRateMode.HIGH
        self.state.current_fps = self.config.fps_high

    def _switch_to_low(self) -> None:
        """Switch to low frame rate mode."""
        if self.state.mode != FrameRateMode.LOW:
            logger.debug("Switching to LOW frame rate mode (no face for %.1fs)", self.state.no_face_duration)
        self.state.mode = FrameRateMode.LOW
        self.state.current_fps = self.config.fps_low

    def _switch_to_idle(self) -> None:
        """Switch to idle frame rate mode."""
        if self.state.mode != FrameRateMode.IDLE:
            logger.debug("Switching to IDLE frame rate mode (no face for %.1fs)", self.state.no_face_duration)
        self.state.mode = FrameRateMode.IDLE
        self.state.current_fps = self.config.fps_idle

    def _check_power_mode(self) -> None:
        """Check if we should switch power modes based on no_face_duration."""
        # Always stay high during conversation
        if self.state.in_conversation:
            self._switch_to_high()
            return

        if self.state.no_face_duration >= self.config.idle_threshold:
            self._switch_to_idle()
        elif self.state.no_face_duration >= self.config.low_power_threshold:
            self._switch_to_low()
        else:
            self._switch_to_high()

    def should_run_inference(self) -> bool:
        """Determine if AI inference should run this frame.

        Returns True if:
        - AI is enabled AND
        - (In conversation mode OR face was recently detected OR periodic check)
        """
        if not self.state.ai_enabled:
            return False

        # Always run during conversation
        if self.state.in_conversation:
            return True

        # High frequency mode: run every frame
        if self.state.mode == FrameRateMode.HIGH:
            return True

        # Low/idle power mode: run periodically
        now = self._now()
        time_since_last = now - self.state.last_face_check_time
        interval = 1.0 / self.state.current_fps

        if time_since_last >= interval:
            self.state.last_face_check_time = now
            return True

        return False

    def should_run_gesture_detection(self) -> bool:
        """Determine if gesture detection should run this frame.

        Gesture detection runs less frequently than face detection.
        """
        if not self.state.ai_enabled:
            return False

        self.state.gesture_frame_counter += 1
        if self.state.gesture_frame_counter >= self.config.gesture_detection_interval:
            self.state.gesture_frame_counter = 0
            return True

        return False

    def get_sleep_interval(self) -> float:
        """Get sleep interval between frames.

        Returns:
            Sleep time in seconds
        """
        return 1.0 / self.state.current_fps

    def suspend(self) -> None:
        """Suspend AI processing."""
        self.state.ai_enabled = False
        self.state.mode = FrameRateMode.SUSPENDED
        self.state.current_fps = 0.1  # Minimal
        logger.debug("Frame processing suspended")

    def resume(self) -> None:
        """Resume AI processing."""
        self.state.ai_enabled = True
        self.state.no_face_duration = 0.0
        self._switch_to_high()
        logger.debug("Frame processing resumed")

    def set_conversation_mode(self, in_conversation: bool) -> None:
        """Set conversation mode state.

        Args:
            in_conversation: Whether robot is in conversation
        """
        was_in_conversation = self.state.in_conversation
        self.state.in_conversation = in_conversation

        if in_conversation and not was_in_conversation:
            # Just entered conversation - switch to high
            self._switch_to_high()


def calculate_frame_interval(fps: float) -> float:
    """Calculate frame interval from FPS.

    Args:
        fps: Frames per second

    Returns:
        Interval in seconds between frames
    """
    if fps <= 0:
        return 1.0  # Default to 1 second
    return 1.0 / fps
