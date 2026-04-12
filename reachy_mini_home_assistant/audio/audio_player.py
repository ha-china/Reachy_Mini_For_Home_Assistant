"""Audio player facade for Reachy Mini audio playback."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import TYPE_CHECKING

from .audio_player_playback import AudioPlayerPlaybackMixin
from .audio_player_sendspin import AudioFormat, AudioPlayerSendspinMixin, ClientListener, SendspinClient
from .audio_player_shared import get_stable_client_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..protocol.zeroconf import SendspinDiscovery


class AudioPlayer(AudioPlayerSendspinMixin, AudioPlayerPlaybackMixin):
    """Audio player using Reachy Mini's media system with automatic Sendspin support."""

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
        self._sway_callback: Callable[[dict], None] | None = None

        self._sendspin_client_id = get_stable_client_id()
        self._sendspin_client: SendspinClient | None = None
        self._sendspin_listener: ClientListener | None = None
        self._sendspin_enabled = False
        self._sendspin_url: str | None = None
        self._sendspin_discovery: SendspinDiscovery | None = None
        self._sendspin_unsubscribers: list[Callable] = []
        self._sendspin_connect_lock: asyncio.Lock | None = None
        self._sendspin_audio_format: AudioFormat | None = None
        self._sendspin_playback_started = False
        self._sendspin_stream_active = False
        self._sendspin_paused = False
        self._sendspin_remote_volume = 100
        self._sendspin_muted = False
        self._sendspin_queue = deque()
        self._sendspin_queue_bytes = 0
        self._sendspin_sway_queue = deque()
        self._sendspin_queue_lock = threading.Lock()
        self._sendspin_queue_event = threading.Event()
        self._sendspin_queue_stop = threading.Event()
        self._sendspin_queue_thread: threading.Thread | None = None
        self._sendspin_sway_state: dict | None = None
        self._logged_resample = False
        self._last_sendspin_overflow_log = 0.0
        self._http_host_override: str | None = None

    def set_sway_callback(self, callback: Callable[[dict], None] | None) -> None:
        self._sway_callback = callback

    def set_reachy_mini(self, reachy_mini) -> None:
        self.reachy_mini = reachy_mini

    def set_http_host_override(self, host: str | None) -> None:
        self._http_host_override = host

    def __del__(self) -> None:
        try:
            self._remove_sendspin_listeners()
            self._clear_sendspin_queue()
            self._stop_sendspin_worker()
            self._sendspin_client = None
        except Exception:
            pass
