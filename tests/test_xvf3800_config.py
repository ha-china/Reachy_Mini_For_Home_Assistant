"""XVF3800 startup tuning: values mirror the upstream conversation app."""

from reachy_mini_home_assistant.audio.xvf3800_config import (
    XVF3800_STARTUP_CONFIG,
    apply_xvf3800_startup_config,
)


def test_tuned_parameters_match_upstream_conversation_app():
    # Locked against reference/reachy_mini_conversation_app audio/startup_config.py
    expected = (
        ("PP_AGCMAXGAIN", (10.0,)),
        ("PP_MIN_NS", (0.8,)),
        ("PP_MIN_NN", (0.8,)),
        ("PP_GAMMA_E", (0.5,)),
        ("PP_GAMMA_ETAIL", (0.5,)),
        ("PP_NLATTENONOFF", (0,)),
        ("PP_MGSCALE", (4.0, 1.0, 1.0)),
    )
    assert XVF3800_STARTUP_CONFIG == expected


class _FakeAudio:
    def __init__(self, *, fail=False):
        self.received = None
        self._fail = fail

    def apply_audio_config(self, config, *, verify=True, write_settle_seconds=0.1):
        if self._fail:
            raise OSError("no respeaker")
        self.received = tuple(config)
        return True


class _FakeMedia:
    def __init__(self, audio):
        self.audio = audio


def test_apply_writes_config_via_sdk():
    audio = _FakeAudio()
    assert apply_xvf3800_startup_config(_FakeMedia(audio)) is True
    assert audio.received == XVF3800_STARTUP_CONFIG


def test_apply_skips_when_audio_missing():
    class _NoAudio:
        audio = None

    assert apply_xvf3800_startup_config(_NoAudio()) is False


def test_apply_skips_on_old_sdk():
    class _OldAudio:
        pass  # no apply_audio_config attribute

    assert apply_xvf3800_startup_config(_FakeMedia(_OldAudio())) is False


def test_apply_swallows_usb_errors():
    assert apply_xvf3800_startup_config(_FakeMedia(_FakeAudio(fail=True))) is False
