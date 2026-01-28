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

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R

from .face_tracking_interpolator import FaceTrackingInterpolator, InterpolationConfig

# Import adaptive frame rate manager
from .frame_processor import AdaptiveFrameRateManager, FrameRateConfig

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

_LOGGER = logging.getLogger(__name__)

# MJPEG boundary string
MJPEG_BOUNDARY = "frame"


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
        reachy_mini: ReachyMini | None = None,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,  # 15fps for smooth face tracking
        quality: int = 80,
        enable_face_tracking: bool = True,
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
        self._face_tracking_enabled = True  # Enabled by default for always-on face tracking
        self._face_tracking_offsets: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self._face_tracking_lock = threading.Lock()

        # Gesture detection state
        self._gesture_detector = None
        self._gesture_detection_enabled = True
        self._current_gesture = "none"
        self._gesture_confidence = 0.0
        self._gesture_lock = threading.Lock()
        self._gesture_state_callback = None  # Callback to notify entity registry
        self._gesture_action_callback = None  # Callback for gesture → action mapping

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
                gesture_detection_interval=3,
            )
        )

        # Stream client tracking for resource optimization
        self._active_stream_clients: set = set()
        self._stream_client_lock = threading.Lock()
        self._next_client_id = 0

    async def start(self) -> None:
        """Start the MJPEG camera server."""
        if self._running:
            _LOGGER.warning("Camera server already running")
            return

        self._running = True

        # Detect media backend type for compatibility handling
        if self.reachy_mini is not None and self.reachy_mini.media is not None:
            try:
                from reachy_mini.media.media_manager import MediaBackend

                backend = self.reachy_mini.media.backend
                backend_name = {
                    MediaBackend.GSTREAMER: "GStreamer",
                    MediaBackend.DEFAULT: "Default",
                    MediaBackend.DEFAULT_NO_VIDEO: "Default (No Video)",
                }.get(backend, str(backend))
                _LOGGER.info("Detected media backend: %s", backend_name)
            except ImportError:
                _LOGGER.debug("MediaBackend enum not available")
            except Exception as e:
                _LOGGER.debug("Failed to detect media backend: %s", e)

        # Initialize head tracker if face tracking enabled
        if self.enable_face_tracking:
            try:
                from .head_tracker import HeadTracker

                self._head_tracker = HeadTracker(confidence_threshold=self._face_confidence_threshold)
                _LOGGER.info(
                    "Face tracking enabled with YOLO head tracker (confidence=%.2f)", self._face_confidence_threshold
                )
            except ImportError as e:
                _LOGGER.error("Failed to import head tracker: %s", e)
                self._head_tracker = None
            except Exception as e:
                _LOGGER.warning("Failed to initialize head tracker: %s", e)
                self._head_tracker = None
        else:
            _LOGGER.info("Face tracking disabled by configuration")

        # Initialize gesture detector
        if self._gesture_detection_enabled:
            try:
                from .gesture_detector import GestureDetector

                self._gesture_detector = GestureDetector()
                if self._gesture_detector.is_available:
                    _LOGGER.info("Gesture detection enabled (18 HaGRID classes)")
                else:
                    _LOGGER.warning("Gesture detection not available")
                    self._gesture_detector = None
            except ImportError as e:
                _LOGGER.warning("Failed to import gesture detector: %s", e)
                self._gesture_detector = None
            except Exception as e:
                _LOGGER.warning("Failed to initialize gesture detector: %s", e)
                self._gesture_detector = None

        # Start frame capture thread
        self._capture_thread = threading.Thread(target=self._capture_frames, daemon=True, name="camera-capture")
        self._capture_thread.start()

        # Start HTTP server
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )

        _LOGGER.info("MJPEG Camera server started on http://%s:%d", self.host, self.port)
        _LOGGER.info("  Stream URL: http://<ip>:%d/stream", self.port)
        _LOGGER.info("  Snapshot URL: http://<ip>:%d/snapshot", self.port)

    async def stop(self, join_timeout: float = 3.0) -> None:
        """Stop the MJPEG camera server and release all resources.

        This method ensures complete cleanup of:
        - Capture thread
        - HTTP server
        - ML models (head tracker, gesture detector)
        - Frame buffers and state
        - SDK media resources
        """
        _LOGGER.info("Stopping MJPEG camera server...")
        self._running = False

        # 0. Close SDK media resources to prevent leaks
        if self.reachy_mini is not None and self.reachy_mini.media is not None:
            try:
                self.reachy_mini.media.close()
                _LOGGER.info("SDK media resources closed")
            except Exception as e:
                _LOGGER.debug("Failed to close SDK media: %s", e)

        # 1. Stop capture thread
        if self._capture_thread:
            # Wait up to join_timeout seconds - longer than max sleep time (2s in idle mode)
            self._capture_thread.join(timeout=join_timeout)
            if self._capture_thread.is_alive():
                _LOGGER.warning("Camera capture thread did not stop cleanly")
            self._capture_thread = None

        # 2. Stop HTTP server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # 3. Release ML models (explicit cleanup)
        self._release_ml_models()

        # 4. Clear frame buffer
        with self._frame_lock:
            self._last_frame = None
            self._last_frame_time = 0

        # 5. Clear tracking state
        with self._face_tracking_lock:
            self._face_tracking_offsets = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        with self._gesture_lock:
            self._current_gesture = "none"
            self._gesture_confidence = 0.0

        # 6. Clear active clients
        with self._stream_client_lock:
            self._active_stream_clients.clear()

        _LOGGER.info("MJPEG Camera server stopped - all resources released")

    def _release_ml_models(self) -> None:
        """Release ML models from memory.

        This is called during stop() and suspend_processing() to free GPU/CPU memory.
        """
        # Release YOLO head tracker model
        if self._head_tracker is not None:
            try:
                # Try to call close() if available, otherwise just delete
                if hasattr(self._head_tracker, "close"):
                    self._head_tracker.close()
                del self._head_tracker
                self._head_tracker = None
                _LOGGER.debug("Head tracker model released")
            except Exception as e:
                _LOGGER.warning("Error releasing head tracker: %s", e)

        # Release gesture detector model
        if self._gesture_detector is not None:
            try:
                if hasattr(self._gesture_detector, "close"):
                    self._gesture_detector.close()
                del self._gesture_detector
                self._gesture_detector = None
                _LOGGER.debug("Gesture detector model released")
            except Exception as e:
                _LOGGER.warning("Error releasing gesture detector: %s", e)

    async def __aenter__(self) -> MJPEGCameraServer:
        """Context manager entry - start the server."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit - stop the server and release resources."""
        await self.stop()
        return False  # Don't suppress exceptions

    def suspend_processing(self) -> None:
        """Suspend AI processing for sleep mode.

        This releases ML models from memory while keeping basic MJPEG
        streaming capability (though it will only serve cached frames).

        Call resume_processing() to restore full functionality.
        """
        _LOGGER.info("Suspending camera processing for sleep mode...")

        # Suspend frame rate manager
        self._frame_rate_manager.suspend()
        self._face_tracking_enabled = False
        self._gesture_detection_enabled = False

        # Release ML models (use shared method to avoid duplication)
        self._release_ml_models()

        # Reset tracking state
        with self._face_tracking_lock:
            self._face_tracking_offsets = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        with self._gesture_lock:
            self._current_gesture = "none"
            self._gesture_confidence = 0.0

        _LOGGER.info("Camera processing suspended - ML models released")

    def resume_processing(self) -> None:
        """Resume AI processing after sleep mode.

        This reloads ML models and restores full camera functionality.
        Should be called after robot has fully woken up.
        """
        _LOGGER.info("Resuming camera processing after sleep...")

        # Resume frame rate manager
        self._frame_rate_manager.resume()

        # Reload head tracker if face tracking was originally enabled
        if self.enable_face_tracking and self._head_tracker is None:
            try:
                from .head_tracker import HeadTracker

                self._head_tracker = HeadTracker(confidence_threshold=self._face_confidence_threshold)
                self._face_tracking_enabled = True
                _LOGGER.info("Head tracker model reloaded (confidence=%.2f)", self._face_confidence_threshold)
            except Exception as e:
                _LOGGER.warning("Failed to reload head tracker: %s", e)
                self._face_tracking_enabled = False

        # Reload gesture detector
        if self._gesture_detector is None:
            try:
                from .gesture_detector import GestureDetector

                self._gesture_detector = GestureDetector()
                if self._gesture_detector.is_available:
                    self._gesture_detection_enabled = True
                    _LOGGER.info("Gesture detector model reloaded")
                else:
                    self._gesture_detector = None
                    self._gesture_detection_enabled = False
            except Exception as e:
                _LOGGER.warning("Failed to reload gesture detector: %s", e)
                self._gesture_detection_enabled = False

        _LOGGER.info("Camera processing resumed - full functionality restored")

    def suspend(self) -> None:
        """Fully suspend the camera server for sleep mode.

        This stops the capture thread and releases all resources to free CPU.
        Call resume_from_suspend() to restart.
        """
        if not self._running:
            _LOGGER.debug("Camera server not running, nothing to suspend")
            return

        _LOGGER.info("Suspending camera server for sleep...")

        # First suspend AI processing
        self.suspend_processing()

        # Stop the capture thread to release CPU
        self._running = False
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=3.0)
            if self._capture_thread.is_alive():
                _LOGGER.warning("Camera capture thread did not stop cleanly during suspend")
            self._capture_thread = None

        _LOGGER.info("Camera server suspended - CPU released")

    def resume_from_suspend(self) -> None:
        """Resume the camera server after sleep.

        This restarts the capture thread and reloads ML models.
        """
        if self._running:
            _LOGGER.debug("Camera server already running")
            return

        _LOGGER.info("Resuming camera server from sleep...")

        self._running = True

        # Resume AI processing (reloads models)
        self.resume_processing()

        # Restart capture thread
        self._capture_thread = threading.Thread(target=self._capture_frames, daemon=True, name="camera-capture")
        self._capture_thread.start()

        _LOGGER.info("Camera server resumed from sleep")

    def _capture_frames(self) -> None:
        """Background thread to capture frames from Reachy Mini and do face tracking.

        Resource optimization:
        - High frequency (15fps) when face detected or in conversation
        - Low frequency (2fps) when idle and no face for short period
        - Ultra-low (0.5fps) when idle for extended period - minimal AI inference
        """
        _LOGGER.info("Starting camera capture thread (face_tracking=%s)", self._face_tracking_enabled)

        frame_count = 0
        face_detect_count = 0
        last_log_time = time.time()

        while self._running:
            try:
                current_time = time.time()

                # Determine if we should run AI inference this frame
                should_run_ai = self._should_run_ai_inference(current_time)
                should_run_gesture = (
                    self._gesture_detection_enabled
                    and self._gesture_detector is not None
                    and self._frame_rate_manager.should_run_gesture_detection()
                )

                # Only get frame if needed (AI inference, gesture detection, or MJPEG streaming)
                frame = (
                    self._get_camera_frame()
                    if should_run_ai or should_run_gesture or self._has_stream_clients()
                    else None
                )

                if frame is not None:
                    frame_count += 1

                    # Encode frame as JPEG for streaming
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                    success, jpeg_data = cv2.imencode(".jpg", frame, encode_params)

                    if success:
                        with self._frame_lock:
                            self._last_frame = jpeg_data.tobytes()
                            self._last_frame_time = time.time()

                    # Only run AI inference when enabled
                    if should_run_ai:
                        # Face tracking
                        if self._face_tracking_enabled and self._head_tracker is not None:
                            face_detect_count += 1
                            face_detected = self._process_face_tracking(frame, current_time)

                            # Update adaptive frame rate manager
                            self._frame_rate_manager.update(face_detected=face_detected)

                            # Check for face detection state change and notify callback
                            # Use is_face_detected() which considers face_lost_delay
                            current_face_state = self.is_face_detected()
                            if current_face_state != self._last_face_detected_state:
                                self._last_face_detected_state = current_face_state
                                if self._face_state_callback:
                                    try:
                                        self._face_state_callback()
                                    except Exception as e:
                                        _LOGGER.debug("Face state callback error: %s", e)

                        # Handle smooth interpolation when face lost
                        self._process_face_lost_interpolation(current_time)

                    # Gesture detection (runs independently of face detection)
                    # Uses its own frame rate control via should_run_gesture_detection()
                    if (
                        self._gesture_detection_enabled
                        and self._gesture_detector is not None
                        and self._frame_rate_manager.should_run_gesture_detection()
                    ):
                        self._process_gesture_detection(frame)

                    # Log stats every 30 seconds
                    if current_time - last_log_time >= 30.0:
                        fps = frame_count / (current_time - last_log_time)
                        detect_fps = face_detect_count / (current_time - last_log_time)
                        mode = self._frame_rate_manager.current_mode.value.upper()
                        no_face = self._frame_rate_manager.state.no_face_duration
                        _LOGGER.debug(
                            "Camera: %.1f fps, AI: %.1f fps (%s), no_face: %.0fs", fps, detect_fps, mode, no_face
                        )
                        frame_count = 0
                        face_detect_count = 0
                        last_log_time = current_time

                # Sleep to maintain target FPS (use adaptive rate)
                sleep_time = self._frame_rate_manager.get_sleep_interval()
                time.sleep(sleep_time)

            except Exception as e:
                _LOGGER.error("Error capturing frame: %s", e)
                time.sleep(1.0)

        _LOGGER.info("Camera capture thread stopped")

    def _should_run_ai_inference(self, current_time: float) -> bool:
        """Determine if AI inference (face/gesture detection) should run."""
        return self._frame_rate_manager.should_run_inference()

    def _has_stream_clients(self) -> bool:
        """Check if there are active MJPEG stream clients."""
        with self._stream_client_lock:
            return len(self._active_stream_clients) > 0

    def _register_stream_client(self) -> int:
        """Register a new stream client and return its ID."""
        with self._stream_client_lock:
            client_id = self._next_client_id
            self._next_client_id += 1
            self._active_stream_clients.add(client_id)
            _LOGGER.debug("Stream client registered: %d (total: %d)", client_id, len(self._active_stream_clients))
            return client_id

    def _unregister_stream_client(self, client_id: int) -> None:
        """Unregister a stream client."""
        with self._stream_client_lock:
            self._active_stream_clients.discard(client_id)
            _LOGGER.debug("Stream client unregistered: %d (total: %d)", client_id, len(self._active_stream_clients))

    @property
    def stream_client_count(self) -> int:
        """Get the number of active stream clients."""
        with self._stream_client_lock:
            return len(self._active_stream_clients)

    def _process_face_tracking(self, frame: np.ndarray, current_time: float) -> bool:
        """Process face tracking on a frame.

        Returns:
            True if face was detected, False otherwise
        """
        if self._head_tracker is None or self.reachy_mini is None:
            return False

        try:
            face_center, _confidence = self._head_tracker.get_head_position(frame)

            if face_center is not None:
                # Face detected - notify interpolator
                self._face_interpolator.on_face_detected(current_time)

                # Convert normalized coordinates to pixel coordinates
                h, w = frame.shape[:2]
                eye_center_norm = (face_center + 1) / 2

                eye_center_pixels = [
                    int(eye_center_norm[0] * w),
                    int(eye_center_norm[1] * h),
                ]

                # Get the head pose needed to look at the target
                target_pose = self.reachy_mini.look_at_image(
                    eye_center_pixels[0],
                    eye_center_pixels[1],
                    duration=0.0,
                    perform_movement=False,
                )

                # Extract translation and rotation from target pose
                translation = target_pose[:3, 3]
                rotation = R.from_matrix(target_pose[:3, :3]).as_euler("xyz", degrees=False)

                # Update interpolator with new offsets (handles scaling and compensation)
                self._face_interpolator.update_offsets(translation, rotation)

                # Sync to thread-safe storage
                with self._face_tracking_lock:
                    self._face_tracking_offsets = list(self._face_interpolator.get_offsets())

                return True

            return False

        except Exception as e:
            _LOGGER.debug("Face tracking error: %s", e)
            return False

    def _process_face_lost_interpolation(self, current_time: float) -> None:
        """Handle smooth interpolation back to neutral when face is lost."""
        # Delegate to interpolator
        self._face_interpolator.process_face_lost(current_time)

        # Sync interpolated offsets to thread-safe storage
        with self._face_tracking_lock:
            self._face_tracking_offsets = list(self._face_interpolator.get_offsets())

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

    def set_face_tracking_enabled(self, enabled: bool) -> None:
        """Enable or disable face tracking."""
        if self._face_tracking_enabled == enabled:
            return  # No change, skip logging
        self._face_tracking_enabled = enabled
        if not enabled:
            # Start interpolation back to neutral
            self._face_interpolator.reset_interpolation()
        _LOGGER.info("Face tracking %s", "enabled" if enabled else "disabled")

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
        """Process gesture detection on a frame."""
        if self._gesture_detector is None:
            return

        try:
            # Detect gesture
            detected_gesture, confidence = self._gesture_detector.detect(frame)

            # Update current gesture state
            state_changed = False
            with self._gesture_lock:
                old_gesture = self._current_gesture
                if detected_gesture.value != "no_gesture":
                    self._current_gesture = detected_gesture.value
                    self._gesture_confidence = confidence
                    if old_gesture != detected_gesture.value:
                        state_changed = True
                        _LOGGER.info("Gesture detected: %s (%.1f%%)", detected_gesture.value, confidence * 100)
                else:
                    if self._current_gesture != "none":
                        state_changed = True
                        _LOGGER.info("Gesture cleared (no gesture detected)")
                    self._current_gesture = "none"
                    self._gesture_confidence = 0.0

            # Notify entity registry to push update to Home Assistant
            if state_changed and self._gesture_state_callback:
                try:
                    self._gesture_state_callback()
                except Exception:
                    pass  # Ignore callback errors

            # Trigger gesture actions (emotions, listening, etc.)
            if state_changed and self._gesture_action_callback:
                try:
                    self._gesture_action_callback(self._current_gesture, self._gesture_confidence)
                except Exception as e:
                    _LOGGER.debug("Gesture action callback error: %s", e)

        except Exception as e:
            _LOGGER.warning("Gesture detection error: %s", e)

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
        self._gesture_detection_enabled = enabled
        if not enabled:
            with self._gesture_lock:
                self._current_gesture = "none"
                self._gesture_confidence = 0.0
        _LOGGER.info("Gesture detection %s", "enabled" if enabled else "disabled")

    def set_gesture_state_callback(self, callback) -> None:
        """Set callback to notify when gesture state changes."""
        self._gesture_state_callback = callback

    def set_gesture_action_callback(self, callback) -> None:
        """Set callback for gesture action handling.

        The callback receives (gesture_name: str, confidence: float).
        """
        self._gesture_action_callback = callback

    def set_face_state_callback(self, callback) -> None:
        """Set callback to notify when face detection state changes."""
        self._face_state_callback = callback

    def _get_camera_frame(self) -> np.ndarray | None:
        """Get a frame from Reachy Mini's camera."""
        if self.reachy_mini is None:
            # Return a test pattern if no robot connected
            return self._generate_test_frame()

        try:
            # Use GStreamer lock to prevent concurrent access conflicts
            acquired = self._gstreamer_lock.acquire(timeout=0.01)
            if acquired:
                try:
                    frame = self.reachy_mini.media.get_frame()
                    return frame
                finally:
                    self._gstreamer_lock.release()
            else:
                _LOGGER.debug("GStreamer lock busy, skipping camera frame")
                # Flush SDK video buffer to prevent buffer overflow during lock contention
                try:
                    if hasattr(self.reachy_mini.media, "flush"):
                        self.reachy_mini.media.flush()
                    elif hasattr(self.reachy_mini.media, "flush_video"):
                        self.reachy_mini.media.flush_video()
                except Exception:
                    pass
                return None
        except Exception as e:
            _LOGGER.debug("Failed to get camera frame: %s", e)
            return None

    def _generate_test_frame(self) -> np.ndarray:
        """Generate a test pattern frame when no camera is available."""
        # Create a simple test pattern
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Add some visual elements
        cv2.putText(
            frame,
            "Reachy Mini Camera",
            (150, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            "No camera connected",
            (180, 280),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (128, 128, 128),
            1,
        )

        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            timestamp,
            (220, 350),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            1,
        )

        return frame

    def get_snapshot(self) -> bytes | None:
        """Get the latest frame as JPEG bytes."""
        with self._frame_lock:
            return self._last_frame

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP client connections."""
        try:
            # Read HTTP request
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            request = request_line.decode("utf-8", errors="ignore").strip()

            # Read headers (we don't need them but must consume them)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line in {b"\r\n", b"\n", b""}:
                    break

            # Parse request path
            parts = request.split(" ")
            if len(parts) >= 2:
                path = parts[1]
            else:
                path = "/"

            _LOGGER.debug("HTTP request: %s", request)

            if path == "/stream":
                await self._handle_stream(writer)
            elif path == "/snapshot":
                await self._handle_snapshot(writer)
            else:
                await self._handle_index(writer)

        except TimeoutError:
            _LOGGER.debug("Client connection timeout")
        except ConnectionResetError:
            _LOGGER.debug("Client connection reset")
        except Exception as e:
            _LOGGER.error("Error handling client: %s", e)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_index(self, writer: asyncio.StreamWriter) -> None:
        """Handle index page request."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Reachy Mini Camera</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d4ff; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        .stream {{ width: 100%; max-width: 640px; border: 2px solid #00d4ff; border-radius: 8px; }}
        a {{ color: #00d4ff; }}
        .info {{ background: #16213e; padding: 20px; border-radius: 8px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Reachy Mini Camera</h1>
        <img class="stream" src="/stream" alt="Camera Stream">
        <div class="info">
            <h3>Endpoints:</h3>
            <ul>
                <li><a href="/stream">/stream</a> - MJPEG video stream</li>
                <li><a href="/snapshot">/snapshot</a> - Single JPEG snapshot</li>
            </ul>
            <h3>Home Assistant Integration:</h3>
            <p>Add a Generic Camera with URL: <code>http://&lt;ip&gt;:{self.port}/stream</code></p>
        </div>
    </div>
</body>
</html>"""

        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(html)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )

        writer.write(response.encode("utf-8"))
        writer.write(html.encode("utf-8"))
        await writer.drain()

    async def _handle_snapshot(self, writer: asyncio.StreamWriter) -> None:
        """Handle snapshot request - return single JPEG image."""
        jpeg_data = self.get_snapshot()

        if jpeg_data is None:
            response = (
                "HTTP/1.1 503 Service Unavailable\r\n"
                "Content-Type: text/plain\r\n"
                "Connection: close\r\n"
                "\r\n"
                "No frame available"
            )
            writer.write(response.encode("utf-8"))
        else:
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg_data)}\r\n"
                "Cache-Control: no-cache, no-store, must-revalidate\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            writer.write(response.encode("utf-8"))
            writer.write(jpeg_data)

        await writer.drain()

    async def _handle_stream(self, writer: asyncio.StreamWriter) -> None:
        """Handle MJPEG stream request."""
        # Register this client for tracking
        client_id = self._register_stream_client()

        # Send MJPEG headers
        response = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()

        _LOGGER.debug("Started MJPEG stream for client %d", client_id)

        last_sent_time = 0

        try:
            while self._running:
                # Get latest frame
                with self._frame_lock:
                    jpeg_data = self._last_frame
                    frame_time = self._last_frame_time

                # Only send if we have a new frame
                if jpeg_data is not None and frame_time > last_sent_time:
                    # Send MJPEG frame
                    frame_header = (
                        f"--{MJPEG_BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg_data)}\r\n\r\n"
                    )

                    writer.write(frame_header.encode("utf-8"))
                    writer.write(jpeg_data)
                    writer.write(b"\r\n")
                    await writer.drain()

                    last_sent_time = frame_time

                # Small delay to prevent busy loop
                await asyncio.sleep(0.01)

        except (ConnectionResetError, BrokenPipeError):
            _LOGGER.debug("Client %d disconnected from stream", client_id)
        except Exception as e:
            _LOGGER.error("Error in MJPEG stream for client %d: %s", client_id, e)
        finally:
            # Always unregister client when done
            self._unregister_stream_client(client_id)

        _LOGGER.debug("Ended MJPEG stream for client %d", client_id)
