"""Audio analyzer for speech-driven head motion.

This module analyzes TTS audio to generate loudness curves that drive
natural head movements during speech playback.

Inspired by reachy_mini_conversation_app's SwayRollRT algorithm.
"""

import io
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from urllib.request import urlopen

import numpy as np

_LOGGER = logging.getLogger(__name__)

# Analysis parameters (matching reachy_mini_conversation_app)
SAMPLE_RATE = 16000
FRAME_MS = 20
HOP_MS = 50  # Output rate: 20 Hz

# Loudness parameters
SWAY_DB_LOW = -46.0
SWAY_DB_HIGH = -18.0
LOUDNESS_GAMMA = 0.9

# Sway parameters (from reachy_mini_conversation_app)
SWAY_MASTER = 1.5
SWAY_F_PITCH = 2.2
SWAY_A_PITCH_DEG = 4.5
SWAY_F_YAW = 0.6
SWAY_A_YAW_DEG = 7.5
SWAY_F_ROLL = 1.3
SWAY_A_ROLL_DEG = 2.25
SWAY_F_X = 0.35
SWAY_A_X_MM = 4.5
SWAY_F_Y = 0.45
SWAY_A_Y_MM = 3.75
SWAY_F_Z = 0.25
SWAY_A_Z_MM = 2.25


@dataclass
class SwayFrame:
    """A single frame of sway offsets."""
    timestamp_s: float
    x_m: float
    y_m: float
    z_m: float
    roll_rad: float
    pitch_rad: float
    yaw_rad: float


def _rms_dbfs(samples: np.ndarray) -> float:
    """Calculate RMS in dBFS for float32 samples in [-1, 1]."""
    rms = np.sqrt(np.mean(samples ** 2) + 1e-12)
    return 20.0 * math.log10(rms + 1e-12)


def _loudness_gain(db: float) -> float:
    """Normalize dB to [0, 1] with gamma correction."""
    t = (db - SWAY_DB_LOW) / (SWAY_DB_HIGH - SWAY_DB_LOW)
    t = max(0.0, min(1.0, t))
    return t ** LOUDNESS_GAMMA


class AudioAnalyzer:
    """Analyzes audio files to generate sway curves for head motion."""

    def __init__(self):
        self._sway_frames: List[SwayFrame] = []
        self._duration_s: float = 0.0
        self._lock = threading.Lock()
        # Random phases for natural variation
        self._phase_pitch = 0.0
        self._phase_yaw = 0.0
        self._phase_roll = 0.0
        self._phase_x = 0.0
        self._phase_y = 0.0
        self._phase_z = 0.0

    def _randomize_phases(self) -> None:
        """Generate random phase offsets."""
        import random
        self._phase_pitch = random.random() * 2 * math.pi
        self._phase_yaw = random.random() * 2 * math.pi
        self._phase_roll = random.random() * 2 * math.pi
        self._phase_x = random.random() * 2 * math.pi
        self._phase_y = random.random() * 2 * math.pi
        self._phase_z = random.random() * 2 * math.pi

    def analyze_url(self, url: str) -> bool:
        """Download and analyze audio from URL.

        Args:
            url: URL to audio file (mp3, wav, etc.)

        Returns:
            True if analysis succeeded
        """
        try:
            _LOGGER.debug("Downloading audio from: %s", url)
            with urlopen(url, timeout=5) as response:
                audio_data = response.read()

            return self.analyze_bytes(audio_data)
        except Exception as e:
            _LOGGER.error("Failed to download audio: %s", e)
            return False

    def analyze_bytes(self, audio_data: bytes) -> bool:
        """Analyze audio data and generate sway frames.

        Args:
            audio_data: Raw audio file bytes (mp3, wav, etc.)

        Returns:
            True if analysis succeeded
        """
        try:
            # Try to decode audio using soundfile
            import soundfile as sf

            audio_io = io.BytesIO(audio_data)
            samples, sr = sf.read(audio_io, dtype='float32')

            # Convert to mono if stereo
            if samples.ndim == 2:
                samples = samples.mean(axis=1)

            # Resample if needed
            if sr != SAMPLE_RATE:
                samples = self._resample(samples, sr, SAMPLE_RATE)

            return self._analyze_samples(samples)
        except Exception as e:
            _LOGGER.error("Failed to analyze audio: %s", e)
            return False

    def _resample(self, samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
        """Simple linear resampling."""
        if sr_in == sr_out:
            return samples
        n_out = int(len(samples) * sr_out / sr_in)
        t_in = np.linspace(0, 1, len(samples))
        t_out = np.linspace(0, 1, n_out)
        return np.interp(t_out, t_in, samples).astype(np.float32)

    def _analyze_samples(self, samples: np.ndarray) -> bool:
        """Analyze audio samples and generate sway frames."""
        self._randomize_phases()

        hop_samples = int(SAMPLE_RATE * HOP_MS / 1000)
        frame_samples = int(SAMPLE_RATE * FRAME_MS / 1000)

        frames: List[SwayFrame] = []
        t = 0.0
        hop_dt = HOP_MS / 1000.0

        pos = 0
        while pos + frame_samples <= len(samples):
            frame = samples[pos:pos + frame_samples]
            db = _rms_dbfs(frame)
            loud = _loudness_gain(db) * SWAY_MASTER

            # Generate sway offsets (matching reachy_mini_conversation_app)
            pitch = (math.radians(SWAY_A_PITCH_DEG) * loud *
                     math.sin(2 * math.pi * SWAY_F_PITCH * t + self._phase_pitch))
            yaw = (math.radians(SWAY_A_YAW_DEG) * loud *
                   math.sin(2 * math.pi * SWAY_F_YAW * t + self._phase_yaw))
            roll = (math.radians(SWAY_A_ROLL_DEG) * loud *
                    math.sin(2 * math.pi * SWAY_F_ROLL * t + self._phase_roll))
            x_mm = SWAY_A_X_MM * loud * math.sin(2 * math.pi * SWAY_F_X * t + self._phase_x)
            y_mm = SWAY_A_Y_MM * loud * math.sin(2 * math.pi * SWAY_F_Y * t + self._phase_y)
            z_mm = SWAY_A_Z_MM * loud * math.sin(2 * math.pi * SWAY_F_Z * t + self._phase_z)

            frames.append(SwayFrame(
                timestamp_s=t,
                x_m=x_mm / 1000.0,
                y_m=y_mm / 1000.0,
                z_m=z_mm / 1000.0,
                roll_rad=roll,
                pitch_rad=pitch,
                yaw_rad=yaw,
            ))

            pos += hop_samples
            t += hop_dt

        with self._lock:
            self._sway_frames = frames
            self._duration_s = t

        _LOGGER.info("Analyzed audio: %.2fs, %d frames", t, len(frames))
        return True

    def get_frame_at(self, t: float) -> Optional[SwayFrame]:
        """Get sway frame at time t (seconds).

        Args:
            t: Time in seconds from start of audio

        Returns:
            SwayFrame or None if out of range
        """
        with self._lock:
            if not self._sway_frames:
                return None

            # Find frame index
            hop_dt = HOP_MS / 1000.0
            idx = int(t / hop_dt)

            if idx < 0:
                return self._sway_frames[0]
            if idx >= len(self._sway_frames):
                return None

            return self._sway_frames[idx]

    def clear(self) -> None:
        """Clear analyzed data."""
        with self._lock:
            self._sway_frames = []
            self._duration_s = 0.0

    @property
    def duration(self) -> float:
        """Get duration of analyzed audio in seconds."""
        with self._lock:
            return self._duration_s

    @property
    def frame_count(self) -> int:
        """Get number of sway frames."""
        with self._lock:
            return len(self._sway_frames)


class SpeechSwayPlayer:
    """Plays pre-analyzed sway animation synchronized with TTS playback."""

    def __init__(self, set_offsets_callback: Callable[[Tuple[float, ...]], None]):
        """Initialize player.

        Args:
            set_offsets_callback: Function to call with (x, y, z, roll, pitch, yaw) offsets
        """
        self._set_offsets = set_offsets_callback
        self._analyzer = AudioAnalyzer()
        self._playing = False
        self._start_time: float = 0.0
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def prepare(self, url: str) -> bool:
        """Prepare sway animation by downloading and analyzing audio.

        Call this when TTS URL is received (e.g., at RUN_START).

        Args:
            url: URL to TTS audio file

        Returns:
            True if preparation succeeded
        """
        self.stop()
        return self._analyzer.analyze_url(url)

    def start(self) -> None:
        """Start playing sway animation.

        Call this when TTS playback starts (e.g., at TTS_START).
        """
        if self._playing:
            return

        if self._analyzer.frame_count == 0:
            _LOGGER.warning("No sway data to play")
            return

        self._stop_event.clear()
        self._playing = True
        self._start_time = time.monotonic()

        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()
        _LOGGER.debug("Started sway playback")

    def stop(self) -> None:
        """Stop sway animation playback."""
        if not self._playing:
            return

        self._stop_event.set()
        self._playing = False

        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None

        # Reset offsets to zero
        self._set_offsets((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        _LOGGER.debug("Stopped sway playback")

    def _playback_loop(self) -> None:
        """Playback loop that outputs sway frames at correct timing."""
        hop_dt = HOP_MS / 1000.0

        while not self._stop_event.is_set():
            elapsed = time.monotonic() - self._start_time
            frame = self._analyzer.get_frame_at(elapsed)

            if frame is None:
                # End of animation
                break

            # Output offsets
            self._set_offsets((
                frame.x_m,
                frame.y_m,
                frame.z_m,
                frame.roll_rad,
                frame.pitch_rad,
                frame.yaw_rad,
            ))

            # Sleep until next frame
            next_time = self._start_time + (int(elapsed / hop_dt) + 1) * hop_dt
            sleep_time = next_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Reset offsets when done
        self._set_offsets((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        self._playing = False

    @property
    def is_playing(self) -> bool:
        """Check if sway animation is currently playing."""
        return self._playing
