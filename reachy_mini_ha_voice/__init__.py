"""
Reachy Mini for Home Assistant

A voice assistant application that runs on Reachy Mini robot and integrates
with Home Assistant via the ESPHome protocol.

Key features:
- Local wake word detection (microWakeWord/openWakeWord)
- ESPHome protocol for Home Assistant integration
- STT/TTS handled by Home Assistant (not locally)
- Reachy Mini motion control integration
"""

__version__ = "0.5.2"
__author__ = "Desmond Dong"

# Don't import main module here to avoid runpy warning
# The app is loaded via entry point: reachy_mini_ha_voice.main:ReachyMiniHAVoiceApp

__all__ = [
    "__version__",
]
