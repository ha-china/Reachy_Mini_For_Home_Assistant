"""
Reachy Mini Home Assistant Voice Assistant

A voice assistant application that runs on Reachy Mini robot and integrates
with Home Assistant via the ESPHome protocol.

Key features:
- Local wake word detection (microWakeWord/openWakeWord)
- ESPHome protocol for Home Assistant integration
- STT/TTS handled by Home Assistant (not locally)
- Reachy Mini motion control integration
"""

__version__ = "0.1.0"
__author__ = "Pollen Robotics"

from .main import ReachyMiniHAVoiceApp
from .voice_assistant import VoiceAssistantService
from .models import ServerState, AvailableWakeWord, Preferences, WakeWordType
from .motion import ReachyMiniMotion

__all__ = [
    "ReachyMiniHAVoiceApp",
    "VoiceAssistantService",
    "ServerState",
    "AvailableWakeWord",
    "Preferences",
    "WakeWordType",
    "ReachyMiniMotion",
    "__version__",
]
