"""Frame processing module for Reachy Mini camera.

Provides simple fixed-rate frame pacing for the MJPEGCameraServer. The old
adaptive high/low/idle frame rate system was tied to in-process face
detection; face tracking now lives in the SDK daemon-side YuNet tracker, so
the camera server runs at a steady fps and only throttles between "capture
for streaming/gesture" and "idle".
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FrameRateMode(Enum):
    """Frame rate modes for the capture loop."""

    HIGH = "high"  # Streaming / gesture detection active
    SUSPENDED = "suspended"  # AI disabled


@dataclass
class FrameRateConfig:
    """Configuration for frame pacing."""

    fps_high: int = 15
    fps_low: int = 15  # Unused; kept for compatibility
    fps_idle: float = 15.0  # Unused; kept for compatibility
    low_power_threshold: float = float("inf")  # Unused; kept for compatibility
    idle_threshold: float = float("inf")  # Unused; kept for compatibility
    gesture_detection_interval: int = 1
    gesture_target_fps: float = 15.0


@dataclass
class ProcessingState:
    """State container for frame processing."""

    current_fps: float = 15.0
    mode: FrameRateMode = FrameRateMode.HIGH

    # Gesture cadence
    gesture_frame_counter: int = 0
    last_gesture_check_time: float = 0.0

    # AI state
    ai_enabled: bool = True


class AdaptiveFrameRateManager:
    """Fixed-rate frame pacing plus gesture detection cadence.

    The previous adaptive high/low/idle logic keyed off face detection,
    which now lives in the SDK daemon-side YuNet tracker. The camera server
    no longer performs face detection, so this manager just paces frames at
    a steady FPS and gates gesture detection at its own cadence.
    """

    def __init__(
        self,
        config: FrameRateConfig | None = None,
        time_func: Callable[[], float] | None = None,
    ):
        self.config = config or FrameRateConfig()
        self._now = time_func or time.time
        self.state = ProcessingState(current_fps=self.config.fps_high)

    @property
    def current_mode(self) -> FrameRateMode:
        return self.state.mode

    @property
    def current_fps(self) -> float:
        return self.state.current_fps

    @property
    def is_ai_enabled(self) -> bool:
        return self.state.ai_enabled

    def update(self, face_detected: bool = False, in_conversation: bool = False) -> None:
        """No-op retained for backward compatibility."""
        return

    def should_run_inference(self) -> bool:
        """Always returns the AI-enabled flag (face detection no longer gates this)."""
        return self.state.ai_enabled

    def should_run_gesture_detection(self) -> bool:
        """Determine if gesture detection should run this frame."""
        if not self.state.ai_enabled:
            return False

        self.state.gesture_frame_counter += 1
        now = self._now()
        min_interval = 1.0 / max(1.0, self.config.gesture_target_fps)

        if self.state.gesture_frame_counter < self.config.gesture_detection_interval:
            return False

        if now - self.state.last_gesture_check_time < min_interval:
            return False

        self.state.gesture_frame_counter = 0
        self.state.last_gesture_check_time = now
        return True

    def get_sleep_interval(self) -> float:
        return 1.0 / max(1.0, self.state.current_fps)

    def suspend(self) -> None:
        self.state.ai_enabled = False
        self.state.mode = FrameRateMode.SUSPENDED
        self.state.current_fps = 0.1
        logger.debug("Frame processing suspended")

    def resume(self) -> None:
        self.state.ai_enabled = True
        self.state.mode = FrameRateMode.HIGH
        self.state.current_fps = self.config.fps_high
        logger.debug("Frame processing resumed")

    def set_conversation_mode(self, in_conversation: bool) -> None:
        """No-op retained for backward compatibility (face tracking is daemon-side)."""
        return


def calculate_frame_interval(fps: float) -> float:
    """Calculate frame interval from FPS."""
    if fps <= 0:
        return 1.0
    return 1.0 / fps
