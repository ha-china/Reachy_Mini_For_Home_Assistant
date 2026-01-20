"""Audio module for Reachy Mini.

This module handles all audio-related functionality:
- AudioPlayer: Audio playback with Sendspin support
- DOATracker: Direction of Arrival sound localization
- MicrophoneOptimizer: ReSpeaker XVF3800 microphone configuration
"""

from .audio_player import AudioPlayer
from .doa_tracker import DOAConfig, DOATracker
from .microphone import MicrophoneDefaults, MicrophoneOptimizer, MicrophonePreferences

__all__ = [
    "AudioPlayer",
    "DOAConfig",
    "DOATracker",
    "MicrophoneDefaults",
    "MicrophoneOptimizer",
    "MicrophonePreferences",
]
