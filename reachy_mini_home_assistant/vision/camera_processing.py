"""Frame processing helpers for `MJPEGCameraServer`."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R

if TYPE_CHECKING:
    from .camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


def capture_frames(server: "MJPEGCameraServer", *, gesture_min_fps: float, face_tracking_target_fps: float) -> None:
    _LOGGER.info("Starting camera capture thread (face_tracking=%s)", server._face_tracking_enabled)
    frame_count = 0
    face_detect_count = 0
    last_log_time = time.time()
    while server._running:
        try:
            current_time = time.time()
            loop_time = time.monotonic()
            should_run_ai = should_run_ai_inference(server, current_time)
            should_run_face_tracking = (
                server._face_tracking_enabled
                and server._head_tracker is not None
                and loop_time >= server._next_face_tracking_time
            )
            should_run_gesture = (
                server._gesture_detection_enabled
                and server._gesture_detector is not None
                and server._frame_rate_manager.should_run_gesture_detection()
            )
            frame = (
                get_camera_frame(server)
                if should_run_ai or should_run_face_tracking or should_run_gesture or has_stream_clients(server)
                else None
            )
            if frame is not None:
                frame_count += 1
                success, jpeg_data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, server.quality])
                if success:
                    with server._frame_lock:
                        server._last_frame = jpeg_data.tobytes()
                        server._last_frame_time = time.time()
                if should_run_ai or should_run_face_tracking:
                    if should_run_face_tracking:
                        face_detect_count += 1
                        face_detected = process_face_tracking(server, frame, current_time)
                        server._next_face_tracking_time = time.monotonic() + (1.0 / face_tracking_target_fps)
                        server._frame_rate_manager.update(face_detected=face_detected)
                        current_face_state = server.is_face_detected()
                        if current_face_state != server._last_face_detected_state:
                            server._last_face_detected_state = current_face_state
                            if server._face_state_callback:
                                try:
                                    server._face_state_callback()
                                except Exception as e:
                                    _LOGGER.debug("Face state callback error: %s", e)
                    process_face_lost_interpolation(server, current_time)
                if server._gesture_detection_enabled and server._gesture_detector is not None and should_run_gesture:
                    process_gesture_detection(server, frame)
                if current_time - last_log_time >= 30.0:
                    fps = frame_count / (current_time - last_log_time)
                    detect_fps = face_detect_count / (current_time - last_log_time)
                    mode = server._frame_rate_manager.current_mode.value.upper()
                    no_face = server._frame_rate_manager.state.no_face_duration
                    _LOGGER.debug("Camera: %.1f fps, AI: %.1f fps (%s), no_face: %.0fs", fps, detect_fps, mode, no_face)
                    frame_count = 0
                    face_detect_count = 0
                    last_log_time = current_time
            elif server._face_tracking_enabled and server._head_tracker is not None:
                process_face_lost_interpolation(server, current_time)
            sleep_time = server._frame_rate_manager.get_sleep_interval()
            if server._face_tracking_enabled and server._head_tracker is not None:
                sleep_time = min(sleep_time, 1.0 / face_tracking_target_fps)
            if server._gesture_detection_enabled and server._gesture_detector is not None:
                sleep_time = min(sleep_time, 1.0 / gesture_min_fps)
            time.sleep(sleep_time)
        except Exception as e:
            _LOGGER.error("Error capturing frame: %s", e)
            time.sleep(1.0)
    _LOGGER.info("Camera capture thread stopped")


def should_run_ai_inference(server: "MJPEGCameraServer", current_time: float) -> bool:
    return server._frame_rate_manager.should_run_inference()


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


def process_face_tracking(server: "MJPEGCameraServer", frame: np.ndarray, current_time: float) -> bool:
    if server._head_tracker is None:
        return False
    try:
        face_center, _confidence = server._head_tracker.get_head_position(frame)
        if face_center is not None:
            server._face_interpolator.on_face_detected(current_time)
            h, w = frame.shape[:2]
            eye_center_norm = (face_center + 1) / 2
            u = int(np.clip(round(float(eye_center_norm[0] * w)), 1, max(1, w - 1)))
            v = int(np.clip(round(float(eye_center_norm[1] * h)), 1, max(1, h - 1)))
            target_pose = server.reachy_mini.look_at_image(u, v, duration=0.0, perform_movement=False)
            translation = target_pose[:3, 3]
            rotation = R.from_matrix(target_pose[:3, :3]).as_euler("xyz", degrees=False)
            server._face_interpolator.update_offsets(translation, rotation)
            with server._face_tracking_lock:
                server._face_tracking_offsets = list(server._face_interpolator.get_offsets())
            return True
        return False
    except Exception as e:
        _LOGGER.debug("Face tracking error: %s", e)
        return False


def process_face_lost_interpolation(server: "MJPEGCameraServer", current_time: float) -> None:
    server._face_interpolator.process_face_lost(current_time)
    with server._face_tracking_lock:
        server._face_tracking_offsets = list(server._face_interpolator.get_offsets())


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
