"""
Wake word detector for Reachy Mini Voice Assistant
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WakeWordDetector(ABC):
    """Abstract base class for wake word detector"""
    
    @abstractmethod
    async def load_model(self, model_path: str):
        """Load wake word model"""
        pass
    
    @abstractmethod
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """Process audio chunk, return True if wake word detected"""
        pass
    
    @abstractmethod
    async def get_confidence(self) -> float:
        """Get detection confidence"""
        pass


class MicroWakeWordDetector(WakeWordDetector):
    """microWakeWord detector"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
        self.model_path = Path(model_path)
        self._confidence = 0.0
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """Load microWakeWord model"""
        try:
            from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures
            
            self.model_path = Path(model_path)
            
            # Load features
            self.features = MicroWakeWordFeatures()
            
            # Load model
            self.model = MicroWakeWord.from_config(str(self.model_path))
            self._loaded = True
            
            logger.info(f"Loaded microWakeWord model from {model_path}")
        except ImportError:
            logger.error("pymicro_wakeword not installed. Install with: pip install pymicro-wakeword")
            raise
        except Exception as e:
            logger.error(f"Failed to load microWakeWord model: {e}")
            raise
    
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """Process audio chunk"""
        if not self._loaded or self.model is None:
            logger.warning("Model not loaded")
            return False
        
        try:
            import numpy as np
            
            # Convert audio to numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Extract features
            features = self.features.process_streaming(audio_array)
            
            # Process with model
            for feature in features:
                score = self.model.process_streaming(feature)
                if score is not None:
                    self._confidence = score
                    if score >= 0.5:  # Threshold
                        logger.info(f"Wake word detected with confidence: {score:.2f}")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return False
    
    async def get_confidence(self) -> float:
        """Get detection confidence"""
        return self._confidence


class OpenWakeWordDetector(WakeWordDetector):
    """openWakeWord detector"""
    
    def __init__(self, model_path: str):
        self.model = None
        self.features = None
        self.model_path = Path(model_path)
        self._confidence = 0.0
        self._loaded = False
    
    async def load_model(self, model_path: str):
        """Load openWakeWord model"""
        try:
            from pyopen_wakeword import OpenWakeWord, OpenWakeWordFeatures
            
            self.model_path = Path(model_path)
            
            # Load features
            self.features = OpenWakeWordFeatures.from_builtin()
            
            # Load model
            self.model = OpenWakeWord(str(self.model_path))
            self._loaded = True
            
            logger.info(f"Loaded openWakeWord model from {model_path}")
        except ImportError:
            logger.error("pyopen_wakeword not installed. Install with: pip install pyopen-wakeword")
            raise
        except Exception as e:
            logger.error(f"Failed to load openWakeWord model: {e}")
            raise
    
    async def process_audio(self, audio_chunk: bytes) -> bool:
        """Process audio chunk"""
        if not self._loaded or self.model is None:
            logger.warning("Model not loaded")
            return False
        
        try:
            import numpy as np
            
            # Convert audio to numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Extract features
            features = self.features.process_streaming(audio_array)
            
            # Process with model
            for feature in features:
                scores = self.model.process_streaming(feature)
                for score in scores:
                    self._confidence = score
                    if score >= 0.5:  # Threshold
                        logger.info(f"Wake word detected with confidence: {score:.2f}")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return False
    
    async def get_confidence(self) -> float:
        """Get detection confidence"""
        return self._confidence


async def load_wake_word_detector(
    model_path: str,
    detector_type: str = "micro"
) -> WakeWordDetector:
    """Load wake word detector based on type"""
    if detector_type == "micro":
        detector = MicroWakeWordDetector(model_path)
    elif detector_type == "open":
        detector = OpenWakeWordDetector(model_path)
    else:
        raise ValueError(f"Unknown detector type: {detector_type}")
    
    await detector.load_model(model_path)
    return detector