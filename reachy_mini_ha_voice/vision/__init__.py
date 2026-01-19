"""Vision module for Reachy Mini.

This module handles all vision-related functionality:
- CameraServer: MJPEG streaming server
- FrameProcessor: Frame processing and adaptive frame rate management
- HeadTracker: YOLO-based face tracking
- GestureDetector: Hand gesture recognition
"""

# Re-export main classes for backward compatibility
from ..camera_server import MJPEGCameraServer
from ..head_tracker import HeadTracker
from ..gesture_detector import GestureDetector

# New modular components
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
    # Main classes
    "MJPEGCameraServer",
    "HeadTracker",
    "GestureDetector",
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
