"""
Reachy Mini for Home Assistant

A deep integration app combining Reachy Mini robot with Home Assistant,
enabling voice control, smart home automation, and expressive robot interactions.

Key features:
- Local wake word detection (microWakeWord/openWakeWord)
- ESPHome protocol for seamless Home Assistant communication
- STT/TTS powered by Home Assistant voice pipeline
- Reachy Mini motion control with expressive animations
- Camera streaming and gesture detection
- Smart home entity control through natural voice commands
"""

try:
    from importlib.metadata import version

    __version__ = version("reachy_mini_home_assistant")
except Exception:
    __version__ = "0.0.0"  # Fallback for development
__author__ = "Desmond Dong"

# Don't import main module here to avoid runpy warning
# The app is loaded via entry point: reachy_mini_home_assistant.main:ReachyMiniHaVoiceApp

__all__ = [
    "__version__",
]
