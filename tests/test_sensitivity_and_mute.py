"""Regression tests: sensitivity cutoffs apply, mute state persists."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aioesphomeapi.api_pb2 import MediaPlayerCommandRequest  # type: ignore[attr-defined]
from aioesphomeapi.model import MediaPlayerCommand

from reachy_mini_home_assistant.entities.entity import MediaPlayerEntity
from reachy_mini_home_assistant.preferences import Preferences
from reachy_mini_home_assistant.voice_assistant import VoiceAssistantService

_MODELS_DIR = Path(__file__).resolve().parent.parent / "reachy_mini_home_assistant" / "wakewords"


class FakeMusicPlayer:
    def __init__(self):
        self.volumes = []

    def set_volume(self, volume):
        self.volumes.append(volume)

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass


class FakeState:
    def __init__(self):
        self.preferences = Preferences()
        self.saved = 0

    def save_preferences(self):
        self.saved += 1


class FakeServer:
    def __init__(self):
        self.state = FakeState()


def _make_entity() -> MediaPlayerEntity:
    server = FakeServer()
    return MediaPlayerEntity(
        server=server,
        key=1,
        name="Media Player",
        object_id="media_player",
        music_player=FakeMusicPlayer(),
        announce_player=FakeMusicPlayer(),
    )


def _command(command) -> MediaPlayerCommandRequest:
    return MediaPlayerCommandRequest(key=1, command=command, has_command=True)


def _volume(volume: float) -> MediaPlayerCommandRequest:
    return MediaPlayerCommandRequest(key=1, volume=volume, has_volume=True)


class TestSensitivityCutoff:
    def test_default_sensitivity_reproduces_stock_cutoff(self):
        """Sensitivity 0.5 must reproduce each model's own tuned cutoff."""
        for model_file in ("stop.json", "okay_nabu.json"):
            cfg = json.loads((_MODELS_DIR / model_file).read_text(encoding="utf-8"))
            stock = cfg["micro"]["probability_cutoff"]

            class FakeModel:
                _stock_probability_cutoff = stock

            cutoff = VoiceAssistantService._sensitivity_cutoff(FakeModel(), 0.5)
            assert cutoff == pytest.approx(stock)

    def test_higher_sensitivity_lowers_cutoff(self):
        class FakeModel:
            _stock_probability_cutoff = 0.5

        low = VoiceAssistantService._sensitivity_cutoff(FakeModel(), 0.2)
        high = VoiceAssistantService._sensitivity_cutoff(FakeModel(), 0.8)
        assert low > 0.5 > high

    def test_cutoff_clamped_to_sane_bounds(self):
        class FakeModel:
            _stock_probability_cutoff = 0.5

        assert VoiceAssistantService._sensitivity_cutoff(FakeModel(), 0.0) <= 0.99
        assert VoiceAssistantService._sensitivity_cutoff(FakeModel(), 1.0) >= 0.05


class TestMutePersistence:
    def test_mute_persists_flag_and_silences(self):
        entity = _make_entity()
        msgs = list(entity.handle_message(_command(MediaPlayerCommand.MUTE)))
        assert entity.muted is True
        assert entity.server.state.preferences.media_muted is True
        assert entity.music_player.volumes[-1] == 0
        assert len(msgs) == 1  # state update yielded

    def test_unmute_restores_tracked_volume(self):
        entity = _make_entity()
        entity.volume = 0.6
        list(entity.handle_message(_command(MediaPlayerCommand.MUTE)))
        list(entity.handle_message(_command(MediaPlayerCommand.UNMUTE)))
        assert entity.muted is False
        assert entity.server.state.preferences.media_muted is False
        assert entity.music_player.volumes[-1] == 60  # pre-mute level restored

    def test_volume_change_while_muted_stays_silent(self):
        entity = _make_entity()
        list(entity.handle_message(_command(MediaPlayerCommand.MUTE)))
        list(entity.handle_message(_volume(0.8)))
        # Stored level tracks the slider, but the DSP stays muted
        assert entity.volume == pytest.approx(0.8)
        assert entity.muted is True
        assert entity.music_player.volumes[-1] == 0
        assert entity.server.state.preferences.media_volume == pytest.approx(0.8)
