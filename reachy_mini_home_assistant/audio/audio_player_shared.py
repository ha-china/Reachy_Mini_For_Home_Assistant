from __future__ import annotations

import hashlib
import logging
import socket
from urllib.parse import urlparse, urlunparse

import numpy as np

_LOGGER = logging.getLogger(__name__)

STREAM_FETCH_CHUNK_SIZE = 2048
UNTHROTTLED_PREROLL_S = 0.35
SENDSPIN_LOCAL_BUFFER_CAPACITY_BYTES = 32_000_000
SENDSPIN_HIGH_WATERMARK_BYTES = 24_000_000
SENDSPIN_LATE_DROP_GRACE_US = 150_000
SENDSPIN_SCHEDULE_AHEAD_LIMIT_US = 2_000_000


def sniff_audio_content_type(audio_bytes: bytes) -> str:
    if len(audio_bytes) >= 12:
        if audio_bytes.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE":
            return "audio/wav"
        if audio_bytes.startswith(b"fLaC"):
            return "audio/flac"
        if audio_bytes.startswith(b"OggS"):
            return "audio/ogg"
        if audio_bytes[:4] == b"ID3":
            return "audio/mpeg"
        if audio_bytes[:2] == b"\xff\xfb" or audio_bytes[:2] == b"\xff\xf3" or audio_bytes[:2] == b"\xff\xf2":
            return "audio/mpeg"
        if audio_bytes[:4] == b"ADIF" or (audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xF0) == 0xF0):
            return "audio/aac"
        if audio_bytes[4:8] == b"ftyp":
            return "audio/mp4"
        if audio_bytes.startswith(b"\x1aE\xdf\xa3"):
            return "audio/webm"
    return ""


def rewrite_local_service_url(url: str, host_override: str | None) -> str:
    if not host_override:
        return url
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return url
        hostname = (parsed.hostname or "").lower()
        if hostname not in {"localhost", "127.0.0.1", "::1", "homeassistant.local", "homeassistant"}:
            return url
        netloc = host_override
        if parsed.port is not None:
            netloc = f"{host_override}:{parsed.port}"
        return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        return url


def get_stable_client_id() -> str:
    try:
        hostname = socket.gethostname()
        hash_input = f"reachy-mini-{hostname}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    except Exception:
        return "reachy-mini-default"


class AudioResampler:
    """Stateful streaming resampler with a scipy fallback.

    soxr's ResampleStream keeps filter state across chunks (no FFT periodicity
    artefacts between chunks) at a fraction of the CPU cost of
    scipy.signal.resample on the robot's ARM SoC. Output arrives with a
    small constant filter delay that continuous playback absorbs.
    """

    def __init__(self, in_rate: int, out_rate: int, channels: int, quality: str = "MQ") -> None:
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._channels = max(1, int(channels))
        self._stream = None
        try:
            import soxr

            self._stream = soxr.ResampleStream(
                in_rate, out_rate, self._channels, dtype="float32", quality=quality
            )
        except ImportError:
            _LOGGER.info("soxr not installed; falling back to scipy resampling")
        except Exception:
            _LOGGER.exception("soxr resampler init failed; falling back to scipy")

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Resample one (frames, channels) float32 chunk."""
        if self._stream is not None:
            out = self._stream.resample_chunk(audio)
            return np.ascontiguousarray(out, dtype=np.float32)
        import scipy.signal

        new_length = int(len(audio) * self.out_rate / self.in_rate)
        if new_length <= 0:
            return audio[:0]
        return scipy.signal.resample(audio, new_length, axis=0).astype(np.float32, copy=False)
