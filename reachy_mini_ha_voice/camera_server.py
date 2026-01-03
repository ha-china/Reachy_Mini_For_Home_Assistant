"""
MJPEG Camera Server for Reachy Mini.

This module provides an HTTP server that streams camera frames from Reachy Mini
as MJPEG, which can be integrated with Home Assistant via Generic Camera.
"""

import asyncio
import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

_LOGGER = logging.getLogger(__name__)

# MJPEG boundary string
MJPEG_BOUNDARY = "frame"


class MJPEGCameraServer:
    """
    MJPEG streaming server for Reachy Mini camera.

    Provides HTTP endpoints:
    - /stream - MJPEG video stream
    - /snapshot - Single JPEG image
    - / - Simple status page
    """

    def __init__(
        self,
        reachy_mini: Optional["ReachyMini"] = None,
        host: str = "0.0.0.0",
        port: int = 8081,
        fps: int = 15,
        quality: int = 80,
    ):
        """
        Initialize the MJPEG camera server.

        Args:
            reachy_mini: Reachy Mini robot instance (can be None for testing)
            host: Host address to bind to
            port: Port number for the HTTP server
            fps: Target frames per second for the stream
            quality: JPEG quality (1-100)
        """
        self.reachy_mini = reachy_mini
        self.host = host
        self.port = port
        self.fps = fps
        self.quality = quality

        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._frame_interval = 1.0 / fps
        self._last_frame: Optional[bytes] = None
        self._last_frame_time: float = 0
        self._frame_lock = threading.Lock()

        # Frame capture thread
        self._capture_thread: Optional[threading.Thread] = None

    async def start(self) -> None:
        """Start the MJPEG camera server."""
        if self._running:
            _LOGGER.warning("Camera server already running")
            return

        self._running = True

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
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        _LOGGER.info("MJPEG Camera server stopped")

    def _capture_frames(self) -> None:
        """Background thread to capture frames from Reachy Mini."""
        _LOGGER.info("Starting camera capture thread")

        while self._running:
            try:
                frame = self._get_camera_frame()

                if frame is not None:
                    # Encode frame as JPEG
                    encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.quality]
                    success, jpeg_data = cv2.imencode('.jpg', frame, encode_params)

                    if success:
                        with self._frame_lock:
                            self._last_frame = jpeg_data.tobytes()
                            self._last_frame_time = time.time()

                # Sleep to maintain target FPS
                time.sleep(self._frame_interval)

            except Exception as e:
                _LOGGER.error("Error capturing frame: %s", e)
                time.sleep(0.5)

        _LOGGER.info("Camera capture thread stopped")

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
