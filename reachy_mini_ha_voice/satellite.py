"""Voice satellite protocol implementation for ESPHome."""

import asyncio
import json
import logging
import struct
from typing import Optional, Union

from .models import ServerState

_LOGGER = logging.getLogger(__name__)


class VoiceSatelliteProtocol(asyncio.Protocol):
    """ESPHome voice satellite protocol implementation."""

    def __init__(self, state: ServerState):
        """Initialize protocol."""
        self.state = state
        self.transport: Optional[asyncio.Transport] = None
        self._buffer = bytearray()
        self._connected = False

    def connection_made(self, transport: asyncio.Transport) -> None:
        """Handle new connection."""
        self.transport = transport
        self.state.satellite = self
        self._connected = True
        _LOGGER.info("Client connected: %s", transport.get_extra_info("peername"))

    def connection_lost(self, exc: Optional[Exception]) -> None:
        """Handle connection loss."""
        self._connected = False
        self.state.satellite = None
        _LOGGER.info("Client disconnected")
        if exc:
            _LOGGER.error("Connection error: %s", exc)

    def data_received(self, data: bytes) -> None:
        """Handle incoming data."""
        self._buffer.extend(data)

        while len(self._buffer) >= 3:
            # Parse message header
            msg_type = self._buffer[0]
            msg_length = struct.unpack(">H", self._buffer[1:3])[0]

            if len(self._buffer) < 3 + msg_length:
                # Need more data
                break

            # Extract message
            msg_data = bytes(self._buffer[3 : 3 + msg_length])
            self._buffer = self._buffer[3 + msg_length :]

            # Process message
            asyncio.create_task(self._process_message(msg_type, msg_data))

    async def _process_message(self, msg_type: int, msg_data: bytes) -> None:
        """Process a message."""
        try:
            if msg_type == 0x01:  # Hello
                await self._handle_hello(msg_data)
            elif msg_type == 0x02:  # Voice Assistant Start
                await self._handle_voice_assistant_start(msg_data)
            elif msg_type == 0x03:  # Voice Assistant End
                await self._handle_voice_assistant_end(msg_data)
            elif msg_type == 0x04:  # TTS Audio
                await self._handle_tts_audio(msg_data)
            else:
                _LOGGER.warning("Unknown message type: %s", msg_type)
        except Exception as e:
            _LOGGER.error("Error processing message: %s", e)

    async def _handle_hello(self, data: bytes) -> None:
        """Handle hello message."""
        _LOGGER.debug("Received hello message")
        # Send hello response
        response = self._build_message(0x01, json.dumps({"name": self.state.name}))
        self._send_message(response)

    async def _handle_voice_assistant_start(self, data: bytes) -> None:
        """Handle voice assistant start message."""
        _LOGGER.info("Voice assistant started")
        # Play wake sound
        try:
            with open(self.state.wakeup_sound, "rb") as f:
                self.state.tts_player.play(f.read())
        except Exception as e:
            _LOGGER.error("Error playing wake sound: %s", e)

    async def _handle_voice_assistant_end(self, data: bytes) -> None:
        """Handle voice assistant end message."""
        _LOGGER.info("Voice assistant ended")

    async def _handle_tts_audio(self, data: bytes) -> None:
        """Handle TTS audio message."""
        try:
            self.state.tts_player.play(data)
        except Exception as e:
            _LOGGER.error("Error playing TTS audio: %s", e)

    def handle_audio(self, audio_chunk: bytes) -> None:
        """Handle audio chunk from microphone."""
        if self._connected and self.transport:
            # Send audio data to Home Assistant
            message = self._build_message(0x10, audio_chunk)
            self._send_message(message)

    def wakeup(self, wake_word) -> None:
        """Handle wake word detection."""
        _LOGGER.info("Wake word detected: %s", wake_word.id)
        # Send wake notification to Home Assistant
        message = self._build_message(
            0x11, json.dumps({"wake_word": wake_word.wake_word})
        )
        self._send_message(message)

    def stop(self) -> None:
        """Handle stop word detection."""
        _LOGGER.info("Stop word detected")
        # Send stop notification to Home Assistant
        message = self._build_message(0x12, json.dumps({"action": "stop"}))
        self._send_message(message)

    def _build_message(self, msg_type: int, data: Union[str, bytes]) -> bytes:
        """Build a message."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        length = len(data)
        return bytes([msg_type]) + struct.pack(">H", length) + data

    def _send_message(self, message: bytes) -> None:
        """Send a message."""
        if self._connected and self.transport:
            self.transport.write(message)