"""Audio player using Reachy Mini's media system.

This module provides audio playback functionality similar to linux-voice-assistant's
MpvMediaPlayer, but using Reachy Mini's GStreamer-based audio system.

For local files: Uses play_sound() which creates an independent playbin pipeline.
For URLs (TTS): Downloads to temp file, then uses play_sound().

This approach avoids conflicts with the recording pipeline.
"""

import logging
import os
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import List, Optional, Union

import numpy as np
import soundfile as sf
import scipy.signal

_LOGGER = logging.getLogger(__name__)


class AudioPlayer:
    """Audio player using Reachy Mini's media system.
    
    Similar to linux-voice-assistant's MpvMediaPlayer but using GStreamer.
    """

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
        self._playback_thread: Optional[threading.Thread] = None

    def set_reachy_mini(self, reachy_mini) -> None:
        """Set the Reachy Mini instance."""
        self.reachy_mini = reachy_mini

    def play(
        self,
        url: Union[str, List[str]],
        done_callback: Optional[Callable[[], None]] = None,
        stop_first: bool = True,
    ) -> None:
        """Play audio file(s) or URL(s).
        
        Args:
            url: Single URL/path or list of URLs/paths to play
            done_callback: Called when all playback is finished
            stop_first: Stop current playback before starting new
        """
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
        """Play the next item in the playlist."""
        if not self._playlist or self._stop_flag.is_set():
            self._on_playback_finished()
            return

        next_url = self._playlist.pop(0)
        _LOGGER.debug("Playing %s", next_url)
        self.is_playing = True

        # Start playback in a thread
        self._playback_thread = threading.Thread(
            target=self._play_file, 
            args=(next_url,), 
            daemon=True
        )
        self._playback_thread.start()

    def _play_file(self, file_path: str) -> None:
        """Play an audio file.
        
        For URLs: Download to temp file first.
        Then use push_audio_sample() to play through the GStreamer pipeline.
        """
        temp_file = None
        try:
            # Handle URLs - download first
            if file_path.startswith(("http://", "https://")):
                _LOGGER.debug("Downloading audio from %s", file_path)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                temp_file.close()
                urllib.request.urlretrieve(file_path, temp_file.name)
                file_path = temp_file.name
                _LOGGER.debug("Downloaded to %s", file_path)

            if self._stop_flag.is_set():
                return

            if not os.path.exists(file_path):
                _LOGGER.error("Audio file not found: %s", file_path)
                return

            # Play using Reachy Mini's audio system
            if self.reachy_mini is not None:
                self._play_via_push_audio(file_path)
            else:
                _LOGGER.warning("No reachy_mini instance, cannot play audio")

        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            # Clean up temp file
            if temp_file is not None:
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass
            
            self.is_playing = False
            
            # Play next in playlist or finish
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    def _play_via_push_audio(self, file_path: str) -> None:
        """Play audio using push_audio_sample().
        
        This pushes audio data to the GStreamer playback pipeline.
        Recording and playback pipelines are separate in GStreamer,
        so they can run simultaneously (like in conversation_app).
        """
        # Read audio file
        data, input_samplerate = sf.read(file_path, dtype='float32')
        
        # Get output sample rate
        output_samplerate = self.reachy_mini.media.get_output_audio_samplerate()
        
        # Convert to mono if stereo
        if data.ndim == 2:
            data = data.mean(axis=1)
        
        # Apply volume
        data = data * self._current_volume
        
        # Resample if needed
        if input_samplerate != output_samplerate:
            num_samples = int(len(data) * output_samplerate / input_samplerate)
            data = scipy.signal.resample(data, num_samples)
        
        total_duration = len(data) / output_samplerate
        _LOGGER.debug("Playing %.2fs audio at %dHz", total_duration, output_samplerate)
        
        # Push audio in chunks (like conversation_app's play_loop)
        chunk_duration = 0.02  # 20ms chunks
        chunk_size = int(output_samplerate * chunk_duration)
        
        start_time = time.monotonic()
        samples_pushed = 0
        
        for i in range(0, len(data), chunk_size):
            if self._stop_flag.is_set():
                _LOGGER.debug("Playback stopped")
                return
            
            chunk = data[i:i + chunk_size].astype(np.float32)
            self.reachy_mini.media.push_audio_sample(chunk)
            samples_pushed += len(chunk)
            
            # Pace the pushing to avoid buffer overflow
            # Calculate how much time should have elapsed
            expected_time = samples_pushed / output_samplerate
            actual_time = time.monotonic() - start_time
            sleep_time = expected_time - actual_time - 0.01  # 10ms ahead
            
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        # Wait for playback to complete
        remaining = total_duration - (time.monotonic() - start_time)
        if remaining > 0:
            time.sleep(remaining + 0.05)  # Small buffer
        
        _LOGGER.debug("Audio playback complete")

    def _on_playback_finished(self) -> None:
        """Called when all playback is finished."""
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
        """Pause playback."""
        self.is_playing = False

    def resume(self) -> None:
        """Resume playback."""
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        """Stop playback and clear playlist."""
        self._stop_flag.set()
        
        # Clear the playback buffer
        if self.reachy_mini is not None:
            try:
                if hasattr(self.reachy_mini.media, 'audio'):
                    audio = self.reachy_mini.media.audio
                    if hasattr(audio, 'clear_player'):
                        audio.clear_player()
            except Exception as e:
                _LOGGER.debug("Error clearing player: %s", e)
        
        self._playlist.clear()
        self.is_playing = False

    def duck(self) -> None:
        """Lower volume for ducking."""
        self._current_volume = self._duck_volume

    def unduck(self) -> None:
        """Restore volume after ducking."""
        self._current_volume = self._unduck_volume

    def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        volume = max(0, min(100, volume))
        self._unduck_volume = volume / 100.0
        self._duck_volume = self._unduck_volume / 2
        self._current_volume = self._unduck_volume
