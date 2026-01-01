"""
Speech-to-Text engine for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class STTEngine(ABC):
    """Abstract base class for STT engine"""
    
    @abstractmethod
    async def load_model(self, model_name: str):
        """Load STT model"""
        pass
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio to text"""
        pass


class WhisperSTT(STTEngine):
    """Whisper STT engine"""
    
    def __init__(self, model_name: str = "base"):
        self.model = None
        self.model_name = model_name
        self._loaded = False
    
    async def load_model(self, model_name: str):
        """Load Whisper model"""
        try:
            import whisper
            
            self.model_name = model_name
            self.model = whisper.load_model(model_name)
            self._loaded = True
            
            logger.info(f"Loaded Whisper model: {model_name}")
        except ImportError:
            logger.error("whisper not installed. Install with: pip install openai-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio to text"""
        if not self._loaded or self.model is None:
            logger.warning("Model not loaded")
            return ""
        
        try:
            import numpy as np
            
            # Convert audio to numpy array
            audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Transcribe
            result = self.model.transcribe(audio)
            text = result["text"].strip()
            
            logger.debug(f"Transcribed: {text}")
            return text
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return ""


class MockSTT(STTEngine):
    """Mock STT engine for testing"""
    
    def __init__(self):
        self._loaded = False
    
    async def load_model(self, model_name: str):
        """Load mock model"""
        self._loaded = True
        logger.info("Loaded mock STT model")
    
    async def transcribe(self, audio_data: bytes) -> str:
        """Mock transcription"""
        return "Hello, this is a test transcription."


async def load_stt_engine(
    engine_type: str = "whisper",
    model_name: str = "base"
) -> STTEngine:
    """Load STT engine based on type"""
    if engine_type == "whisper":
        engine = WhisperSTT(model_name)
    elif engine_type == "mock":
        engine = MockSTT()
    else:
        raise ValueError(f"Unknown STT engine type: {engine_type}")
    
    await engine.load_model(model_name)
    return engine