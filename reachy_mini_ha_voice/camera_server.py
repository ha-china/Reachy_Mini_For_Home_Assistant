"""
MJPEG Camera Server for Reachy Mini with Face Tracking and Gesture Detection.

This module provides an HTTP server that streams camera frames from Reachy Mini
as MJPEG, which can be integrated with Home Assistant via Generic Camera.
Also provides face tracking for head movement control and gesture detection.

Reference: reachy_mini_conversation_app/src/reachy_mini_conversation_app/camera_worker.py
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Tuple, List, Callable, TYPE_CHECKING

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
    MJPEG streaming server for Reachy Mini camera with face tracking and gesture detection.

    Provides HTTP endpoints:
    - /stream - MJPEG video stream
    - /snapshot - Single JPEG image
    - / - Simple status page
    
    Also provides face tracking offsets for head movement control
    and gesture detection for interaction (thumbs up, open palm/stop).
    """

    def __init__(
        self,
        reachy_mini: Optional["ReachyMini"] = None,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,  # 15fps for smooth face tracking
        quality: int = 80,
        enable_face_tracking: bool = True,
        enable_gesture_detection: bool = True,
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
            enable_gesture_detection: Enable gesture detection (thumbs up, stop)
        """
        self.reachy_mini = reachy_mini
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality
        self.enable_face_tracking = enable_face_tracking
        self.enable_gesture_detection = enable_gesture_detection

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
        
        # Face tracking timing (smooth interpolation when face lost)
        self._last_face_detected_time: Optional[float] = None
        self._interpolation_start_time: Optional[float] = None
        self._interpolation_start_pose: Optional[np.ndarray] = None
        self._face_lost_delay = 1.0  # Reduced from 2.0s to 1.0s for faster response
        self._interpolation_duration = 0.8  # Reduced from 1.0s to 0.8s for faster return
        
        # Offset scaling (same as conversation_app)
        self._offset_scale = 0.6
        
        # Gesture detection state
        self._gesture_detector = None
        self._gesture_detection_enabled = True

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
        
        # Initialize gesture detector if enabled
        if self.enable_gesture_detection:
            try:
                from .gesture_detector import GestureDetector
                self._gesture_detector = GestureDetector()
                if self._gesture_detector.is_available:
                    _LOGGER.info("Gesture detection enabled with MediaPipe Hands")
                else:
                    _LOGGER.warning("Gesture detection not available (MediaPipe not installed)")
                    self._gesture_detector = None
            except ImportError as e:
                _LOGGER.warning("Failed to import gesture detector: %s", e)
                self._gesture_detector = None
            except Exception as e:
                _LOGGER.warning("Failed to initialize gesture detector: %s", e)
                self._gesture_detector = None
        else:
            _LOGGER.info("Gesture detection disabled by configuration")

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
            self._capture_thread.join(timeout=0.5)
            self._capture_thread = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        _LOGGER.info("MJPEG Camera server stopped")

    def _capture_frames(self) -> None:
        """Background thread to capture frames from Reachy Mini and do face tracking + gesture detection."""
        _LOGGER.info("Starting camera capture thread (face_tracking=%s, gesture_detection=%s)", 
                    self._face_tracking_enabled, self._gesture_detection_enabled)

        frame_count = 0
        last_log_time = time.time()

        while self._running:
            try:
                current_time = time.time()
                frame = self._get_camera_frame()

                if frame is not None:
                    frame_count += 1
                    
                    # Encode frame as JPEG for streaming
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                    success, jpeg_data = cv2.imencode('.jpg', frame, encode_params)

                    if success:
                        with self._frame_lock:
                            self._last_frame = jpeg_data.tobytes()
                            self._last_frame_time = time.time()
                    
                    # Do face tracking if enabled
                    if self._face_tracking_enabled and self._head_tracker is not None:
                        self._process_face_tracking(frame, current_time)
                    
                    # Handle smooth interpolation when face lost
                    self._process_face_lost_interpolation(current_time)
                    
                    # Do gesture detection if enabled (every other frame to save CPU)
                    if self._gesture_detection_enabled and self._gesture_detector is not None:
                        if frame_count % 2 == 0:  # Process every other frame
                            self._gesture_detector.process_frame(frame)
                    
                    # Log stats every 10 seconds
                    if current_time - last_log_time >= 10.0:
                        fps = frame_count / (current_time - last_log_time)
                        _LOGGER.debug("Camera: %.1f fps, face_tracking=%s, gesture_detection=%s",
                                     fps, self._face_tracking_enabled, self._gesture_detection_enabled)
                        frame_count = 0
                        last_log_time = current_time

                # Sleep to maintain target FPS
                time.sleep(self._frame_interval)

            except Exception as e:
                _LOGGER.error("Error capturing frame: %s", e)
                time.sleep(0.5)

        _LOGGER.info("Camera capture thread stopped")
    
    def _process_face_tracking(self, frame: np.ndarray, current_time: float) -> None:
        """Process face tracking on a frame."""
        if self._head_tracker is None or self.reachy_mini is None:
            return
        
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
        
        except Exception as e:
            _LOGGER.debug("Face tracking error: %s", e)
    
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
    
    def set_face_tracking_enabled(self, enabled: bool) -> None:
        """Enable or disable face tracking."""
        self._face_tracking_enabled = enabled
        if not enabled:
            # Start interpolation back to neutral
            self._last_face_detected_time = time.time()
            self._interpolation_start_time = None
        _LOGGER.info("Face tracking %s", "enabled" if enabled else "disabled")

    # =========================================================================
    # Public API for gesture detection
    # =========================================================================
    
    def get_current_gesture(self) -> str:
        """Get current detected gesture as string.
        
        Returns:
            Gesture name: "none", "thumbs_up", "open_palm"
        """
        if self._gesture_detector is None:
            return "none"
        return self._gesture_detector.current_gesture.value
    
    def set_gesture_detection_enabled(self, enabled: bool) -> None:
        """Enable or disable gesture detection."""
        self._gesture_detection_enabled = enabled
        _LOGGER.info("Gesture detection %s", "enabled" if enabled else "disabled")
    
    def set_gesture_callbacks(
        self,
        on_thumbs_up: Optional[Callable[[], None]] = None,
        on_thumbs_down: Optional[Callable[[], None]] = None,
        on_open_palm: Optional[Callable[[], None]] = None,
        on_fist: Optional[Callable[[], None]] = None,
        on_peace: Optional[Callable[[], None]] = None,
        on_ok: Optional[Callable[[], None]] = None,
        on_pointing_up: Optional[Callable[[], None]] = None,
        on_rock: Optional[Callable[[], None]] = None,
        on_call: Optional[Callable[[], None]] = None,
        on_three: Optional[Callable[[], None]] = None,
        on_four: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set gesture detection callbacks."""
        if self._gesture_detector is not None:
            self._gesture_detector.set_callbacks(
                on_thumbs_up=on_thumbs_up,
                on_thumbs_down=on_thumbs_down,
                on_open_palm=on_open_palm,
                on_fist=on_fist,
                on_peace=on_peace,
                on_ok=on_ok,
                on_pointing_up=on_pointing_up,
                on_rock=on_rock,
                on_call=on_call,
                on_three=on_three,
                on_four=on_four,
            )

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
