"""Voice pipeline helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantTimerEventType

from ..core.util import call_all

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import VoiceAssistantTimerEventResponse  # type: ignore[attr-defined]
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


def handle_voice_event(
    protocol: "VoiceSatelliteProtocol", event_type: VoiceAssistantEventType, data: dict[str, str]
) -> None:
    _LOGGER.debug("Voice event: type=%s, data=%s", event_type.name, data)

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
        protocol._pipeline_active = True
        protocol._tts_url = data.get("url")
        protocol._tts_played = False
        protocol._continue_conversation = False
        protocol._reachy_on_listening()
        return

    if event_type in (
        VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
        VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
    ):
        protocol._is_streaming_audio = False
        protocol._reachy_on_thinking()
        return

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
        if data.get("tts_start_streaming") == "1":
            protocol.play_tts()
        return

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
        if data.get("continue_conversation") == "1":
            protocol._continue_conversation = True
        return

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_START:
        _LOGGER.debug("TTS_START event received, triggering speaking animation")
        protocol._reachy_on_speaking()
        return

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
        protocol._tts_url = data.get("url")
        protocol.play_tts()
        return

    if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
        protocol._is_streaming_audio = False
        if not protocol._tts_played:
            protocol._pipeline_active = False
            protocol._tts_finished()
        protocol._tts_played = False


def handle_timer_event(
    protocol: "VoiceSatelliteProtocol",
    event_type: VoiceAssistantTimerEventType,
    msg: "VoiceAssistantTimerEventResponse",
) -> None:
    _LOGGER.debug("Timer event: type=%s", event_type.name)
    if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED and not protocol._timer_finished:
        protocol.state.active_wake_words.add(protocol.state.stop_word.id)
        protocol._set_stop_word_active(True)
        protocol._timer_finished = True
        protocol._timer_ring_start = time.monotonic()
        protocol.duck()
        protocol._play_timer_finished()
        protocol._reachy_on_timer_finished()


def stop(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._pipeline_active = False
    protocol._is_streaming_audio = False
    protocol._continue_conversation = False
    protocol._pending_voice_request = None
    protocol.state.active_wake_words.discard(protocol.state.stop_word.id)
    protocol._set_stop_word_active(False)

    if protocol._timer_finished:
        protocol._timer_finished = False
        protocol._timer_ring_start = None
        protocol.unduck()
        protocol.state.tts_player.stop()
        _LOGGER.debug("Stopping timer finished sound")
    else:
        protocol.state.tts_player.stop()
        _LOGGER.debug("TTS response stopped manually")
        protocol._tts_url = None
        protocol._tts_played = True
        protocol._tts_finished()


def play_tts(protocol: "VoiceSatelliteProtocol") -> None:
    if (not protocol._tts_url) or protocol._tts_played:
        return
    protocol._tts_played = True
    _LOGGER.debug("Playing TTS response: %s", protocol._tts_url)
    protocol.state.active_wake_words.add(protocol.state.stop_word.id)
    protocol._set_stop_word_active(True)
    protocol.state.tts_player.play(protocol._tts_url, done_callback=protocol._tts_finished)


def duck(protocol: "VoiceSatelliteProtocol") -> None:
    _LOGGER.debug("Ducking music")
    protocol.state.music_player.duck()
    protocol.state.music_player.pause_sendspin()


def unduck(protocol: "VoiceSatelliteProtocol") -> None:
    _LOGGER.debug("Unducking music")
    protocol.state.music_player.unduck()
    protocol.state.music_player.resume_sendspin()


def play_timer_finished(protocol: "VoiceSatelliteProtocol") -> None:
    if not protocol._timer_finished:
        protocol._timer_ring_start = None
        protocol.unduck()
        return

    if protocol._timer_ring_start is not None:
        elapsed = time.monotonic() - protocol._timer_ring_start
        if elapsed >= protocol.state.timer_max_ring_seconds:
            _LOGGER.info(
                "Timer auto-stopped after %.0f seconds (max=%.0f)",
                elapsed,
                protocol.state.timer_max_ring_seconds,
            )
            protocol._timer_finished = False
            protocol._timer_ring_start = None
            protocol.state.active_wake_words.discard(protocol.state.stop_word.id)
            protocol._set_stop_word_active(False)
            protocol.unduck()
            return

    protocol.state.tts_player.play(
        protocol.state.timer_finished_sound,
        done_callback=lambda: call_all(lambda: time.sleep(1.0), protocol._play_timer_finished),
    )
