"""
Voice processing module for Reachy Mini Voice Assistant

Note: STT and TTS are handled by Home Assistant via ESPHome protocol.
This module only contains offline wake word detection.
"""

from .detector import WakeWordDetector, MicroWakeWordDetector, OpenWakeWordDetector

__all__ = [
    "WakeWordDetector",
    "MicroWakeWordDetector",
    "OpenWakeWordDetector",
]