"""Tests for the voice session flow (wake -> listen -> TTS finish transitions)."""

import asyncio
from types import SimpleNamespace

from aioesphomeapi.api_pb2 import VoiceAssistantAnnounceFinished, VoiceAssistantRequest

from reachy_mini_home_assistant.protocol.session_flow import (
    cancel_delayed_continue_conversation,
    get_or_create_conversation_id,
    on_wakeup_sound_finished,
    queue_voice_request_after_wakeup,
    start_audio_streaming,
    tts_finished,
)


class FakeTTSPlayer:
    def __init__(self):
        self.played = []

    def play(self, sound, done_callback=None):
        self.played.append(sound)
        if done_callback is not None:
            done_callback()


class FakeStopWord:
    id = "stop"


class FakeState:
    def __init__(self):
        self.tts_player = FakeTTSPlayer()
        self.wakeup_sound = "/sounds/wake_word_triggered.flac"
        self.active_wake_words = {"okay_nabu"}
        self.stop_word = FakeStopWord()
        self.is_muted = False
        self.preferences = SimpleNamespace(continuous_conversation=False)


class FakeProtocol:
    """Minimal stand-in exposing the attributes session_flow operates on."""

    def __init__(self):
        self.state = FakeState()
        self.sent = []
        self._is_streaming_audio = False
        self._pipeline_active = False
        self._pending_voice_request = None
        self._continue_conversation = False
        self._conversation_id = None
        self._last_conversation_time = 0.0
        self._conversation_timeout = 300.0
        self._continue_conversation_timer = None
        self._idle_return_timer = None
        self._stop_word_states = []
        self.motion_runs = []
        self.unducked = False

    def send_messages(self, msgs):
        self.sent.extend(msgs)

    def _set_stop_word_active(self, active):
        self._stop_word_states.append(active)

    def _run_motion_state(self, context, callback_name):
        self.motion_runs.append((context, callback_name))

    def unduck(self):
        self.unducked = True

    def _schedule_delayed_idle_return(self):
        pass

    def _reachy_on_listening(self):
        pass


def test_wake_sound_finish_starts_streaming():
    p = FakeProtocol()
    queue_voice_request_after_wakeup(p, wake_word_phrase="okay nabu", conversation_id="conv-1")
    assert p._pending_voice_request == ("okay nabu", "conv-1")
    assert not p._is_streaming_audio

    on_wakeup_sound_finished(p)

    assert p._pending_voice_request is None
    assert p._is_streaming_audio is True
    assert len(p.sent) == 1
    req = p.sent[0]
    assert isinstance(req, VoiceAssistantRequest)
    assert req.start is True
    assert req.wake_word_phrase == "okay nabu"
    assert req.conversation_id == "conv-1"


def test_start_audio_streaming_immediate():
    p = FakeProtocol()
    start_audio_streaming(p, wake_word_phrase="hey", conversation_id="c")

    assert p._is_streaming_audio is True
    assert len(p.sent) == 1
    assert p.sent[0].start is True


def test_tts_finished_without_continue_resets_session():
    p = FakeProtocol()
    p._pipeline_active = True
    p._is_streaming_audio = True
    p._continue_conversation = False
    p.state.active_wake_words.add("stop")

    tts_finished(p)

    assert p._pipeline_active is False
    assert p._is_streaming_audio is False
    assert p.unducked is True
    assert "stop" not in p.state.active_wake_words
    assert p._stop_word_states == [False]
    assert p.motion_runs == [("speaking_end", "on_speaking_end")]
    assert any(isinstance(m, VoiceAssistantAnnounceFinished) for m in p.sent)


def test_tts_finished_with_continue_keeps_pipeline_and_schedules():
    p = FakeProtocol()
    p._pipeline_active = True
    p._continue_conversation = True
    p.state.preferences.continuous_conversation = True

    try:
        tts_finished(p)
        assert p._pipeline_active is True  # held during settle delay
        assert p._continue_conversation_timer is not None  # continuation scheduled
        assert p._pending_voice_request is None  # queued by the timer, not immediately

        # After the settle delay the continuation runs: wakeup sound replays and
        # its completion callback immediately re-arms audio streaming.
        import time

        time.sleep(0.7)
        assert p.state.tts_player.played  # wakeup sound replayed
        assert p._is_streaming_audio is True
        start_requests = [m for m in p.sent if isinstance(m, VoiceAssistantRequest) and m.start]
        assert len(start_requests) >= 1
    finally:
        cancel_delayed_continue_conversation(p)


def test_conversation_id_reused_within_timeout():
    p = FakeProtocol()
    p._conversation_timeout = 300.0

    first = get_or_create_conversation_id(p)
    assert first == get_or_create_conversation_id(p)
    assert p._last_conversation_time > 0


def test_conversation_id_recreated_after_timeout():
    import time

    p = FakeProtocol()
    p._conversation_timeout = 1.0
    p._conversation_id = "old"
    p._last_conversation_time = time.time() - 10

    new_id = get_or_create_conversation_id(p)
    assert new_id != "old"


def test_streaming_event_loop_compat():
    """session_flow sends protobufs; ensure no loop-bound state is required."""
    async def run():
        p = FakeProtocol()
        start_audio_streaming(p, wake_word_phrase="w")
        return p._is_streaming_audio

    assert asyncio.run(run()) is True
