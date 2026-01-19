"""Microphone optimization for ReSpeaker XVF3800.

This module provides utilities for configuring the XMOS XVF3800 audio processor
for optimal voice command recognition at distances up to 2-3 meters.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)


@dataclass
class MicrophonePreferences:
    """User preferences for microphone settings."""

    agc_enabled: Optional[bool] = None
    agc_max_gain: Optional[float] = None
    noise_suppression: Optional[float] = None


@dataclass
class MicrophoneDefaults:
    """Default microphone settings for voice recognition."""

    agc_enabled: bool = True
    agc_max_gain: float = 40.0  # dB (max supported by XVF3800 for quiet mic)
    noise_suppression: float = 15.0  # percentage
    agc_desired_level: float = -12.0  # dB (increased from -18 for louder output)
    agc_time_constant: float = 0.3  # seconds (faster response for voice commands)
    mic_gain: float = 6.0  # linear multiplier (increased from 2.0 for quiet mic)


class MicrophoneOptimizer:
    """Optimizes ReSpeaker XVF3800 microphone settings for voice recognition.

    Key optimizations:
    1. Enable AGC with higher max gain for distant speech
    2. Reduce noise suppression to preserve quiet speech
    3. Increase base microphone gain
    4. Optimize AGC response times for voice commands

    Reference: reachy_mini/src/reachy_mini/media/audio_control_utils.py
    XMOS docs: https://www.xmos.com/documentation/XM-014888-PC/
    """

    def __init__(self, defaults: Optional[MicrophoneDefaults] = None):
        """Initialize the optimizer.

        Args:
            defaults: Default settings to use. If None, uses built-in defaults.
        """
        self.defaults = defaults or MicrophoneDefaults()

    def optimize(
        self,
        respeaker: Any,
        preferences: Optional[MicrophonePreferences] = None
    ) -> bool:
        """Apply optimized microphone settings.

        Args:
            respeaker: ReSpeaker device instance with write() method
            preferences: User preferences that override defaults

        Returns:
            True if optimization was successful, False otherwise
        """
        if respeaker is None:
            _LOGGER.debug("ReSpeaker device not found")
            return False

        prefs = preferences or MicrophonePreferences()

        # Determine actual values (preferences override defaults)
        agc_enabled = (
            prefs.agc_enabled if prefs.agc_enabled is not None
            else self.defaults.agc_enabled
        )
        agc_max_gain = (
            prefs.agc_max_gain if prefs.agc_max_gain is not None
            else self.defaults.agc_max_gain
        )
        noise_suppression = (
            prefs.noise_suppression if prefs.noise_suppression is not None
            else self.defaults.noise_suppression
        )

        success = True

        # ========== 1. AGC (Automatic Gain Control) Settings ==========
        success &= self._set_agc_enabled(respeaker, agc_enabled, prefs.agc_enabled is not None)
        success &= self._set_agc_max_gain(respeaker, agc_max_gain, prefs.agc_max_gain is not None)
        success &= self._set_agc_desired_level(respeaker, self.defaults.agc_desired_level)
        success &= self._set_agc_time_constant(respeaker, self.defaults.agc_time_constant)

        # ========== 2. Base Microphone Gain ==========
        success &= self._set_mic_gain(respeaker, self.defaults.mic_gain)

        # ========== 3. Noise Suppression Settings ==========
        success &= self._set_noise_suppression(respeaker, noise_suppression, prefs.noise_suppression is not None)

        # ========== 4. Echo Cancellation Settings ==========
        success &= self._set_echo_cancellation(respeaker, True)

        # ========== 5. High-pass filter ==========
        success &= self._set_highpass_filter(respeaker, True)

        _LOGGER.info(
            "Microphone settings initialized (AGC=%s, MaxGain=%.0fdB, NoiseSuppression=%.0f%%)",
            "ON" if agc_enabled else "OFF", agc_max_gain, noise_suppression
        )

        return success

    def _set_agc_enabled(self, respeaker: Any, enabled: bool, from_prefs: bool) -> bool:
        """Set AGC on/off."""
        try:
            respeaker.write("PP_AGCONOFF", [1 if enabled else 0])
            _LOGGER.info(
                "AGC %s (PP_AGCONOFF=%d)%s",
                "enabled" if enabled else "disabled",
                1 if enabled else 0,
                " [from preferences]" if from_prefs else " [default]"
            )
            return True
        except Exception as e:
            _LOGGER.debug("Could not set AGC: %s", e)
            return False

    def _set_agc_max_gain(self, respeaker: Any, gain: float, from_prefs: bool) -> bool:
        """Set AGC maximum gain."""
        try:
            respeaker.write("PP_AGCMAXGAIN", [gain])
            _LOGGER.info(
                "AGC max gain set (PP_AGCMAXGAIN=%.1fdB)%s",
                gain,
                " [from preferences]" if from_prefs else " [default]"
            )
            return True
        except Exception as e:
            _LOGGER.debug("Could not set PP_AGCMAXGAIN: %s", e)
            return False

    def _set_agc_desired_level(self, respeaker: Any, level: float) -> bool:
        """Set AGC desired output level."""
        try:
            respeaker.write("PP_AGCDESIREDLEVEL", [level])
            _LOGGER.debug("AGC desired level set (PP_AGCDESIREDLEVEL=%.1fdB)", level)
            return True
        except Exception as e:
            _LOGGER.debug("Could not set PP_AGCDESIREDLEVEL: %s", e)
            return False

    def _set_agc_time_constant(self, respeaker: Any, time_constant: float) -> bool:
        """Set AGC time constant."""
        try:
            respeaker.write("PP_AGCTIME", [time_constant])
            _LOGGER.debug("AGC time constant set (PP_AGCTIME=%.1fs)", time_constant)
            return True
        except Exception as e:
            _LOGGER.debug("Could not set PP_AGCTIME: %s", e)
            return False

    def _set_mic_gain(self, respeaker: Any, gain: float) -> bool:
        """Set base microphone gain."""
        try:
            respeaker.write("AUDIO_MGR_MIC_GAIN", [gain])
            _LOGGER.info("Microphone gain increased (AUDIO_MGR_MIC_GAIN=%.1f)", gain)
            return True
        except Exception as e:
            _LOGGER.debug("Could not set AUDIO_MGR_MIC_GAIN: %s", e)
            return False

    def _set_noise_suppression(self, respeaker: Any, suppression: float, from_prefs: bool) -> bool:
        """Set noise suppression level.

        Args:
            suppression: Suppression strength as percentage (0-100)
        """
        # PP_MIN_NS: minimum noise suppression threshold
        # PP_MIN_NS = 0.85 means "keep at least 85% of signal" = 15% max suppression
        pp_min_ns = 1.0 - (suppression / 100.0)

        try:
            respeaker.write("PP_MIN_NS", [pp_min_ns])
            _LOGGER.info(
                "Noise suppression set to %.0f%% strength (PP_MIN_NS=%.2f)%s",
                suppression, pp_min_ns,
                " [from preferences]" if from_prefs else " [default]"
            )
        except Exception as e:
            _LOGGER.debug("Could not set PP_MIN_NS: %s", e)
            return False

        # PP_MIN_NN: minimum noise floor estimation (match PP_MIN_NS)
        try:
            respeaker.write("PP_MIN_NN", [pp_min_ns])
            _LOGGER.debug("Noise floor threshold set (PP_MIN_NN=%.2f)", pp_min_ns)
        except Exception as e:
            _LOGGER.debug("Could not set PP_MIN_NN: %s", e)

        return True

    def _set_echo_cancellation(self, respeaker: Any, enabled: bool) -> bool:
        """Set echo cancellation on/off."""
        try:
            respeaker.write("PP_ECHOONOFF", [1 if enabled else 0])
            _LOGGER.debug(
                "Echo cancellation %s (PP_ECHOONOFF=%d)",
                "enabled" if enabled else "disabled", 1 if enabled else 0
            )
            return True
        except Exception as e:
            _LOGGER.debug("Could not set PP_ECHOONOFF: %s", e)
            return False

    def _set_highpass_filter(self, respeaker: Any, enabled: bool) -> bool:
        """Set high-pass filter on/off."""
        try:
            respeaker.write("AEC_HPFONOFF", [1 if enabled else 0])
            _LOGGER.debug(
                "High-pass filter %s (AEC_HPFONOFF=%d)",
                "enabled" if enabled else "disabled", 1 if enabled else 0
            )
            return True
        except Exception as e:
            _LOGGER.debug("Could not set AEC_HPFONOFF: %s", e)
            return False
