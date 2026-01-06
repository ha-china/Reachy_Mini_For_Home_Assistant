"""Audio player using Reachy Mini's media system."""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import soundfile as sf

_LOGGER = logging.getLogger(__name__)


class AudioPlayer:
    """Audio player using Reachy Mini's media system."""

    def __init__(self, reachy_mini=None) -> None:
        self.reachy_mini = reachy_mini
        self.is_playing = False
        self._playlist: List[str] = []
        self._done_callback: Optional[Callable[[], None]] = None
        self._done_callback_lock = threading.Lock()
        self._duck_volume: float = 0.5
        self._unduck_volume: float = 1.0
        self._current_volume: float = 1.0
        self._stop_flag = threading.Event()

    def set_reachy_mini(self, reachy_mini) -> None:
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

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
        """Play an audio file using play_sound() - independent GStreamer playbin."""
        try:
            # Handle URLs - download first
            if file_path.startswith(("http://", "https://")):
                import urllib.request
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    urllib.request.urlretrieve(file_path, tmp.name)
                    file_path = tmp.name

            if self._stop_flag.is_set():
                return

            # Use Reachy Mini's play_sound() for TTS playback
            # This creates an independent GStreamer playbin that doesn't conflict
            # with the recording pipeline (unlike push_audio_sample which shares appsrc)
            if self.reachy_mini is not None:
                try:
                    self._play_via_play_sound(file_path)
                except Exception as e:
                    _LOGGER.warning("play_sound failed, trying sounddevice: %s", e)
                    self._play_file_fallback(file_path)
            else:
                self._play_file_fallback(file_path)

        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            self.is_playing = False
            # Play next in playlist or finish
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    def _play_via_play_sound(self, file_path: str) -> None:
        """Play audio using Reachy Mini's play_sound() method.
        
        This creates an independent GStreamer playbin pipeline that doesn't
        conflict with the recording pipeline. This is the key difference from
        push_audio_sample() which writes to the shared appsrc pipeline.
        """
        # play_sound() is non-blocking, so we need to estimate duration and wait
        data, samplerate = sf.read(file_path, dtype='float32')
        duration = len(data) / samplerate
        
        _LOGGER.debug("Playing via play_sound: %s (duration=%.2fs)", file_path, duration)
        
        # Call play_sound - creates independent playbin
        self.reachy_mini.media.play_sound(file_path)
        
        # Wait for playback to complete (play_sound is non-blocking)
        # Check stop flag periodically
        elapsed = 0.0
        while elapsed < duration and not self._stop_flag.is_set():
            time.sleep(0.1)
            elapsed += 0.1

    def _play_file_fallback(self, file_path: str) -> None:
        """Play audio using sounddevice (fallback when Reachy Mini not available)."""
        import sounddevice as sd
        import scipy.signal

        data, samplerate = sf.read(file_path, dtype='float32')

        # Convert to mono if stereo
        if data.ndim == 2:
            data = data.mean(axis=1)

        # Apply volume
        data = data * self._current_volume
        
        # Resample to 48000Hz (standard rate supported by most devices)
        target_samplerate = 48000
        if samplerate != target_samplerate:
            num_samples = int(len(data) * target_samplerate / samplerate)
            data = scipy.signal.resample(data, num_samples)
            samplerate = target_samplerate

        if not self._stop_flag.is_set():
            try:
                sd.play(data.astype(np.float32), samplerate)
                sd.wait()
            except Exception as e:
                _LOGGER.warning("sounddevice playback failed: %s", e)

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
        self.is_playing = False

    def resume(self) -> None:
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        self._stop_flag.set()
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
