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
            frame = (
                get_camera_frame(server)
                if should_run_gesture or has_stream_clients(server)
                else None
            )
            if frame is not None:
                frame_count += 1
                success, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, server.quality])
                if success:
                    with server._frame_lock:
                        server._last_frame = jpeg_data.tobytes()
                        server._last_frame_time = time.time()
                if should_run_gesture:
                    process_gesture_detection(server, frame)
                if current_time - last_log_time >= 30.0:
                    fps = frame_count / (current_time - last_log_time)
                    _LOGGER.debug("Camera: %.1f fps", fps)
                    frame_count = 0
                    last_log_time = current_time
            sleep_time = server._frame_rate_manager.get_sleep_interval()
            if server._gesture_detection_enabled and server._gesture_detector is not None:
                sleep_time = min(sleep_time, 1.0 / gesture_min_fps)
            time.sleep(sleep_time)
        except Exception as e:
            _LOGGER.error("Error capturing frame: %s", e)
            time.sleep(1.0)
    _LOGGER.info("Camera capture thread stopped")


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


def encode_snapshot_frame(server: "MJPEGCameraServer") -> bytes | None:
    frame = get_camera_frame(server)
    if frame is None:
        return None

    try:
        success, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, server.quality])
        if not success:
            return None

        encoded = jpeg_data.tobytes()
        with server._frame_lock:
            server._last_frame = encoded
            server._last_frame_time = time.time()
        return encoded
    except Exception as e:
        _LOGGER.debug("Failed to encode snapshot frame: %s", e)
        return None
