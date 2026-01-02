"""Audio player using sounddevice for Reachy Mini."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import sounddevice as sd

_LOGGER = logging.getLogger(__name__)


class AudioPlayer:
    """Audio player using sounddevice."""

    def __init__(self, device: Optional[str] = None) -> None:
        self.device = device
        self.is_playing = False
        self._playlist: List[str] = []
        self._done_callback: Optional[Callable[[], None]] = None
        self._done_callback_lock = threading.Lock()
        self._duck_volume: float = 0.5
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()

    def play(
        self,
        url: Union[str, List[str]],
        done_callback: Optional[Callable[[], None]] = None,
        stop_first: bool = True,
    ) -> None:
        if stop_first:
            self.stop()

        if isinstance(url, str):
            self._playlist = [url]
        else:
            self._playlist = list(url)

        self._done_callback = done_callback
        self._stop_flag.clear()
        self._play_next()

    def _play_next(self) -> None:
        if not self._playlist or self._stop_flag.is_set():
            self._on_playback_finished()
            return

        next_url = self._playlist.pop(0)
        _LOGGER.debug("Playing %s", next_url)
        self.is_playing = True

        # Start playback in a thread
        thread = threading.Thread(target=self._play_file, args=(next_url,), daemon=True)
        thread.start()

    def _play_file(self, file_path: str) -> None:
        """Play an audio file."""
        try:
            # Try to load the audio file
            if file_path.startswith(("http://", "https://")):
                # For URLs, download first
                import urllib.request
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    urllib.request.urlretrieve(file_path, tmp.name)
                    file_path = tmp.name

            # Load audio file
            import soundfile as sf
            data, samplerate = sf.read(file_path)

            # Apply volume
            data = data * self._current_volume

            # Play
            if not self._stop_flag.is_set():
                sd.play(data, samplerate, device=self.device)
                sd.wait()

        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            self.is_playing = False
            # Play next in playlist or finish
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    def _on_playback_finished(self) -> None:
        """Called when playback is finished."""
        self.is_playing = False
        todo_callback: Optional[Callable[[], None]] = None

        with self._done_callback_lock:
            if self._done_callback:
                todo_callback = self._done_callback
                self._done_callback = None

        if todo_callback:
            try:
                todo_callback()
            except Exception:
                _LOGGER.exception("Unexpected error running done callback")

    def pause(self) -> None:
        sd.stop()
        self.is_playing = False

    def resume(self) -> None:
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        self._stop_flag.set()
        sd.stop()
        self._playlist.clear()
        self.is_playing = False

    def duck(self) -> None:
        self._current_volume = self._duck_volume

    def unduck(self) -> None:
        self._current_volume = self._unduck_volume

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, volume))
        self._unduck_volume = volume / 100.0
        self._duck_volume = self._unduck_volume / 2
        self._current_volume = self._unduck_volume
