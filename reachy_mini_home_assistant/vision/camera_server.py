"""
MJPEG Camera Server for Reachy Mini.

Streams camera frames from the SDK's media backend as MJPEG, which can be
integrated with Home Assistant via Generic Camera. Optional gesture
detection is also run here.

Face tracking is no longer handled in-process — it is delegated to the
SDK's daemon-side head tracking
(``reachy_mini.start_head_tracking`` / ``stop_head_tracking``). The
MJPEGCameraServer holds no face-tracking state and no longer instantiates
a YOLO head tracker; the only ML work it runs is gesture detection.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..core.config import Config
from .camera_http import handle_client, handle_index, handle_snapshot, handle_stream
from .camera_processing import (
    capture_frames,
    encode_snapshot_frame,
    get_camera_frame,
    has_stream_clients,
    process_gesture_detection,
    register_stream_client,
    unregister_stream_client,
)
from .camera_runtime import (
    apply_runtime_vision_state,
    load_gesture_detector,
    log_vision_runtime_state,
    release_ml_models,
    resume_from_suspend,
    resume_processing,
    start,
    stop,
    suspend,
    suspend_processing,
)
from .frame_processor import AdaptiveFrameRateManager, FrameRateConfig

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

_LOGGER = logging.getLogger(__name__)

MJPEG_BOUNDARY = "frame"
GESTURE_MIN_FPS = 12.0


class MJPEGCameraServer:
    """MJPEG streaming server for Reachy Mini camera.

    Provides HTTP endpoints:
    - /stream - MJPEG video stream
    - /snapshot - Single JPEG image
    - / - Simple status page
    """

    def __init__(
        self,
        reachy_mini: ReachyMini,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,
        quality: int = 80,
        enable_gesture_detection: bool = False,
        gstreamer_lock: threading.Lock | None = None,
    ):
        """Initialize the MJPEG camera server.

        Args:
            reachy_mini: Reachy Mini robot instance (can be None for testing)
            host: Host address to bind to
            port: Port number for the HTTP server
            fps: Target frames per second for the stream
            quality: JPEG quality (1-100)
            enable_gesture_detection: Enable HaGRID gesture recognition
            gstreamer_lock: Threading lock for GStreamer media access (shared across all media operations).
        """
        self.reachy_mini = reachy_mini
        self._gstreamer_lock = gstreamer_lock if gstreamer_lock is not None else threading.Lock()
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality

        self._server: asyncio.Server | None = None
        self._running = False
        self._frame_interval = 1.0 / fps
        self._last_frame: bytes | None = None
        self._last_frame_time: float = 0
        self._frame_lock = threading.Lock()

        # Frame capture thread
        self._capture_thread: threading.Thread | None = None

        # Gesture detection state
        self._gesture_detector = None
        self._gesture_detection_requested = enable_gesture_detection
        self._gesture_detection_enabled = enable_gesture_detection
        self._current_gesture = "none"
        self._gesture_confidence = 0.0
        self._gesture_lock = threading.Lock()
        self._gesture_state_callback = None

        # Adaptive frame rate manager
        self._frame_rate_manager = AdaptiveFrameRateManager(
            config=FrameRateConfig(
                fps_high=fps,
                fps_low=fps,
                fps_idle=fps,
                low_power_threshold=float("inf"),
                idle_threshold=float("inf"),
                gesture_detection_interval=Config.camera.gesture_detection_interval,
            )
        )

        # Stream client tracking for resource optimization
        self._active_stream_clients: set = set()
        self._stream_client_lock = threading.Lock()
        self._next_client_id = 0

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

    async def __aenter__(self) -> "MJPEGCameraServer":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.stop()
        return False

    def suspend_processing(self) -> None:
        suspend_processing(self)

    def resume_processing(self) -> None:
        resume_processing(self)

    def apply_runtime_vision_state(self, *, gesture_requested: bool, models_allowed: bool) -> None:
        apply_runtime_vision_state(
            self,
            gesture_requested=gesture_requested,
            models_allowed=models_allowed,
        )

    def suspend(self) -> None:
        suspend(self)

    def resume_from_suspend(self) -> None:
        resume_from_suspend(self)

    def _capture_frames(self) -> None:
        capture_frames(self, gesture_min_fps=GESTURE_MIN_FPS)

    def _has_stream_clients(self) -> bool:
        return has_stream_clients(self)

    def _register_stream_client(self) -> int:
        return register_stream_client(self)

    def _unregister_stream_client(self, client_id: int) -> None:
        unregister_stream_client(self, client_id)

    @property
    def stream_client_count(self) -> int:
        with self._stream_client_lock:
            return len(self._active_stream_clients)

    def _process_gesture_detection(self, frame: np.ndarray) -> None:
        process_gesture_detection(self, frame)

    # =========================================================================
    # Public API for gesture detection
    # =========================================================================

    def get_current_gesture(self) -> str:
        with self._gesture_lock:
            return self._current_gesture

    def get_gesture_confidence(self) -> float:
        with self._gesture_lock:
            return self._gesture_confidence * 100.0

    def set_gesture_detection_enabled(self, enabled: bool) -> None:
        if self._gesture_detection_requested == enabled and self._gesture_detection_enabled == enabled:
            return

        self._gesture_detection_requested = enabled
        self._gesture_detection_enabled = enabled
        if enabled:
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
        return self._gesture_detection_requested

    def set_gesture_state_callback(self, callback) -> None:
        self._gesture_state_callback = callback

    def _log_vision_runtime_state(self, source: str) -> None:
        log_vision_runtime_state(self, source)

    def _get_camera_frame(self) -> np.ndarray | None:
        return get_camera_frame(self)

    def get_snapshot(self) -> bytes | None:
        with self._frame_lock:
            if self._last_frame is not None:
                return self._last_frame

        if not self._running:
            return None

        return encode_snapshot_frame(self)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_client(self, reader, writer)

    async def _handle_index(self, writer: asyncio.StreamWriter) -> None:
        await handle_index(self, writer)

    async def _handle_snapshot(self, writer: asyncio.StreamWriter) -> None:
        await handle_snapshot(self, writer)

    async def _handle_stream(self, writer: asyncio.StreamWriter) -> None:
        await handle_stream(self, writer, MJPEG_BOUNDARY)
