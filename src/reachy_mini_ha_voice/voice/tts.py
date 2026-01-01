"""
Text-to-Speech engine for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional
import io

logger = logging.getLogger(__name__)


class TTSEngine(ABC):
    """Abstract base class for TTS engine"""
    
    @abstractmethod
    async def load_model(self, model_path: str):
        """Load TTS model"""
        pass
    
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio"""
        pass


class PiperTTS(TTSEngine):
    """Piper TTS engine"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.model_path = model_path
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """Load Piper model"""
        try:
            from piper import PiperVoice
            
            self.model_path = model_path
            self.model = PiperVoice.load(model_path)
            self._loaded = True
            
            logger.info(f"Loaded Piper model from {model_path}")
        except ImportError:
            logger.error("piper-tts not installed. Install with: pip install piper-tts")
            raise
        except Exception as e:
            logger.error(f"Failed to load Piper model: {e}")
            raise
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio"""
        if not self._loaded or self.model is None:
            logger.warning("Model not loaded")
            return b""
        
        try:
            import numpy as np
            
            # Synthesize
            audio_stream = io.BytesIO()
            self.model.synthesize(text, audio_stream)
            audio_stream.seek(0)
            
            # Convert to bytes
            audio_data = audio_stream.read()
            
            logger.debug(f"Synthesized {len(text)} characters")
            return audio_data
        except Exception as e:
            logger.error(f"Error synthesizing text: {e}")
            return b""


class MockTTS(TTSEngine):
    """Mock TTS engine for testing"""
    
    def __init__(self):
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """Load mock model"""
        self._loaded = True
        logger.info("Loaded mock TTS model")
    
    async def synthesize(self, text: str) -> bytes:
        """Mock synthesis - return silent audio"""
        import numpy as np
        
        # Generate 1 second of silence at 16kHz
        sample_rate = 16000
        duration = len(text) * 0.1  # Rough estimation
        samples = int(sample_rate * duration)
        silence = np.zeros(samples, dtype=np.int16)
        
        return silence.tobytes()


async def load_tts_engine(
    engine_type: str = "piper",
    model_path: str = "en_US-lessac-medium"
) -> TTSEngine:
    """Load TTS engine based on type"""
    if engine_type == "piper":
        engine = PiperTTS(model_path)
    elif engine_type == "mock":
        engine = MockTTS()
    else:
        raise ValueError(f"Unknown TTS engine type: {engine_type}")
    
    await engine.load_model(model_path)
    return engine