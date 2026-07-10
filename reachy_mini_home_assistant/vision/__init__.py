"""Vision module for Reachy Mini.

This module handles all vision-related functionality:
- MJPEGCameraServer: MJPEG streaming camera server (HA Generic Camera)
- GestureDetector: HaGRID gesture recognition
- FrameProcessor: Frame processing and adaptive frame rate management

Face tracking is now delegated to the SDK's daemon-side head tracking
(``reachy_mini.start_head_tracking`` / ``stop_head_tracking``), which runs
a YuNet ONNX detector in its own GStreamer branch and blends the aim into
the IK output. The MJPEGCameraServer no longer participates in face
detection; it only encodes frames for streaming and (optionally) gesture
detection.
"""

from .camera_server import MJPEGCameraServer
from .frame_processor import (
    AdaptiveFrameRateManager,
    FrameRateConfig,
    FrameRateMode,
    ProcessingState,
    calculate_frame_interval,
)
from .gesture_detector import Gesture, GestureDetector
from .gesture_smoother import GestureSmoother

__all__ = [
    "AdaptiveFrameRateManager",
    "FrameRateConfig",
    "FrameRateMode",
    "Gesture",
    "GestureDetector",
    "GestureSmoother",
    "MJPEGCameraServer",
    "ProcessingState",
    "calculate_frame_interval",
]
