"""Runtime lifecycle helpers for `MJPEGCameraServer`."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


def load_head_tracker(server: "MJPEGCameraServer") -> bool:
    try:
        from .head_tracker import HeadTracker

        server._head_tracker = HeadTracker(confidence_threshold=server._face_confidence_threshold)
        server._face_tracking_enabled = True
        return True
    except Exception as e:
        _LOGGER.warning("Failed to load head tracker: %s", e)
        server._head_tracker = None
        server._face_tracking_enabled = False
        return False


def load_gesture_detector(server: "MJPEGCameraServer") -> bool:
    try:
        from .gesture_detector import GestureDetector

        server._gesture_detector = GestureDetector()
        if server._gesture_detector.is_available:
            server._gesture_detection_enabled = True
            return True
        server._gesture_detector = None
        server._gesture_detection_enabled = False
        return False
    except Exception as e:
        _LOGGER.warning("Failed to load gesture detector: %s", e)
        server._gesture_detector = None
        server._gesture_detection_enabled = False
        return False


async def start(server: "MJPEGCameraServer") -> None:
    if server._running:
        _LOGGER.warning("Camera server already running")
        return
    if not server._camera_ready():
        _LOGGER.warning("Camera server not started: SDK media camera is unavailable")
        return

    server._running = True
    try:
        from reachy_mini.media.media_manager import MediaBackend

        backend = server.reachy_mini.media.backend
        backend_name = {
            MediaBackend.NO_MEDIA: "No Media",
            MediaBackend.GSTREAMER: "GStreamer",
            MediaBackend.GSTREAMER_NO_VIDEO: "GStreamer (No Video)",
            MediaBackend.DEFAULT: "Default",
            MediaBackend.DEFAULT_NO_VIDEO: "Default (No Video)",
            MediaBackend.SOUNDDEVICE_OPENCV: "SoundDevice + OpenCV",
            MediaBackend.SOUNDDEVICE_NO_VIDEO: "SoundDevice (No Video)",
            MediaBackend.WEBRTC: "WebRTC",
        }.get(backend, str(backend))
        _LOGGER.info("Detected media backend: %s", backend_name)
    except ImportError:
        _LOGGER.debug("MediaBackend enum not available")
    except Exception as e:
        _LOGGER.debug("Failed to detect media backend: %s", e)

    if server._face_tracking_enabled:
        if load_head_tracker(server):
            _LOGGER.info("Face tracking enabled with YOLO head tracker (confidence=%.2f)", server._face_confidence_threshold)
    else:
        _LOGGER.info("Face tracking disabled by configuration")

    if server._gesture_detection_enabled:
        if load_gesture_detector(server):
            _LOGGER.info("Gesture detection enabled (18 HaGRID classes)")
        else:
            _LOGGER.warning("Gesture detection not available")

    server._capture_thread = threading.Thread(target=server._capture_frames, daemon=True, name="camera-capture")
    server._capture_thread.start()
    server._server = await asyncio.start_server(server._handle_client, server.host, server.port)
    _LOGGER.info("MJPEG Camera server started on http://%s:%d", server.host, server.port)
    _LOGGER.info("  Stream URL: http://<ip>:%d/stream", server.port)
    _LOGGER.info("  Snapshot URL: http://<ip>:%d/snapshot", server.port)


async def stop(server: "MJPEGCameraServer", join_timeout: float = 3.0) -> None:
    _LOGGER.info("Stopping MJPEG camera server...")
    server._running = False
    if server._capture_thread:
        server._capture_thread.join(timeout=join_timeout)
        if server._capture_thread.is_alive():
            _LOGGER.warning("Camera capture thread did not stop cleanly")
        server._capture_thread = None
    if server._server:
        server._server.close()
        await server._server.wait_closed()
        server._server = None
    release_ml_models(server)
    with server._frame_lock:
        server._last_frame = None
        server._last_frame_time = 0
    with server._face_tracking_lock:
        server._face_tracking_offsets = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    with server._gesture_lock:
        server._current_gesture = "none"
        server._gesture_confidence = 0.0
    with server._stream_client_lock:
        server._active_stream_clients.clear()
    _LOGGER.info("MJPEG Camera server stopped - all resources released")


def release_ml_models(server: "MJPEGCameraServer") -> None:
    if server._head_tracker is not None:
        try:
            if hasattr(server._head_tracker, "close"):
                server._head_tracker.close()
            del server._head_tracker
            server._head_tracker = None
            _LOGGER.debug("Head tracker model released")
        except Exception as e:
            _LOGGER.warning("Error releasing head tracker: %s", e)
    if server._gesture_detector is not None:
        try:
            if hasattr(server._gesture_detector, "close"):
                server._gesture_detector.close()
            del server._gesture_detector
            server._gesture_detector = None
            _LOGGER.debug("Gesture detector model released")
        except Exception as e:
            _LOGGER.warning("Error releasing gesture detector: %s", e)


def suspend_processing(server: "MJPEGCameraServer") -> None:
    _LOGGER.info("Suspending camera processing for sleep mode...")
    server._frame_rate_manager.suspend()
    server._face_tracking_enabled = False
    server._gesture_detection_enabled = False
    release_ml_models(server)
    with server._face_tracking_lock:
        server._face_tracking_offsets = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    with server._gesture_lock:
        server._current_gesture = "none"
        server._gesture_confidence = 0.0
    _LOGGER.info("Camera processing suspended - ML models released")
    log_vision_runtime_state(server, "Suspended")


def resume_processing(server: "MJPEGCameraServer") -> None:
    _LOGGER.info("Resuming camera processing after sleep...")
    if server._face_tracking_requested or server._gesture_detection_requested:
        server._frame_rate_manager.resume()
    if server._face_tracking_requested and server._head_tracker is None:
        if load_head_tracker(server):
            _LOGGER.info("Head tracker model reloaded (confidence=%.2f)", server._face_confidence_threshold)
    else:
        server._face_tracking_enabled = server._face_tracking_requested and server._head_tracker is not None
    if server._gesture_detection_requested and server._gesture_detector is None:
        if load_gesture_detector(server):
            _LOGGER.info("Gesture detector model reloaded")
    else:
        server._gesture_detection_enabled = server._gesture_detection_requested and server._gesture_detector is not None
    _LOGGER.info("Camera processing resumed - full functionality restored")
    log_vision_runtime_state(server, "Resumed")


def suspend(server: "MJPEGCameraServer") -> None:
    if not server._running:
        _LOGGER.debug("Camera server not running, nothing to suspend")
        return
    _LOGGER.info("Suspending camera server for sleep...")
    suspend_processing(server)
    server._running = False
    if server._capture_thread is not None:
        server._capture_thread.join(timeout=3.0)
        if server._capture_thread.is_alive():
            _LOGGER.warning("Camera capture thread did not stop cleanly during suspend")
        server._capture_thread = None
    _LOGGER.info("Camera server suspended - CPU released")


def resume_from_suspend(server: "MJPEGCameraServer") -> None:
    if server._running:
        _LOGGER.debug("Camera server already running")
        return
    _LOGGER.info("Resuming camera server from sleep...")
    server._running = True
    resume_processing(server)
    server._capture_thread = threading.Thread(target=server._capture_frames, daemon=True, name="camera-capture")
    server._capture_thread.start()
    _LOGGER.info("Camera server resumed from sleep")


def log_vision_runtime_state(server: "MJPEGCameraServer", source: str) -> None:
    _LOGGER.info(
        "%s vision state: face requested=%s active=%s, gesture requested=%s active=%s",
        source,
        server._face_tracking_requested,
        server._face_tracking_enabled,
        server._gesture_detection_requested,
        server._gesture_detection_enabled,
    )
