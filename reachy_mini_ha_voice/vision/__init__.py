"""Vision module for Reachy Mini.

This module handles all vision-related functionality:
- MJPEGCameraServer: MJPEG streaming camera server
- HeadTracker: YOLO-based face detection
- GestureDetector: HaGRID gesture recognition
- FrameProcessor: Frame processing and adaptive frame rate management
- FaceTrackingInterpolator: Smooth pose interpolation when face is lost
"""

from .camera_server import MJPEGCameraServer
from .face_tracking_interpolator import (
    FaceTrackingInterpolator,
    InterpolationConfig,
)
from .frame_processor import (
    AdaptiveFrameRateManager,
    FrameRateConfig,
    FrameRateMode,
    ProcessingState,
    calculate_frame_interval,
)
from .gesture_detector import Gesture, GestureDetector
from .gesture_smoother import GestureSmoother
from .head_tracker import HeadTracker

__all__ = [
    "AdaptiveFrameRateManager",
    "FaceTrackingInterpolator",
    "FrameRateConfig",
    "FrameRateMode",
    "Gesture",
    "GestureDetector",
    "GestureSmoother",
    "HeadTracker",
    "InterpolationConfig",
    "MJPEGCameraServer",
    "ProcessingState",
    "calculate_frame_interval",
]
