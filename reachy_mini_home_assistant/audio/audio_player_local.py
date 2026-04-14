from __future__ import annotations

import time

from .audio_player_shared import MOVEMENT_LATENCY_S, STREAM_FETCH_CHUNK_SIZE, _LOGGER, sniff_audio_content_type


class AudioPlayerLocalMixin:
    def _play_cached_audio(self, audio_bytes: bytes | bytearray, content_type: str, source_url: str = "") -> bool:
        if not audio_bytes:
            return False
        audio_data = bytes(audio_bytes)
        if (not content_type) or (content_type == "application/octet-stream"):
            sniffed = sniff_audio_content_type(audio_data[: min(len(audio_data), 64)])
            if sniffed:
                content_type = sniffed
        mem_iter = (
            audio_data[i : i + STREAM_FETCH_CHUNK_SIZE] for i in range(0, len(audio_data), STREAM_FETCH_CHUNK_SIZE)
        )
        adapted_response = self._iterator_response_adapter(mem_iter)
        if self._is_pcm_content_type(content_type):
            return self._stream_pcm_response(adapted_response, content_type)
        if self._stream_decoded_response(adapted_response, source_url or "memory-cache", content_type):
            return True
        return self._play_cached_audio_via_tempfile(audio_data, content_type, source_url)

    def _play_cached_audio_via_tempfile(self, audio_data: bytes, content_type: str, source_url: str) -> bool:
        import os
        import tempfile

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=self._guess_audio_suffix(content_type, source_url)
            ) as tmp:
                tmp.write(audio_data)
                temp_path = tmp.name
            self._play_local_file(temp_path)
            return True
        except Exception as e:
            _LOGGER.debug("Tempfile fallback playback failed: %s", e)
            return False
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def _guess_audio_suffix(self, content_type: str, source_url: str) -> str:
        from urllib.parse import urlparse

        ct = (content_type or "").split(";", 1)[0].strip().lower()
        mapping = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/aac": ".aac",
            "audio/mp4": ".m4a",
            "audio/ogg": ".ogg",
            "application/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/webm": ".webm",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/flac": ".flac",
            "audio/x-flac": ".flac",
        }
        if ct in mapping:
            return mapping[ct]
        try:
            path = urlparse(source_url).path
            if "." in path:
                suffix = "." + path.rsplit(".", 1)[1]
                if len(suffix) <= 8:
                    return suffix
        except Exception:
            pass
        return ".bin"

    def _play_local_file(self, file_path: str) -> None:
        try:
            duration: float | None = None
            sway_frames: list[dict] = []
            try:
                import soundfile as sf

                info = sf.info(file_path)
                if info.samplerate > 0 and info.frames > 0:
                    duration = float(info.frames) / float(info.samplerate)
            except Exception:
                duration = None
            if self._sway_callback is not None:
                try:
                    import soundfile as sf

                    data, sample_rate = sf.read(file_path)
                    if duration is None and sample_rate > 0:
                        duration = len(data) / sample_rate
                    from ..motion.speech_sway import SpeechSwayRT

                    sway = SpeechSwayRT()
                    sway_frames = sway.feed(data, sample_rate)
                except Exception:
                    sway_frames = []
            self.reachy_mini.media.play_sound(file_path)
            start_time = time.monotonic()
            frame_duration = 0.05
            frame_idx = 0
            has_duration = (duration is not None) and (duration > 0)
            duration_s = duration if has_duration and duration is not None else 0.0
            max_duration = (duration_s * 1.5) if has_duration else 60.0
            playback_timeout = start_time + max_duration
            sway_base_ts = start_time + MOVEMENT_LATENCY_S
            while True:
                now = time.monotonic()
                if now > playback_timeout:
                    _LOGGER.warning("Audio playback timeout (%.1fs), stopping", max_duration)
                    self.reachy_mini.media.stop_playing()
                    break
                if self._stop_flag.is_set():
                    self.reachy_mini.media.stop_playing()
                    break
                if has_duration:
                    if (now - start_time) >= duration_s:
                        break
                else:
                    try:
                        if not bool(self.reachy_mini.media.is_playing()):
                            break
                    except Exception:
                        pass
                if self._sway_callback and frame_idx < len(sway_frames):
                    target_frame = frame_idx
                    while target_frame < len(sway_frames) and now >= (sway_base_ts + target_frame * frame_duration):
                        target_frame += 1
                    while frame_idx < target_frame and frame_idx < len(sway_frames):
                        self._sway_callback(sway_frames[frame_idx])
                        frame_idx += 1
                next_sleep = 0.02
                if self._sway_callback and frame_idx < len(sway_frames):
                    next_sway_ts = sway_base_ts + frame_idx * frame_duration
                    next_sleep = min(next_sleep, max(0.0, next_sway_ts - now))
                time.sleep(next_sleep)
        finally:
            if self._sway_callback:
                try:
                    self._sway_callback(
                        {"pitch_rad": 0.0, "yaw_rad": 0.0, "roll_rad": 0.0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0}
                    )
                except Exception:
                    pass
