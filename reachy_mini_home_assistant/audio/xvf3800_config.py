"""XVF3800 mic-processor tuning applied at media startup.

The SDK's ``apply_audio_config`` ships no defaults — callers pass values
tuned for their app. These are the same parameters the upstream
conversation app applies on identical hardware: a higher AGC ceiling and
gentler echo/noise suppression so the mic array favours picking the user
up over suppressing everything else.

Best-effort by design: absent ReSpeaker (Lite board, dev machines) or an
older SDK simply skips the write.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

AudioControlValue = float | int
AudioStartupParameter = tuple[str, tuple[AudioControlValue, ...]]

WRITE_SETTLE_SECONDS = 0.1

XVF3800_STARTUP_CONFIG: tuple[AudioStartupParameter, ...] = (
    ("PP_AGCMAXGAIN", (10.0,)),
    ("PP_MIN_NS", (0.8,)),
    ("PP_MIN_NN", (0.8,)),
    ("PP_GAMMA_E", (0.5,)),
    ("PP_GAMMA_ETAIL", (0.5,)),
    ("PP_NLATTENONOFF", (0,)),
    ("PP_MGSCALE", (4.0, 1.0, 1.0)),
)


def apply_xvf3800_startup_config(media, *, verify: bool = True) -> bool:
    """Write the tuned XVF3800 parameters via the SDK. Returns True when applied."""
    audio = getattr(media, "audio", None)
    if audio is None:
        _LOGGER.debug("Skipping XVF3800 tuning: media audio is unavailable")
        return False
    apply_audio_config = getattr(audio, "apply_audio_config", None)
    if not callable(apply_audio_config):
        _LOGGER.debug("Skipping XVF3800 tuning: SDK audio config API unavailable")
        return False
    try:
        applied = bool(
            apply_audio_config(
                XVF3800_STARTUP_CONFIG,
                verify=verify,
                write_settle_seconds=WRITE_SETTLE_SECONDS,
            )
        )
    except Exception as e:
        _LOGGER.warning("XVF3800 tuning failed: %s", e)
        return False
    if applied:
        _LOGGER.info("Applied XVF3800 voice tuning (%d parameters)", len(XVF3800_STARTUP_CONFIG))
    else:
        _LOGGER.warning("XVF3800 tuning was not verified after write")
    return applied
