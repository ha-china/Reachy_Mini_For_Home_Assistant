from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from .audio_player_local import AudioPlayerLocalMixin
from .audio_player_shared import STREAM_FETCH_CHUNK_SIZE, _LOGGER
from .audio_player_stream_decoded import AudioPlayerStreamDecodedMixin
from .audio_player_stream_pcm import AudioPlayerStreamPCMMixin

if TYPE_CHECKING:
    from collections.abc import Callable


class AudioPlayerPlaybackMixin(AudioPlayerLocalMixin, AudioPlayerStreamDecodedMixin, AudioPlayerStreamPCMMixin):
    def play(
        self, url: str | list[str], done_callback: Callable[[], None] | None = None, stop_first: bool = True
    ) -> None:
        if stop_first:
            self.stop()
        self._playlist = [url] if isinstance(url, str) else list(url)
        self._done_callback = done_callback
        self._stop_flag.clear()
        if self._playback_thread and self._playback_thread.is_alive():
            _LOGGER.warning("Previous playback still active, stopping it")
            self.stop()
        self._play_next()

    def _play_next(self) -> None:
        if not self._playlist or self._stop_flag.is_set():
            self._on_playback_finished()
            return
        next_url = self._playlist.pop(0)
        _LOGGER.debug("Playing %s", next_url)
        self.is_playing = True
        self._playback_thread = threading.Thread(target=self._play_file, args=(next_url,), daemon=True)
        self._playback_thread.start()

    def _play_file(self, file_path: str) -> None:
        try:
            if file_path.startswith(("http://", "https://")):
                import requests

                source_url = file_path
                streamed = False
                cached_audio = bytearray()
                content_type = ""
                try:
                    with requests.get(source_url, stream=True, timeout=(5.0, 30.0)) as response:
                        response.raise_for_status()
                        content_type = (response.headers.get("Content-Type") or "").lower()
                        stream_iter = response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE)

                        def caching_iter_content(chunk_size: int = STREAM_FETCH_CHUNK_SIZE):
                            del chunk_size
                            for chunk in stream_iter:
                                if chunk:
                                    cached_audio.extend(chunk)
                                    yield chunk

                        adapted_response = self._iterator_response_adapter(caching_iter_content())
                        if self._is_pcm_content_type(content_type):
                            _LOGGER.info("TTS playback mode: streaming_pcm")
                            streamed = self._stream_pcm_response(adapted_response, content_type)
                        else:
                            _LOGGER.info("TTS playback mode: streaming_decoded")
                            streamed = self._stream_decoded_response(adapted_response, source_url, content_type)
                        if not streamed:
                            for chunk in stream_iter:
                                if chunk:
                                    cached_audio.extend(chunk)
                except Exception as e:
                    _LOGGER.debug("Streaming TTS failed, fallback to memory playback: %s", e)
                if streamed:
                    return
                _LOGGER.info("TTS playback mode: fallback_memory")
                played = self._play_cached_audio(cached_audio, content_type, source_url=source_url)
                if played:
                    return
                _LOGGER.error("Failed to play cached TTS audio from memory")
                return
            if self._stop_flag.is_set():
                return
            self._play_local_file(file_path)
        except Exception as e:
            _LOGGER.error("Error playing audio: %s", e)
        finally:
            self.is_playing = False
            if self._playlist and not self._stop_flag.is_set():
                self._play_next()
            else:
                self._on_playback_finished()

    @staticmethod
    def _iterator_response_adapter(iterator):
        class _ResponseAdapter:
            def __init__(self, iter_obj) -> None:
                self._iter_obj = iter_obj

            def iter_content(self, chunk_size: int = 8192):
                del chunk_size
                return self._iter_obj

        return _ResponseAdapter(iterator)

    def _on_playback_finished(self) -> None:
        self.is_playing = False
        todo_callback: Callable[[], None] | None = None
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
        self._stop_flag.set()
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass
        self.is_playing = False

    def resume_playback(self) -> None:
        self._stop_flag.clear()
        if self._playlist:
            self._play_next()

    def stop(self) -> None:
        self._stop_flag.set()
        try:
            self.reachy_mini.media.stop_playing()
        except Exception:
            pass
        if self._playback_thread and self._playback_thread.is_alive():
            try:
                self._playback_thread.join(timeout=2.0)
                if self._playback_thread.is_alive():
                    _LOGGER.warning("Playback thread did not stop in time")
            except Exception:
                pass
            self._playback_thread = None
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

    def suspend(self) -> None:
        _LOGGER.info("Suspending AudioPlayer resources...")
        self.stop()
        self._sway_callback = None
        _LOGGER.info("AudioPlayer resources suspended")

    def resume(self) -> None:
        _LOGGER.info("Resuming AudioPlayer resources...")
        self._stop_flag.clear()
        _LOGGER.info("AudioPlayer resources resumed")
