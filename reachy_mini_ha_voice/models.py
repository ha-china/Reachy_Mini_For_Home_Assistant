"""Shared models for Reachy Mini Voice Assistant."""

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from queue import Queue

    from pymicro_wakeword import MicroWakeWord
    from pyopen_wakeword import OpenWakeWord

    from .audio.audio_player import AudioPlayer
    from .entities.entity import ESPHomeEntity, MediaPlayerEntity
    from .protocol.satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


class WakeWordType(str, Enum):
    MICRO_WAKE_WORD = "micro"
    OPEN_WAKE_WORD = "openWakeWord"


@dataclass
class AvailableWakeWord:
    id: str
    type: WakeWordType
    wake_word: str
    trained_languages: list[str]
    wake_word_path: Path

    def load(self) -> "MicroWakeWord | OpenWakeWord":
        if self.type == WakeWordType.MICRO_WAKE_WORD:
            from pymicro_wakeword import MicroWakeWord
            return MicroWakeWord.from_config(config_path=self.wake_word_path)

        if self.type == WakeWordType.OPEN_WAKE_WORD:
            from pyopen_wakeword import OpenWakeWord
            oww_model = OpenWakeWord.from_model(model_path=self.wake_word_path)
            oww_model.wake_word = self.wake_word
            return oww_model

        raise ValueError(f"Unexpected wake word type: {self.type}")


@dataclass
class Preferences:
    active_wake_words: list[str] = field(default_factory=list)
    # Audio processing settings (persisted from Home Assistant)
    agc_enabled: bool | None = None  # None = use hardware default
    agc_max_gain: float | None = None  # None = use hardware default
    noise_suppression: float | None = None  # None = use hardware default
    # Continuous conversation mode (controlled from Home Assistant)
    continuous_conversation: bool = False


@dataclass
class ServerState:
    """Global server state."""
    name: str
    mac_address: str
    audio_queue: "Queue[bytes | None]"
    entities: "list[ESPHomeEntity]"
    available_wake_words: "dict[str, AvailableWakeWord]"
    wake_words: "dict[str, MicroWakeWord | OpenWakeWord]"
    active_wake_words: set[str]
    stop_word: "MicroWakeWord"
    music_player: "AudioPlayer"
    tts_player: "AudioPlayer"
    wakeup_sound: str
    timer_finished_sound: str
    preferences: Preferences
    preferences_path: Path
    download_dir: Path

    # Reachy Mini specific
    reachy_mini: object | None = None
    motion_enabled: bool = True
    motion: object | None = None  # ReachyMiniMotion instance

    media_player_entity: "MediaPlayerEntity | None" = None
    satellite: "VoiceSatelliteProtocol | None" = None
    wake_words_changed: bool = False
    refractory_seconds: float = 2.0

    # Sleep state (updated by SleepManager)
    is_sleeping: bool = False
    services_suspended: bool = False

    # Mute state (controlled from Home Assistant)
    is_muted: bool = False

    # Camera state (controlled from Home Assistant)
    camera_enabled: bool = True

    # Callbacks for sleep/wake from HA buttons (set by VoiceAssistant)
    on_ha_sleep: object | None = None  # Callable[[], None]
    on_ha_wake: object | None = None   # Callable[[], None]

    def save_preferences(self) -> None:
        """Save preferences as JSON."""
        _LOGGER.debug("Saving preferences: %s", self.preferences_path)
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.preferences_path, "w", encoding="utf-8") as preferences_file:
            json.dump(
                asdict(self.preferences), preferences_file, ensure_ascii=False, indent=4
            )
