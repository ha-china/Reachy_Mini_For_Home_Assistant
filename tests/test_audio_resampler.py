"""Tests for the Sendspin/TTS streaming resampler."""

import numpy as np
import pytest

from reachy_mini_home_assistant.audio.audio_player_shared import AudioResampler


def _tone(seconds: float, rate: int, channels: int = 2) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    wave = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    return np.tile(wave.reshape(-1, 1), (1, channels))


class TestAudioResampler:
    def test_equal_rates_preserve_length(self):
        r = AudioResampler(16000, 16000, 2)
        chunk = _tone(0.032, 16000)
        out = r.process(chunk)
        assert len(out) == pytest.approx(len(chunk), abs=2)

    def test_downsample_produces_expected_average_rate(self):
        r = AudioResampler(48000, 16000, 2)
        total_out = 0
        n_chunks = 50
        for _ in range(n_chunks):
            out = r.process(_tone(0.01, 48000))  # 480 frames in
            total_out += out.shape[0]
        # Allow the filter group delay to explain a small deficit
        assert total_out == pytest.approx(n_chunks * 160, rel=0.1)

    def test_output_is_float32_stereo(self):
        r = AudioResampler(48000, 16000, 2)
        out = r.process(_tone(0.05, 48000))
        assert out.ndim == 2
        assert out.shape[1] == 2
        assert out.dtype == np.float32

    def test_no_nan_or_inf_across_chunks(self):
        r = AudioResampler(44100, 16000, 1)
        for _ in range(20):
            out = r.process(_tone(0.02, 44100, channels=1))
            assert np.isfinite(out).all()

    def test_no_signal_clipping(self):
        r = AudioResampler(48000, 16000, 2)
        out = r.process(_tone(0.1, 48000))
        assert np.abs(out).max() <= 0.31
