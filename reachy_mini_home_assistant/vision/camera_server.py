"""
MJPEG Camera Server for Reachy Mini with Face Tracking.

This module provides an HTTP server that streams camera frames from Reachy Mini
as MJPEG, which can be integrated with Home Assistant via Generic Camera.
Also provides face tracking for head movement control.

Reference: reachy_mini_conversation_app/src/reachy_mini_conversation_app/camera_worker.py
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from ..core.config import Config
from .camera_http import handle_client, handle_index, handle_snapshot, handle_stream
from .camera_processing import (
    capture_frames,
    get_camera_frame,
    has_stream_clients,
    process_face_lost_interpolation,
    process_face_tracking,
    process_gesture_detection,
    register_stream_client,
    should_run_ai_inference,
    unregister_stream_client,
)
from .camera_runtime import (
    apply_runtime_vision_state,
    load_gesture_detector,
    load_head_tracker,
    log_vision_runtime_state,
    release_ml_models,
    resume_from_suspend,
    resume_processing,
    start,
    stop,
    suspend,
    suspend_processing,
)
from .face_tracking_interpolator import FaceTrackingInterpolator, InterpolationConfig

# Import adaptive frame rate manager
from .frame_processor import AdaptiveFrameRateManager, FrameRateConfig

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

_LOGGER = logging.getLogger(__name__)

# MJPEG boundary string
MJPEG_BOUNDARY = "frame"
GESTURE_MIN_FPS = 12.0
FACE_TRACKING_TARGET_FPS = 25.0


class MJPEGCameraServer:
    """
    MJPEG streaming server for Reachy Mini camera with face tracking.

    Provides HTTP endpoints:
    - /stream - MJPEG video stream
    - /snapshot - Single JPEG image
    - / - Simple status page

    Also provides face tracking offsets for head movement control.

    Resource Optimization:
    - Adaptive frame rate: high (15fps) when face detected or in conversation,
      low (3fps) when idle and no face for extended period
    - Face detection pauses after prolonged absence to save CPU
    """

    def __init__(
        self,
        reachy_mini: ReachyMini,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,  # 15fps for smooth face tracking
        quality: int = 80,
        enable_face_tracking: bool = True,
        enable_gesture_detection: bool = False,
        face_confidence_threshold: float = 0.5,  # Min confidence for face detection
        gstreamer_lock: threading.Lock | None = None,
    ):
        """
        Initialize the MJPEG camera server.

        Args:
            reachy_mini: Reachy Mini robot instance (can be None for testing)
            host: Host address to bind to
            port: Port number for the HTTP server
            fps: Target frames per second for the stream
            quality: JPEG quality (1-100)
            enable_face_tracking: Enable face tracking for head movement
            face_confidence_threshold: Minimum confidence for face detection (0-1)
            gstreamer_lock: Threading lock for GStreamer media access (shared across all media operations).
        """
        self.reachy_mini = reachy_mini
        self._gstreamer_lock = gstreamer_lock if gstreamer_lock is not None else threading.Lock()
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality
        self.enable_face_tracking = enable_face_tracking
        self._face_confidence_threshold = face_confidence_threshold

        self._server: asyncio.Server | None = None
        self._running = False
        self._frame_interval = 1.0 / fps
        self._last_frame: bytes | None = None
        self._last_frame_time: float = 0
        self._frame_lock = threading.Lock()

        # Frame capture thread
        self._capture_thread: threading.Thread | None = None

        # Face tracking state
        self._head_tracker = None
        self._face_tracking_requested = enable_face_tracking
        self._face_tracking_enabled = enable_face_tracking
        self._face_tracking_offsets: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self._face_tracking_lock = threading.Lock()
        self._next_face_tracking_time = 0.0

        # Gesture detection state
        self._gesture_detector = None
        self._gesture_detection_requested = enable_gesture_detection
        self._gesture_detection_enabled = enable_gesture_detection
        self._current_gesture = "none"
        self._gesture_confidence = 0.0
        self._gesture_lock = threading.Lock()
        self._gesture_state_callback = None  # Callback to notify entity registry

        # Face detection state callback (similar to gesture)
        self._face_state_callback = None  # Callback to notify entity registry
        self._last_face_detected_state = False  # Track previous state for change detection

        # Face tracking interpolator (handles smooth return to neutral)
        self._face_interpolator = FaceTrackingInterpolator(
            config=InterpolationConfig(
                face_lost_delay=2.0,
                interpolation_duration=1.0,
                offset_scale=0.6,
                pitch_offset_deg=9.0,
                yaw_offset_deg=-7.0,
            )
        )

        # =====================================================================
        # Adaptive frame rate manager (replaces inline logic)
        # =====================================================================
        self._frame_rate_manager = AdaptiveFrameRateManager(
            config=FrameRateConfig(
                fps_high=fps,
                fps_low=2,
                fps_idle=0.5,
                low_power_threshold=5.0,
                idle_threshold=30.0,
                gesture_detection_interval=Config.camera.gesture_detection_interval,
            )
        )

        # Stream client tracking for resource optimization
        self._active_stream_clients: set = set()
        self._stream_client_lock = threading.Lock()
        self._next_client_id = 0

    def _load_head_tracker(self) -> bool:
        return load_head_tracker(self)

    def _load_gesture_detector(self) -> bool:
        return load_gesture_detector(self)

    def _get_media_camera(self):
        """Return the SDK camera object when video is available."""
        return self.reachy_mini.media.camera

    def _camera_ready(self) -> bool:
        """Whether the SDK reports a usable camera backend."""
        return self._get_media_camera() is not None

    async def start(self) -> None:
        await start(self)

    async def stop(self, join_timeout: float = 3.0) -> None:
        await stop(self, join_timeout=join_timeout)

    def _release_ml_models(self) -> None:
        release_ml_models(self)

    async def __aenter__(self) -> MJPEGCameraServer:
        """Context manager entry - start the server."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit - stop the server and release resources."""
        await self.stop()
        return False  # Don't suppress exceptions

    def suspend_processing(self) -> None:
        suspend_processing(self)

    def resume_processing(self) -> None:
        resume_processing(self)

    def apply_runtime_vision_state(
        self, *, face_requested: bool, gesture_requested: bool, models_allowed: bool
    ) -> None:
        apply_runtime_vision_state(
            self,
            face_requested=face_requested,
            gesture_requested=gesture_requested,
            models_allowed=models_allowed,
        )

    def suspend(self) -> None:
        suspend(self)

    def resume_from_suspend(self) -> None:
        resume_from_suspend(self)

    def _capture_frames(self) -> None:
        capture_frames(self, gesture_min_fps=GESTURE_MIN_FPS, face_tracking_target_fps=FACE_TRACKING_TARGET_FPS)

    def _should_run_ai_inference(self, current_time: float) -> bool:
        return should_run_ai_inference(self, current_time)

    def _has_stream_clients(self) -> bool:
        return has_stream_clients(self)

    def _register_stream_client(self) -> int:
        return register_stream_client(self)

    def _unregister_stream_client(self, client_id: int) -> None:
        unregister_stream_client(self, client_id)

    @property
    def stream_client_count(self) -> int:
        """Get the number of active stream clients."""
        with self._stream_client_lock:
            return len(self._active_stream_clients)

    def _process_face_tracking(self, frame: np.ndarray, current_time: float) -> bool:
        return process_face_tracking(self, frame, current_time)

    def _process_face_lost_interpolation(self, current_time: float) -> None:
        process_face_lost_interpolation(self, current_time)

    # =========================================================================
    # Public API for face tracking
    # =========================================================================

    def get_face_tracking_offsets(self) -> tuple[float, float, float, float, float, float]:
        """Get current face tracking offsets (thread-safe).

        Returns:
            Tuple of (x, y, z, roll, pitch, yaw) offsets
        """
        with self._face_tracking_lock:
            offsets = self._face_tracking_offsets
            return (offsets[0], offsets[1], offsets[2], offsets[3], offsets[4], offsets[5])

    def is_face_detected(self) -> bool:
        """Check if a face is currently detected.

        Returns True if face was detected recently (within face_lost_delay period).
        This is useful for Home Assistant entities to expose face detection status.

        Returns:
            True if face is detected, False otherwise
        """
        return self._face_interpolator.is_face_detected()

    def _log_vision_runtime_state(self, source: str) -> None:
        log_vision_runtime_state(self, source)

    def set_face_tracking_enabled(self, enabled: bool) -> None:
        """Enable or disable face tracking."""
        if self._face_tracking_requested == enabled and self._face_tracking_enabled == enabled:
            return  # No change, skip logging
        self._face_tracking_requested = enabled
        self._face_tracking_enabled = enabled
        self._next_face_tracking_time = 0.0
        if enabled:
            # Ensure AI scheduler is active when user re-enables tracking from HA switch.
            self._frame_rate_manager.resume()
            if self._head_tracker is None:
                self._load_head_tracker()
        else:
            # Start interpolation back to neutral
            self._face_interpolator.reset_interpolation()
            self._head_tracker = None
            with self._face_tracking_lock:
                self._face_tracking_offsets = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self._log_vision_runtime_state("Face toggle")

    def get_face_tracking_enabled(self) -> bool:
        """Return whether face tracking is enabled."""
        return self._face_tracking_requested

    def get_face_confidence_threshold(self) -> float:
        """Return current face confidence threshold (0-1)."""
        return self._face_confidence_threshold

    def set_face_confidence_threshold(self, threshold: float) -> None:
        """Set face detection confidence threshold (0-1)."""
        threshold = max(0.0, min(1.0, float(threshold)))
        if abs(self._face_confidence_threshold - threshold) < 1e-6:
            return

        self._face_confidence_threshold = threshold

        # Reload model to apply threshold immediately when enabled.
        if self._face_tracking_requested:
            if not self._load_head_tracker():
                _LOGGER.warning("Failed to apply face confidence threshold %.2f", threshold)

        _LOGGER.info("Face confidence threshold set to %.2f", self._face_confidence_threshold)

    def set_conversation_mode(self, in_conversation: bool) -> None:
        """Set conversation mode for adaptive face tracking.

        When in conversation mode, face tracking runs at high frequency
        regardless of whether a face is currently detected.

        Args:
            in_conversation: True when voice assistant is actively conversing
        """
        self._frame_rate_manager.set_conversation_mode(in_conversation)
        if in_conversation:
            _LOGGER.debug("Face tracking: conversation mode ON (high frequency)")
        else:
            _LOGGER.debug("Face tracking: conversation mode OFF (adaptive)")

    # =========================================================================
    # Gesture detection
    # =========================================================================

    def _process_gesture_detection(self, frame: np.ndarray) -> None:
        process_gesture_detection(self, frame)

    def get_current_gesture(self) -> str:
        """Get current detected gesture name (thread-safe).

        Returns:
            Gesture name string (e.g., "like", "peace", "none")
        """
        with self._gesture_lock:
            return self._current_gesture

    def get_gesture_confidence(self) -> float:
        """Get current gesture detection confidence (thread-safe).

        Returns:
            Confidence value (0.0 to 1.0), multiplied by 100 for percentage display
        """
        with self._gesture_lock:
            return self._gesture_confidence * 100.0  # Return as percentage

    def set_gesture_detection_enabled(self, enabled: bool) -> None:
        """Enable or disable gesture detection."""
        if self._gesture_detection_requested == enabled and self._gesture_detection_enabled == enabled:
            return

        self._gesture_detection_requested = enabled
        self._gesture_detection_enabled = enabled
        if enabled:
            # Ensure AI scheduler is active when user re-enables tracking from HA switch.
            self._frame_rate_manager.resume()
            if self._gesture_detector is None:
                self._load_gesture_detector()
        else:
            self._gesture_detector = None
            with self._gesture_lock:
                self._current_gesture = "none"
                self._gesture_confidence = 0.0
        self._log_vision_runtime_state("Gesture toggle")

    def get_gesture_detection_enabled(self) -> bool:
        """Return whether gesture detection is enabled."""
        return self._gesture_detection_requested

    def set_gesture_state_callback(self, callback) -> None:
        """Set callback to notify when gesture state changes."""
        self._gesture_state_callback = callback

    def set_face_state_callback(self, callback) -> None:
        """Set callback to notify when face detection state changes."""
        self._face_state_callback = callback

    def _get_camera_frame(self) -> np.ndarray | None:
        return get_camera_frame(self)

    def get_snapshot(self) -> bytes | None:
        """Get the latest frame as JPEG bytes."""
        with self._frame_lock:
            return self._last_frame

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await handle_client(self, reader, writer)

    async def _handle_index(self, writer: asyncio.StreamWriter) -> None:
        await handle_index(self, writer)

    async def _handle_snapshot(self, writer: asyncio.StreamWriter) -> None:
        await handle_snapshot(self, writer)

    async def _handle_stream(self, writer: asyncio.StreamWriter) -> None:
        await handle_stream(self, writer, MJPEG_BOUNDARY)
