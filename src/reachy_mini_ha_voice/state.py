"""
State management for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from queue import Queue

logger = logging.getLogger(__name__)


@dataclass
class ServerState:
    """Global server state"""
    name: str
    
    # Configuration
    config: Optional[Any] = None
    
    # Audio
    microphone: Optional[Any] = None
    speaker: Optional[Any] = None
    audio_queue: Queue = field(default_factory=Queue)
    
    # Voice
    wake_word_detector: Optional[Any] = None
    stop_word_detector: Optional[Any] = None
    active_wake_words: list = field(default_factory=list)
    
    # Motion
    motion_controller: Optional[Any] = None
    motion_queue: Optional[Any] = None
    
    # ESPHome
    esphome_server: Optional[Any] = None
    voice_satellite: Optional[Any] = None
    
    # Status
    is_running: bool = False
    is_streaming: bool = False
    
    # Callbacks
    on_wake_word: Optional[callable] = None
    on_stt_result: Optional[callable] = None
    on_tts_audio: Optional[callable] = None
    
    def __post_init__(self):
        """Post-initialization"""
        logger.debug(f"ServerState initialized for {self.name}")
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up ServerState")
        
        if self.microphone:
            try:
                await self.microphone.stop_recording()
            except Exception as e:
                logger.error(f"Error stopping microphone: {e}")
        
        if self.motion_controller:
            try:
                await self.motion_controller.stop_speech_reactive_motion()
                await self.motion_controller.turn_off()
                await self.motion_controller.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting motion controller: {e}")
        
        if self.motion_queue:
            try:
                await self.motion_queue.stop()
            except Exception as e:
                logger.error(f"Error stopping motion queue: {e}")
        
        if self.esphome_server:
            try:
                await self.esphome_server.stop()
            except Exception as e:
                logger.error(f"Error stopping ESPHome server: {e}")
        
        logger.info("ServerState cleanup complete")