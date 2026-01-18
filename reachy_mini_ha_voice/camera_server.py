"""
MJPEG Camera Server for Reachy Mini with Face Tracking.

This module provides an HTTP server that streams camera frames from Reachy Mini
as MJPEG, which can be integrated with Home Assistant via Generic Camera.
Also provides face tracking for head movement control.

Reference: reachy_mini_conversation_app/src/reachy_mini_conversation_app/camera_worker.py
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Tuple, List, TYPE_CHECKING

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as R

# Import SDK interpolation utilities (same as conversation_app)
try:
    from reachy_mini.utils.interpolation import linear_pose_interpolation
    SDK_INTERPOLATION_AVAILABLE = True
except ImportError:
    SDK_INTERPOLATION_AVAILABLE = False

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
        reachy_mini: Optional["ReachyMini"] = None,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,  # 15fps for smooth face tracking
        quality: int = 80,
        enable_face_tracking: bool = True,
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
        """
        self.reachy_mini = reachy_mini
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality
        self.enable_face_tracking = enable_face_tracking

        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._frame_interval = 1.0 / fps
        self._last_frame: Optional[bytes] = None
        self._last_frame_time: float = 0
        self._frame_lock = threading.Lock()

        # Frame capture thread
        self._capture_thread: Optional[threading.Thread] = None

        # Face tracking state
        self._head_tracker = None
        self._face_tracking_enabled = True  # Enabled by default for always-on face tracking
        self._face_tracking_offsets: List[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self._face_tracking_lock = threading.Lock()

        # Gesture detection state
        self._gesture_detector = None
        self._gesture_detection_enabled = True
        self._current_gesture = "none"
        self._gesture_confidence = 0.0
        self._gesture_lock = threading.Lock()
        self._gesture_frame_counter = 0
        self._gesture_detection_interval = 3  # Run gesture detection every N frames
        self._gesture_state_callback = None  # Callback to notify entity registry

        # Face detection state callback (similar to gesture)
        self._face_state_callback = None  # Callback to notify entity registry
        self._last_face_detected_state = False  # Track previous state for change detection

        # Face tracking timing (smooth interpolation when face lost)
        self._last_face_detected_time: Optional[float] = None
        self._interpolation_start_time: Optional[float] = None
        self._interpolation_start_pose: Optional[np.ndarray] = None
        self._face_lost_delay = 1.0  # Reduced from 2.0s to 1.0s for faster response
        self._interpolation_duration = 0.8  # Reduced from 1.0s to 0.8s for faster return

        # Offset scaling (same as conversation_app)
        self._offset_scale = 0.6

        # =====================================================================
        # Resource optimization: Adaptive frame rate for face tracking
        # =====================================================================
        # High frequency when: face detected, in conversation, or recently active
        # Low frequency when: idle and no face for extended period
        # Ultra-low when: idle for very long time (just MJPEG stream, minimal AI)
        self._fps_high = fps  # Normal tracking rate (15fps)
        self._fps_low = 2     # Low power rate (2fps) - periodic face check
        self._fps_idle = 0.5  # Ultra-low power (0.5fps) - minimal CPU usage
        self._current_fps = fps

        # Conversation state (set by voice assistant)
        self._in_conversation = False
        self._conversation_lock = threading.Lock()

        # Adaptive tracking timing
        self._no_face_duration = 0.0  # How long since last face detection
        self._low_power_threshold = 5.0   # Switch to low power after 5s without face
        self._idle_threshold = 30.0       # Switch to idle mode after 30s without face
        self._last_face_check_time = 0.0

        # Skip AI inference in idle mode (only stream MJPEG)
        self._ai_enabled = True

    async def start(self) -> None:
        """Start the MJPEG camera server."""
        if self._running:
            _LOGGER.warning("Camera server already running")
            return

        self._running = True

        # Initialize head tracker if face tracking enabled
        if self.enable_face_tracking:
            try:
                from .head_tracker import HeadTracker
                self._head_tracker = HeadTracker()
                _LOGGER.info("Face tracking enabled with YOLO head tracker")
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
        self._capture_thread = threading.Thread(
            target=self._capture_frames,
            daemon=True,
            name="camera-capture"
        )
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

    async def stop(self) -> None:
        """Stop the MJPEG camera server."""
        self._running = False

        if self._capture_thread:
            # Wait up to 3 seconds - longer than max sleep time (2s in idle mode)
            self._capture_thread.join(timeout=3.0)
            if self._capture_thread.is_alive():
                _LOGGER.warning("Camera capture thread did not stop cleanly")
            self._capture_thread = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        _LOGGER.info("MJPEG Camera server stopped")

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

                # Only get frame if needed (AI inference or MJPEG streaming)
                frame = self._get_camera_frame() if should_run_ai or self._has_stream_clients() else None

                if frame is not None:
                    frame_count += 1

                    # Encode frame as JPEG for streaming
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                    success, jpeg_data = cv2.imencode('.jpg', frame, encode_params)

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

                            # Update adaptive timing based on detection result
                            if face_detected:
                                self._no_face_duration = 0.0
                                self._current_fps = self._fps_high
                                self._ai_enabled = True
                            else:
                                # Accumulate no-face duration
                                if self._last_face_detected_time is not None:
                                    self._no_face_duration = current_time - self._last_face_detected_time
                                else:
                                    self._no_face_duration += 1.0 / self._current_fps

                                # Adaptive power mode
                                if self._no_face_duration > self._idle_threshold:
                                    self._current_fps = self._fps_idle
                                elif self._no_face_duration > self._low_power_threshold:
                                    self._current_fps = self._fps_low

                            self._last_face_check_time = current_time

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

                        # Gesture detection (only when face detected recently)
                        if (self._gesture_detection_enabled
                                and self._gesture_detector is not None
                                and self._no_face_duration < 5.0):
                            # Only detect gestures when someone is present
                            self._gesture_frame_counter += 1
                            if self._gesture_frame_counter >= self._gesture_detection_interval:
                                self._gesture_frame_counter = 0
                                self._process_gesture_detection(frame)

                    # Log stats every 30 seconds
                    if current_time - last_log_time >= 30.0:
                        fps = frame_count / (current_time - last_log_time)
                        detect_fps = face_detect_count / (current_time - last_log_time)
                        if self._current_fps == self._fps_high:
                            mode = "HIGH"
                        elif self._current_fps == self._fps_low:
                            mode = "LOW"
                        else:
                            mode = "IDLE"
                        _LOGGER.debug(
                            "Camera: %.1f fps, AI: %.1f fps (%s), no_face: %.0fs",
                            fps, detect_fps, mode, self._no_face_duration)
                        frame_count = 0
                        face_detect_count = 0
                        last_log_time = current_time

                # Sleep to maintain target FPS (use current adaptive rate)
                sleep_time = 1.0 / self._current_fps
                time.sleep(sleep_time)

            except Exception as e:
                _LOGGER.error("Error capturing frame: %s", e)
                time.sleep(1.0)

        _LOGGER.info("Camera capture thread stopped")

    def _should_run_ai_inference(self, current_time: float) -> bool:
        """Determine if AI inference (face/gesture detection) should run.

        Returns True if:
        - In conversation mode (always run)
        - Face was recently detected
        - Periodic check in low power mode
        """
        # Always run during conversation
        with self._conversation_lock:
            if self._in_conversation:
                return True

        # High frequency mode: run every frame
        if self._current_fps == self._fps_high:
            return True

        # Low/idle power mode: run periodically
        time_since_last = current_time - self._last_face_check_time
        return time_since_last >= (1.0 / self._current_fps)

    def _has_stream_clients(self) -> bool:
        """Check if there are active MJPEG stream clients."""
        # For now, always return True to keep stream available
        # Could be optimized to track actual client connections
        return True

    def _process_face_tracking(self, frame: np.ndarray, current_time: float) -> bool:
        """Process face tracking on a frame.

        Returns:
            True if face was detected, False otherwise
        """
        if self._head_tracker is None or self.reachy_mini is None:
            return False

        try:
            face_center, confidence = self._head_tracker.get_head_position(frame)

            if face_center is not None:
                # Face detected - update tracking
                self._last_face_detected_time = current_time
                self._interpolation_start_time = None  # Stop any interpolation

                # Convert normalized coordinates to pixel coordinates
                h, w = frame.shape[:2]
                eye_center_norm = (face_center + 1) / 2

                eye_center_pixels = [
                    eye_center_norm[0] * w,
                    eye_center_norm[1] * h,
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

                # Scale down for smoother tracking (same as conversation_app)
                translation = translation * self._offset_scale
                rotation = rotation * self._offset_scale

                # Apply pitch offset compensation (robot tends to look up)
                # rotation[1] is pitch in xyz euler order
                # Positive pitch = look down in robot coordinate system
                pitch_offset_rad = np.radians(9.0)  # Look down 9 degrees
                rotation[1] += pitch_offset_rad

                # Apply yaw offset compensation (robot tends to look to user's right)
                # rotation[2] is yaw in xyz euler order
                # Negative yaw = turn right (towards user's left from robot's perspective)
                yaw_offset_rad = np.radians(-7.0)  # Turn right 7 degrees
                rotation[2] += yaw_offset_rad

                # Update face tracking offsets
                with self._face_tracking_lock:
                    self._face_tracking_offsets = [
                        float(translation[0]),
                        float(translation[1]),
                        float(translation[2]),
                        float(rotation[0]),
                        float(rotation[1]),
                        float(rotation[2]),
                    ]

                return True

            return False

        except Exception as e:
            _LOGGER.debug("Face tracking error: %s", e)
            return False

    def _process_face_lost_interpolation(self, current_time: float) -> None:
        """Handle smooth interpolation back to neutral when face is lost."""
        if self._last_face_detected_time is None:
            return

        time_since_face_lost = current_time - self._last_face_detected_time

        if time_since_face_lost < self._face_lost_delay:
            return  # Still within delay period, keep current offsets

        # Start interpolation if not already started
        if self._interpolation_start_time is None:
            self._interpolation_start_time = current_time
            # Capture current pose as start of interpolation
            with self._face_tracking_lock:
                current_offsets = self._face_tracking_offsets.copy()

            # Convert to 4x4 pose matrix
            pose_matrix = np.eye(4, dtype=np.float32)
            pose_matrix[:3, 3] = current_offsets[:3]
            pose_matrix[:3, :3] = R.from_euler("xyz", current_offsets[3:]).as_matrix()
            self._interpolation_start_pose = pose_matrix

        # Calculate interpolation progress
        elapsed = current_time - self._interpolation_start_time
        t = min(1.0, elapsed / self._interpolation_duration)

        # Interpolate to neutral (identity matrix)
        if self._interpolation_start_pose is not None:
            neutral_pose = np.eye(4, dtype=np.float32)
            interpolated_pose = self._linear_pose_interpolation(
                self._interpolation_start_pose, neutral_pose, t
            )

            # Extract translation and rotation
            translation = interpolated_pose[:3, 3]
            rotation = R.from_matrix(interpolated_pose[:3, :3]).as_euler("xyz", degrees=False)

            with self._face_tracking_lock:
                self._face_tracking_offsets = [
                    float(translation[0]),
                    float(translation[1]),
                    float(translation[2]),
                    float(rotation[0]),
                    float(rotation[1]),
                    float(rotation[2]),
                ]

        # Reset when interpolation complete
        if t >= 1.0:
            self._last_face_detected_time = None
            self._interpolation_start_time = None
            self._interpolation_start_pose = None

    def _linear_pose_interpolation(
        self, start: np.ndarray, end: np.ndarray, t: float
    ) -> np.ndarray:
        """Linear interpolation between two 4x4 pose matrices.

        Uses SDK's linear_pose_interpolation if available, otherwise falls back
        to manual SLERP implementation.
        """
        if SDK_INTERPOLATION_AVAILABLE:
            return linear_pose_interpolation(start, end, t)

        # Fallback: manual interpolation
        # Interpolate translation
        start_trans = start[:3, 3]
        end_trans = end[:3, 3]
        interp_trans = start_trans * (1 - t) + end_trans * t

        # Interpolate rotation using SLERP
        start_rot = R.from_matrix(start[:3, :3])
        end_rot = R.from_matrix(end[:3, :3])

        # Use scipy's slerp - create Rotation array from list
        from scipy.spatial.transform import Slerp
        key_rots = R.from_quat(np.array([start_rot.as_quat(), end_rot.as_quat()]))
        slerp = Slerp([0, 1], key_rots)
        interp_rot = slerp(t)

        # Build result matrix
        result = np.eye(4, dtype=np.float32)
        result[:3, :3] = interp_rot.as_matrix()
        result[:3, 3] = interp_trans

        return result

    # =========================================================================
    # Public API for face tracking
    # =========================================================================

    def get_face_tracking_offsets(self) -> Tuple[float, float, float, float, float, float]:
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
        if self._last_face_detected_time is None:
            return False

        # Face is considered detected if we saw it recently
        time_since_detected = time.time() - self._last_face_detected_time
        return time_since_detected < self._face_lost_delay

    def set_face_tracking_enabled(self, enabled: bool) -> None:
        """Enable or disable face tracking."""
        if self._face_tracking_enabled == enabled:
            return  # No change, skip logging
        self._face_tracking_enabled = enabled
        if not enabled:
            # Start interpolation back to neutral
            self._last_face_detected_time = time.time()
            self._interpolation_start_time = None
        _LOGGER.info("Face tracking %s", "enabled" if enabled else "disabled")

    def set_conversation_mode(self, in_conversation: bool) -> None:
        """Set conversation mode for adaptive face tracking.

        When in conversation mode, face tracking runs at high frequency
        regardless of whether a face is currently detected.

        Args:
            in_conversation: True when voice assistant is actively conversing
        """
        with self._conversation_lock:
            self._in_conversation = in_conversation

        if in_conversation:
            # Immediately switch to high frequency mode
            self._current_fps = self._fps_high
            self._ai_enabled = True
            self._no_face_duration = 0.0  # Reset no-face timer
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
                        _LOGGER.debug(
                            "Gesture: %s (%.0f%%)",
                            detected_gesture.value, confidence * 100)
                else:
                    if self._current_gesture != "none":
                        state_changed = True
                    self._current_gesture = "none"
                    self._gesture_confidence = 0.0

            # Notify entity registry to push update to Home Assistant
            if state_changed and self._gesture_state_callback:
                try:
                    self._gesture_state_callback()
                except Exception:
                    pass  # Ignore callback errors

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

    def set_face_state_callback(self, callback) -> None:
        """Set callback to notify when face detection state changes."""
        self._face_state_callback = callback

    def _get_camera_frame(self) -> Optional[np.ndarray]:
        """Get a frame from Reachy Mini's camera."""
        if self.reachy_mini is None:
            # Return a test pattern if no robot connected
            return self._generate_test_frame()

        try:
            frame = self.reachy_mini.media.get_frame()
            return frame
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

    def get_snapshot(self) -> Optional[bytes]:
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
            request_line = await asyncio.wait_for(
                reader.readline(),
                timeout=10.0
            )
            request = request_line.decode('utf-8', errors='ignore').strip()

            # Read headers (we don't need them but must consume them)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line == b'\r\n' or line == b'\n' or line == b'':
                    break

            # Parse request path
            parts = request.split(' ')
            if len(parts) >= 2:
                path = parts[1]
            else:
                path = '/'

            _LOGGER.debug("HTTP request: %s", request)

            if path == '/stream':
                await self._handle_stream(writer)
            elif path == '/snapshot':
                await self._handle_snapshot(writer)
            else:
                await self._handle_index(writer)

        except asyncio.TimeoutError:
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

        writer.write(response.encode('utf-8'))
        writer.write(html.encode('utf-8'))
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
            writer.write(response.encode('utf-8'))
        else:
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg_data)}\r\n"
                "Cache-Control: no-cache, no-store, must-revalidate\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            writer.write(response.encode('utf-8'))
            writer.write(jpeg_data)

        await writer.drain()

    async def _handle_stream(self, writer: asyncio.StreamWriter) -> None:
        """Handle MJPEG stream request."""
        # Send MJPEG headers
        response = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        )
        writer.write(response.encode('utf-8'))
        await writer.drain()

        _LOGGER.debug("Started MJPEG stream")

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
                        f"--{MJPEG_BOUNDARY}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(jpeg_data)}\r\n"
                        "\r\n"
                    )

                    writer.write(frame_header.encode('utf-8'))
                    writer.write(jpeg_data)
                    writer.write(b"\r\n")
                    await writer.drain()

                    last_sent_time = frame_time

                # Small delay to prevent busy loop
                await asyncio.sleep(0.01)

        except (ConnectionResetError, BrokenPipeError):
            _LOGGER.debug("Client disconnected from stream")
        except Exception as e:
            _LOGGER.error("Error in MJPEG stream: %s", e)

        _LOGGER.debug("Ended MJPEG stream")
