from __future__ import annotations

import hashlib
import logging
import socket

_LOGGER = logging.getLogger(__name__)

MOVEMENT_LATENCY_S = 0.2
SWAY_FRAME_DT_S = 0.05
STREAM_FETCH_CHUNK_SIZE = 2048
UNTHROTTLED_PREROLL_S = 0.35
SENDSPIN_LOCAL_BUFFER_CAPACITY_BYTES = 32_000_000
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


def get_stable_client_id() -> str:
    try:
        hostname = socket.gethostname()
        hash_input = f"reachy-mini-{hostname}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    except Exception:
        return "reachy-mini-default"
