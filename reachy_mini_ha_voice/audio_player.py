"""Audio player using Reachy Mini's media system."""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import scipy.signal

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
        """Play an audio file."""
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

            # Use Reachy Mini's push_audio_sample for safe playback
            # This writes directly to the existing GStreamer pipeline
            # instead of creating a new one (which can cause conflicts)
            if self.reachy_mini is not None:
                try:
                    self._play_via_push_audio(file_path)
                except Exception as e:
                    _LOGGER.warning("push_audio_sample failed, trying sounddevice: %s", e)
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

    def _play_file_fallback(self, file_path: str) -> None:
        """Play audio using sounddevice (avoids GStreamer conflicts)."""
        import sounddevice as sd
        import soundfile as sf

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
                # Try to find the Reachy Mini audio output device
                devices = sd.query_devices()
                output_device = None
                for i, dev in enumerate(devices):
                    if dev['max_output_channels'] > 0:
                        name = dev['name'].lower()
                        # Look for Reachy Mini's audio device
                        if 'reachymini' in name or 'reachy' in name or 'usb' in name:
                            output_device = i
                            break
                
                if output_device is not None:
                    sd.play(data.astype(np.float32), samplerate, device=output_device)
                else:
                    sd.play(data.astype(np.float32), samplerate)
                sd.wait()
            except Exception as e:
                _LOGGER.warning("sounddevice playback failed: %s", e)

    def _play_via_push_audio(self, file_path: str) -> None:
        """Play audio by pushing samples to Reachy Mini's GStreamer pipeline.
        
        This method writes audio directly to the existing GStreamer pipeline
        instead of creating a new one, avoiding conflicts that can crash the daemon.
        """
        import soundfile as sf
        
        # Read audio file
        data, input_samplerate = sf.read(file_path, dtype='float32')
        _LOGGER.debug("Audio file: %s, samplerate=%d, shape=%s", file_path, input_samplerate, data.shape)
        
        # Get output sample rate from Reachy Mini
        output_samplerate = self.reachy_mini.media.get_output_audio_samplerate()
        _LOGGER.debug("Output samplerate: %d", output_samplerate)
        
        # Convert to mono if stereo
        if data.ndim == 2:
            data = data.mean(axis=1)
        
        # Apply volume
        data = data * self._current_volume
        
        # Resample if needed
        if input_samplerate != output_samplerate:
            num_samples = int(len(data) * output_samplerate / input_samplerate)
            data = scipy.signal.resample(data, num_samples)
            _LOGGER.debug("Resampled to %d samples", num_samples)
        
        # Push audio in chunks (similar to conversation_app)
        chunk_size = int(output_samplerate * 0.1)  # 100ms chunks
        for i in range(0, len(data), chunk_size):
            if self._stop_flag.is_set():
                break
            chunk = data[i:i + chunk_size].astype(np.float32)
            self.reachy_mini.media.push_audio_sample(chunk)
            # Small sleep to prevent buffer overflow
            time.sleep(0.05)

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
        if self.reachy_mini is not None:
            try:
                self.reachy_mini.media.clear_output_buffer()
            except Exception:
                pass
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
