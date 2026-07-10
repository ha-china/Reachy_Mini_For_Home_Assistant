from __future__ import annotations

import logging
import threading

_LOGGER = logging.getLogger(__name__)


class LocalAudioPlayer:
    """Local audio player for TTS playback via SDK media pipeline.

    Head wobbling is handled by the SDK's HeadWobbler which is registered
    by VoiceAssistantService via media.enable_wobbling(). Audio played
    through this player flows through the GStreamer tee automatically.
    """

    def __init__(self) -> None:
        self.reachy_mini = None
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()
        self._playback_thread: threading.Thread | None = None
        self._http_host_override: str | None = None

    def set_reachy_mini(self, reachy_mini) -> None:
        self.reachy_mini = reachy_mini

    def set_http_host_override(self, host: str | None) -> None:
        self._http_host_override = host
