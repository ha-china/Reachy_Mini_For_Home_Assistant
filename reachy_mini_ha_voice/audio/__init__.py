"""Audio module for Reachy Mini.

This module handles all audio-related functionality:
- DOATracker: Direction of Arrival sound localization
- MicrophoneOptimizer: ReSpeaker XVF3800 microphone configuration

Note: AudioPlayer and VoiceSatelliteProtocol are in the parent package
to avoid circular imports.
"""

from .doa_tracker import DOATracker, DOAConfig
from .microphone import MicrophoneOptimizer, MicrophonePreferences, MicrophoneDefaults

__all__ = [
    "DOATracker",
    "DOAConfig",
    "MicrophoneOptimizer",
    "MicrophonePreferences",
    "MicrophoneDefaults",
]
