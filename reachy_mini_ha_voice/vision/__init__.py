"""Vision module for Reachy Mini.

This module handles vision processing utilities:
- FrameProcessor: Frame processing and adaptive frame rate management
- FaceTrackingInterpolator: Smooth pose interpolation when face is lost

Note: MJPEGCameraServer, HeadTracker, and GestureDetector are in the parent
package to avoid circular imports. Import them directly:
    from reachy_mini_ha_voice.camera_server import MJPEGCameraServer
    from reachy_mini_ha_voice.head_tracker import HeadTracker
    from reachy_mini_ha_voice.gesture_detector import GestureDetector
"""

from .frame_processor import (
    FrameRateMode,
    FrameRateConfig,
    ProcessingState,
    AdaptiveFrameRateManager,
    calculate_frame_interval,
)
from .face_tracking_interpolator import (
    InterpolationConfig,
    FaceTrackingInterpolator,
)

__all__ = [
    # Frame processing
    "FrameRateMode",
    "FrameRateConfig",
    "ProcessingState",
    "AdaptiveFrameRateManager",
    "calculate_frame_interval",
    # Face tracking interpolation
    "InterpolationConfig",
    "FaceTrackingInterpolator",
]
