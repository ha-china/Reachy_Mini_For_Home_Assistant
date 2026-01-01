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

    MICRO_WAKE_WORD = "micro"
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

            return MicroWakeWord.from_config(config_path=self.wake_word_path)
        elif self.type == WakeWordType.OPEN_WAKE_WORD:
            from pyopen_wakeword import OpenWakeWord

            oww_model = OpenWakeWord.from_model(model_path=self.wake_word_path)
            setattr(oww_model, "wake_word", self.wake_word)

            return oww_model
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
    audio_queue: "Queue[Optional[bytes]]"
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
    wake_words_changed: bool = False
    reachy_integration: Optional["ReachyMiniIntegration"] = None
    media_player_entity: Optional["MediaPlayerEntity"] = None

    def save_preferences(self) -> None:
        """Save preferences to file."""
        try:
            import json

            with open(self.preferences_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"active_wake_words": self.preferences.active_wake_words},
                    f,
                )
        except Exception as e:
            _LOGGER.error("Error saving preferences: %s", e)


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
        self._ducked = False

    def play(self, audio_data: Union[bytes, str], done_callback=None) -> None:
        """Play audio data or URL."""
        import pyaudio

        if self._pyaudio is None:
            self._pyaudio = pyaudio.PyAudio()

        if isinstance(audio_data, str):
            # It's a URL or file path
            try:
                from urllib.request import urlopen

                if audio_data.startswith("http://") or audio_data.startswith("https://"):
                    with urlopen(audio_data) as response:
                        audio_data = response.read()
                else:
                    # It's a file path
                    with open(audio_data, "rb") as f:
                        audio_data = f.read()
            except Exception as e:
                _LOGGER.error("Error loading audio: %s", e)
                if done_callback:
                    done_callback()
                return

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

        if done_callback:
            done_callback()

    def duck(self) -> None:
        """Duck the volume (reduce by 50%)."""
        self._ducked = True
        # For simple implementation, we just note the state
        # In a full implementation, we would actually reduce the volume

    def unduck(self) -> None:
        """Unduck the volume (restore to normal)."""
        self._ducked = False
        # For simple implementation, we just note the state
        # In a full implementation, we would actually restore the volume

    def stop(self) -> None:
        """Stop playing and reset the stream."""
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

    def close(self) -> None:
        """Close the audio player."""
        self.stop()
        if self._pyaudio is not None:
            self._pyaudio.terminate()
            self._pyaudio = None