"""Frame processing helpers for `MJPEGCameraServer`."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from .camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


def capture_frames(server: "MJPEGCameraServer", *, gesture_min_fps: float) -> None:
    """Capture and encode frames for MJPEG streaming + gesture detection.

    JPEG encoding uses the SDK's GStreamer jpegenc pipeline (hardware-accelerated
    on RPi) via ``get_frame_jpeg()`` whenever the raw frame isn't needed for
    gesture detection. When gesture detection is active, the raw BGR frame is
    fetched once via ``get_frame()`` and encoded locally with OpenCV to avoid a
    double-fetch.
    """
    _LOGGER.info("Starting camera capture thread")
    frame_count = 0
    last_log_time = time.time()
    while server._running:
        try:
            current_time = time.time()
            should_run_gesture = (
                server._gesture_detection_enabled
                and server._gesture_detector is not None
                and server._frame_rate_manager.should_run_gesture_detection()
            )
            streaming = has_stream_clients(server)
            if not should_run_gesture and not streaming:
                sleep_time = server._frame_rate_manager.get_sleep_interval()
                if server._gesture_detection_enabled and server._gesture_detector is not None:
                    sleep_time = min(sleep_time, 1.0 / gesture_min_fps)
                time.sleep(sleep_time)
                continue

            if should_run_gesture:
                # Need raw BGR frame for gesture detection; encode locally for streaming.
                frame = get_camera_frame(server)
                if frame is None:
                    _sleep_until_next(server, gesture_min_fps)
                    continue
                frame_count += 1
                if streaming:
                    success, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, server.quality])
                    if success:
                        _store_frame(server, jpeg_data.tobytes())
                process_gesture_detection(server, frame)
            else:
                # Only streaming — use SDK's hardware JPEG encoder directly.
                jpeg = get_camera_jpeg(server)
                if jpeg is not None:
                    frame_count += 1
                    _store_frame(server, jpeg)

            if current_time - last_log_time >= 30.0:
                fps = frame_count / (current_time - last_log_time)
                _LOGGER.debug("Camera: %.1f fps", fps)
                frame_count = 0
                last_log_time = current_time

            _sleep_until_next(server, gesture_min_fps)
        except Exception as e:
            _LOGGER.error("Error capturing frame: %s", e)
            time.sleep(1.0)
    _LOGGER.info("Camera capture thread stopped")


def _store_frame(server: "MJPEGCameraServer", jpeg_bytes: bytes) -> None:
    with server._frame_lock:
        server._last_frame = jpeg_bytes
        server._last_frame_time = time.time()


def _sleep_until_next(server: "MJPEGCameraServer", gesture_min_fps: float) -> None:
    sleep_time = server._frame_rate_manager.get_sleep_interval()
    if server._gesture_detection_enabled and server._gesture_detector is not None:
        sleep_time = min(sleep_time, 1.0 / gesture_min_fps)
    if sleep_time > 0:
        time.sleep(sleep_time)


def has_stream_clients(server: "MJPEGCameraServer") -> bool:
    with server._stream_client_lock:
        return len(server._active_stream_clients) > 0


def register_stream_client(server: "MJPEGCameraServer") -> int:
    with server._stream_client_lock:
        client_id = server._next_client_id % 1000000
        server._next_client_id += 1
        server._active_stream_clients.add(client_id)
        _LOGGER.debug("Stream client registered: %d (total: %d)", client_id, len(server._active_stream_clients))
        return client_id


def unregister_stream_client(server: "MJPEGCameraServer", client_id: int) -> None:
    with server._stream_client_lock:
        server._active_stream_clients.discard(client_id)
        _LOGGER.debug("Stream client unregistered: %d (total: %d)", client_id, len(server._active_stream_clients))


def process_gesture_detection(server: "MJPEGCameraServer", frame: np.ndarray) -> None:
    if server._gesture_detector is None:
        return
    try:
        detected_gesture, confidence = server._gesture_detector.detect(frame)
        state_changed = False
        with server._gesture_lock:
            old_gesture = server._current_gesture
            if detected_gesture.value != "no_gesture":
                server._current_gesture = detected_gesture.value
                server._gesture_confidence = confidence
                if old_gesture != detected_gesture.value:
                    state_changed = True
                    _LOGGER.info("Gesture detected: %s (%.1f%%)", detected_gesture.value, confidence * 100)
            else:
                if server._current_gesture != "none":
                    state_changed = True
                    _LOGGER.info("Gesture cleared (no gesture detected)")
                server._current_gesture = "none"
                server._gesture_confidence = 0.0
        if state_changed and server._gesture_state_callback:
            try:
                server._gesture_state_callback()
            except Exception:
                pass
    except Exception as e:
        _LOGGER.warning("Gesture detection error: %s", e)


def get_camera_frame(server: "MJPEGCameraServer") -> np.ndarray | None:
    """Fetch a raw BGR frame from the SDK media backend (for gesture detection)."""
    if not server._camera_ready():
        return None
    try:
        acquired = server._gstreamer_lock.acquire(timeout=0.05)
        if acquired:
            try:
                return server.reachy_mini.media.get_frame()
            finally:
                server._gstreamer_lock.release()
        _LOGGER.debug("GStreamer lock busy, skipping camera frame")
        return None
    except Exception as e:
        _LOGGER.debug("Failed to get camera frame: %s", e)
        return None


def get_camera_jpeg(server: "MJPEGCameraServer") -> bytes | None:
    """Fetch a JPEG-encoded frame from the SDK's GStreamer jpegenc pipeline."""
    if not server._camera_ready():
        return None
    try:
        acquired = server._gstreamer_lock.acquire(timeout=0.05)
        if acquired:
            try:
                return server.reachy_mini.media.get_frame_jpeg()
            finally:
                server._gstreamer_lock.release()
        _LOGGER.debug("GStreamer lock busy, skipping camera jpeg")
        return None
    except Exception as e:
        _LOGGER.debug("Failed to get camera jpeg: %s", e)
        return None


def encode_snapshot_frame(server: "MJPEGCameraServer") -> bytes | None:
    """Encode a single JPEG snapshot via the SDK's GStreamer jpegenc pipeline."""
    jpeg = get_camera_jpeg(server)
    if jpeg is None:
        return None
    _store_frame(server, jpeg)
    return jpeg
