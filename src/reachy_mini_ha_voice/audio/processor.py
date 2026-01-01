"""
Audio processor for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from queue import Queue
from typing import Optional, Callable
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Process audio chunks for wake word detection and streaming"""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        block_size: int = 1024
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        
        self._audio_queue: Queue[bytes] = Queue()
        self._is_processing = False
        self._wake_word_callbacks: list[Callable[[bytes], None]] = []
        self._stream_callbacks: list[Callable[[bytes], None]] = []
    
    def add_wake_word_callback(self, callback: Callable[[bytes], None]):
        """Add a callback for wake word detection"""
        self._wake_word_callbacks.append(callback)
    
    def add_stream_callback(self, callback: Callable[[bytes], None]):
        """Add a callback for audio streaming"""
        self._stream_callbacks.append(callback)
    
    async def process_audio_chunk(self, audio_chunk: bytes):
        """Process an audio chunk"""
        # Convert to numpy array for processing
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Call wake word callbacks
        for callback in self._wake_word_callbacks:
            try:
                callback(audio_chunk)
            except Exception as e:
                logger.error(f"Error in wake word callback: {e}")
        
        # Call stream callbacks
        for callback in self._stream_callbacks:
            try:
                callback(audio_chunk)
            except Exception as e:
                logger.error(f"Error in stream callback: {e}")
    
    async def start_processing(self):
        """Start processing audio"""
        if self._is_processing:
            logger.warning("Already processing audio")
            return
        
        self._is_processing = True
        logger.info("Started audio processing")
    
    async def stop_processing(self):
        """Stop processing audio"""
        if not self._is_processing:
            return
        
        self._is_processing = False
        logger.info("Stopped audio processing")
    
    def is_processing(self) -> bool:
        """Check if processing audio"""
        return self._is_processing
    
    async def process_audio_stream(self, audio_stream: Callable[[], bytes]):
        """Process a continuous audio stream"""
        await self.start_processing()
        
        try:
            while self._is_processing:
                audio_chunk = audio_stream()
                if audio_chunk:
                    await self.process_audio_chunk(audio_chunk)
                else:
                    await asyncio.sleep(0.001)
        except Exception as e:
            logger.error(f"Error processing audio stream: {e}")
        finally:
            await self.stop_processing()