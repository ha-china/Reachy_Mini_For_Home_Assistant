"""Data models for the voice assistant."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional, Set, Union

import numpy as np

_LOGGER = logging.getLogger(__name__)


class WakeWordType(str, Enum):
    """Type of wake word model."""

    MICRO_WAKE_WORD = "microWakeWord"
    OPEN_WAKE_WORD = "openWakeWord"


@dataclass
class AvailableWakeWord:
    """Information about an available wake word model."""

    id: str
    type: WakeWordType
    wake_word: str
    trained_languages: List[str] = field(default_factory=list)
    wake_word_path: Optional[Path] = None

    def load(self):
        """Load the wake word model."""
        if self.type == WakeWordType.MICRO_WAKE_WORD:
            from pymicro_wakeword import MicroWakeWord

            return MicroWakeWord.from_config(self.wake_word_path)
        elif self.type == WakeWordType.OPEN_WAKE_WORD:
            from pyopen_wakeword import OpenWakeWord

            return OpenWakeWord.from_config(self.wake_word_path)
        else:
            raise ValueError(f"Unknown wake word type: {self.type}")


@dataclass
class Preferences:
    """User preferences."""

    active_wake_words: List[str] = field(default_factory=list)


@dataclass
class ServerState:
    """Shared server state."""

    name: str
    mac_address: str
    audio_queue: Queue
    entities: List["Entity"]
    available_wake_words: Dict[str, AvailableWakeWord]
    wake_words: Dict[str, Union["MicroWakeWord", "OpenWakeWord"]]
    active_wake_words: Set[str]
    stop_word: "MicroWakeWord"
    music_player: "AudioPlayer"
    tts_player: "AudioPlayer"
    wakeup_sound: str
    timer_finished_sound: str
    preferences: Preferences
    preferences_path: Path
    refractory_seconds: float
    download_dir: Path
    satellite: Optional["VoiceSatelliteProtocol"] = None
    wake_words_changed: bool = True
    reachy_integration: Optional["ReachyMiniIntegration"] = None


@dataclass
class Entity:
    """A Home Assistant entity."""

    key: str
    name: str
    state: str
    attributes: Dict[str, str] = field(default_factory=dict)


class AudioPlayer:
    """Simple audio player using PyAudio."""

    def __init__(self, device: Optional[int] = None):
        """Initialize audio player."""
        self.device = device
        self._stream = None
        self._pyaudio = None

    def play(self, audio_data: bytes) -> None:
        """Play audio data."""
        import pyaudio

        if self._pyaudio is None:
            self._pyaudio = pyaudio.PyAudio()

        # Assume 16-bit PCM, 16kHz, mono
        if self._stream is None:
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
                output_device_index=self.device,
            )

        self._stream.write(audio_data)

    def close(self) -> None:
        """Close the audio player."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if self._pyaudio is not None:
            self._pyaudio.terminate()
            self._pyaudio = None