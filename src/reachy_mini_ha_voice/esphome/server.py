"""
ESPHome server for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from typing import Optional, Callable, List
from .protocol import VoiceAssistantEventType, VoiceAssistantFeature

logger = logging.getLogger(__name__)


class ESPHomeServer:
    """ESPHome protocol server"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 6053):
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None
        self._is_running = False
        self._clients: List = []
        self._audio_callback: Optional[Callable[[bytes], None]] = None
        self._event_callback: Optional[Callable[[VoiceAssistantEventType, dict], None]] = None
    
    async def start(self):
        """Start ESPHome server"""
        if self._is_running:
            logger.warning("ESPHome server already running")
            return
        
        try:
            self._server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port
            )
            self._is_running = True
            
            logger.info(f"ESPHome server started on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start ESPHome server: {e}")
            raise
    
    async def stop(self):
        """Stop ESPHome server"""
        if not self._is_running:
            return
        
        self._is_running = False
        
        # Close all clients
        for client in self._clients:
            client.close()
        self._clients.clear()
        
        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        logger.info("ESPHome server stopped")
    
    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """Set audio callback"""
        self._audio_callback = callback
    
    def set_event_callback(self, callback: Callable[[VoiceAssistantEventType, dict], None]):
        """Set event callback"""
        self._event_callback = callback
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data to all clients"""
        for client in self._clients:
            try:
                client.write(audio_data)
                await client.drain()
            except Exception as e:
                logger.error(f"Error sending audio to client: {e}")
    
    async def send_event(self, event_type: VoiceAssistantEventType, data: dict):
        """Send event to all clients"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle client connection"""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"Client connected: {client_addr}")
        
        self._clients.append(writer)
        
        try:
            while self._is_running:
                # Read data from client
                data = await reader.read(4096)
                if not data:
                    break
                
                # Process data (simplified ESPHome protocol)
                await self._process_data(data)
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}")
        finally:
            self._clients.remove(writer)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client disconnected: {client_addr}")
    
    async def _process_data(self, data: bytes):
        """Process incoming data"""
        # Simplified ESPHome protocol processing
        # In a real implementation, this would parse ESPHome frames
        logger.debug(f"Received {len(data)} bytes from client")


class VoiceSatelliteProtocol:
    """Voice satellite protocol handler"""
    
    def __init__(self, state):
        self.state = state
        self._is_streaming = False
        self._refractory_period = 2.0  # seconds
        self._last_wake_word_time = 0.0
    
    async def handle_message(self, msg):
        """Handle ESPHome message"""
        # Simplified message handling
        logger.debug(f"Received message: {msg}")
    
    async def handle_audio(self, audio_chunk: bytes):
        """Handle audio chunk"""
        if self._is_streaming and self.state.esphome_server:
            await self.state.esphome_server.send_audio(audio_chunk)
    
    async def handle_wake_word(self):
        """Handle wake word detection"""
        current_time = asyncio.get_event_loop().time()
        
        # Check refractory period
        if current_time - self._last_wake_word_time < self._refractory_period:
            logger.debug("Wake word in refractory period, ignoring")
            return
        
        self._last_wake_word_time = current_time
        
        # Send wake word event
        if self.state.esphome_server:
            await self.state.esphome_server.send_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_WAKE_WORD_END,
                {"wake_word": "detected"}
            )
        
        # Start streaming
        self._is_streaming = True
        
        logger.info("Wake word detected, started streaming")
    
    async def stop_streaming(self):
        """Stop audio streaming"""
        self._is_streaming = False
        logger.info("Stopped streaming")