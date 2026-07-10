from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from .audio_player_playback import AudioPlayerPlaybackMixin

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)


class LocalAudioPlayer(AudioPlayerPlaybackMixin):
    """Local audio player for TTS playback via SDK media pipeline.

    Head wobbling is handled by the SDK's HeadWobbler which is registered
    by VoiceAssistantService via media.enable_wobbling(). Audio played
    through this player flows through the GStreamer tee automatically.
    """

    def __init__(self, reachy_mini=None, gstreamer_lock=None) -> None:
        self.reachy_mini = reachy_mini
        self._gstreamer_lock = gstreamer_lock if gstreamer_lock is not None else threading.Lock()
        self.is_playing = False
        self._playlist: list[str] = []
        self._done_callback: Callable[[], None] | None = None
        self._done_callback_lock = threading.Lock()
        self._duck_volume: float = 0.5
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()
        self._playback_thread: threading.Thread | None = None
        self._http_host_override: str | None = None

    def set_reachy_mini(self, reachy_mini) -> None:
        self.reachy_mini = reachy_mini

    def set_http_host_override(self, host: str | None) -> None:
        self._http_host_override = host