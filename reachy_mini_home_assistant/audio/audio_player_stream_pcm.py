from __future__ import annotations

import time

import numpy as np

from .audio_player_shared import STREAM_FETCH_CHUNK_SIZE, UNTHROTTLED_PREROLL_S


class AudioPlayerStreamPCMMixin:
    @staticmethod
    def _is_pcm_content_type(content_type: str) -> bool:
        return ("audio/l16" in content_type) or ("audio/pcm" in content_type) or ("audio/raw" in content_type)

    @staticmethod
    def _parse_pcm_format(content_type: str) -> tuple[int, int]:
        channels = 1
        sample_rate = 16000
        if ";" in content_type:
            for part in content_type.split(";"):
                token = part.strip()
                if token.startswith("channels="):
                    try:
                        channels = max(1, int(token.split("=", 1)[1]))
                    except Exception:
                        pass
                elif token.startswith("rate="):
                    try:
                        sample_rate = max(8000, int(token.split("=", 1)[1]))
                    except Exception:
                        pass
        return channels, sample_rate

    def _ensure_media_playback_started(self) -> bool:
        acquired = self._gstreamer_lock.acquire(timeout=0.3)
        if not acquired:
            return False
        try:
            self.reachy_mini.media.start_playing()
            return True
        except Exception:
            return False
        finally:
            self._gstreamer_lock.release()

    def _push_audio_float(self, audio_float: np.ndarray, max_wait_s: float = 1.0) -> bool:
        deadline = time.monotonic() + max(0.05, max_wait_s)
        while time.monotonic() < deadline:
            if self._stop_flag.is_set():
                return False
            acquired = self._gstreamer_lock.acquire(timeout=0.1)
            if not acquired:
                continue
            try:
                self.reachy_mini.media.push_audio_sample(audio_float)
                return True
            finally:
                self._gstreamer_lock.release()
        return False

    def _stream_pcm_response(self, response, content_type: str) -> bool:
        channels, sample_rate = self._parse_pcm_format(content_type)
        target_sr = self.reachy_mini.media.get_output_audio_samplerate()
        if target_sr <= 0:
            target_sr = 16000
        if not self._ensure_media_playback_started():
            return False
        remainder = b""
        pushed_any = False
        played_frames = 0
        stream_start = time.monotonic()
        sway_ctx = self._init_stream_sway_context()
        bytes_per_frame = 2 * channels
        for chunk in response.iter_content(chunk_size=STREAM_FETCH_CHUNK_SIZE):
            if self._stop_flag.is_set():
                break
            if not chunk:
                continue
            data = remainder + chunk
            usable_len = (len(data) // bytes_per_frame) * bytes_per_frame
            remainder = data[usable_len:]
            if usable_len == 0:
                continue
            pcm = np.frombuffer(data[:usable_len], dtype=np.int16).astype(np.float32) / 32768.0
            pcm = np.clip(pcm * self._current_volume, -1.0, 1.0).reshape(-1, channels)
            if sample_rate != target_sr and target_sr > 0:
                import scipy.signal

                new_len = int(len(pcm) * target_sr / sample_rate)
                if new_len > 0:
                    pcm = scipy.signal.resample(pcm, new_len, axis=0).astype(np.float32, copy=False)
            target_elapsed = played_frames / float(target_sr)
            actual_elapsed = time.monotonic() - stream_start
            if target_elapsed > UNTHROTTLED_PREROLL_S and target_elapsed > actual_elapsed:
                time.sleep(min(0.05, target_elapsed - actual_elapsed))
            if not self._push_audio_float(pcm):
                continue
            pushed_any = True
            played_frames += int(pcm.shape[0])
            self._feed_stream_sway(sway_ctx, pcm, target_sr)
        self._finalize_stream_sway(sway_ctx)
        return pushed_any
