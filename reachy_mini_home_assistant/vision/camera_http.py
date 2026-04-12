"""HTTP endpoint helpers for `MJPEGCameraServer`."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


def build_index_html(server: "MJPEGCameraServer") -> str:
    return f"""<!DOCTYPE html>
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
            <p>Add a Generic Camera with URL: <code>http://&lt;ip&gt;:{server.port}/stream</code></p>
        </div>
    </div>
</body>
</html>"""


async def handle_client(server: "MJPEGCameraServer", reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
        request = request_line.decode("utf-8", errors="ignore").strip()
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line in {b"\r\n", b"\n", b""}:
                break
        parts = request.split(" ")
        path = parts[1] if len(parts) >= 2 else "/"
        _LOGGER.debug("HTTP request: %s", request)
        if path == "/stream":
            await handle_stream(server, writer, server.MJPEG_BOUNDARY if hasattr(server, 'MJPEG_BOUNDARY') else 'frame')
        elif path == "/snapshot":
            await handle_snapshot(server, writer)
        else:
            await handle_index(server, writer)
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


async def handle_index(server: "MJPEGCameraServer", writer: asyncio.StreamWriter) -> None:
    html = build_index_html(server)
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


async def handle_snapshot(server: "MJPEGCameraServer", writer: asyncio.StreamWriter) -> None:
    jpeg_data = server.get_snapshot()
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


async def handle_stream(server: "MJPEGCameraServer", writer: asyncio.StreamWriter, boundary: str) -> None:
    client_id = server._register_stream_client()
    response = (
        "HTTP/1.1 200 OK\r\n"
        f"Content-Type: multipart/x-mixed-replace; boundary={boundary}\r\n"
        "Cache-Control: no-cache, no-store, must-revalidate\r\n"
        "Connection: keep-alive\r\n"
        "\r\n"
    )
    writer.write(response.encode("utf-8"))
    await writer.drain()
    _LOGGER.debug("Started MJPEG stream for client %d", client_id)
    last_sent_time = 0
    try:
        while server._running:
            with server._frame_lock:
                jpeg_data = server._last_frame
                frame_time = server._last_frame_time
            if jpeg_data is not None and frame_time > last_sent_time:
                frame_header = (
                    f"--{boundary}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg_data)}\r\n\r\n"
                )
                writer.write(frame_header.encode("utf-8"))
                writer.write(jpeg_data)
                writer.write(b"\r\n")
                await writer.drain()
                last_sent_time = frame_time
            await asyncio.sleep(0.01)
    except (ConnectionResetError, BrokenPipeError):
        _LOGGER.debug("Client %d disconnected from stream", client_id)
    except Exception as e:
        _LOGGER.error("Error in MJPEG stream for client %d: %s", client_id, e)
    finally:
        server._unregister_stream_client(client_id)
    _LOGGER.debug("Ended MJPEG stream for client %d", client_id)
