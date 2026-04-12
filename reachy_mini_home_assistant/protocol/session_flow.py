"""Session flow helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import TYPE_CHECKING

from aioesphomeapi.api_pb2 import VoiceAssistantAnnounceFinished, VoiceAssistantRequest  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from .satellite import VoiceSatelliteProtocol

logger = logging.getLogger(__name__)


def get_or_create_conversation_id(protocol: "VoiceSatelliteProtocol") -> str:
    now = time.time()
    if protocol._conversation_id is None or now - protocol._last_conversation_time > protocol._conversation_timeout:
        protocol._conversation_id = str(uuid.uuid4())
        logger.debug("Created new conversation_id: %s", protocol._conversation_id)

    protocol._last_conversation_time = now
    return protocol._conversation_id


def clear_conversation(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._conversation_id = None
    protocol._continue_conversation = False


def queue_voice_request_after_wakeup(
    protocol: "VoiceSatelliteProtocol", *, wake_word_phrase: str | None = None, conversation_id: str | None = None
) -> None:
    protocol._pending_voice_request = (wake_word_phrase, conversation_id)


def on_wakeup_sound_finished(protocol: "VoiceSatelliteProtocol") -> None:
    if protocol._pending_voice_request is None:
        logger.debug("Wakeup sound finished with no pending voice request")
        return

    wake_word_phrase, conversation_id = protocol._pending_voice_request
    protocol._pending_voice_request = None

    request = VoiceAssistantRequest(start=True)
    if wake_word_phrase:
        request.wake_word_phrase = wake_word_phrase
    if conversation_id:
        request.conversation_id = conversation_id

    protocol.send_messages([request])
    protocol._is_streaming_audio = True


def play_wakeup_sound(protocol: "VoiceSatelliteProtocol") -> None:
    protocol.state.tts_player.play(
        protocol.state.wakeup_sound, done_callback=lambda: on_wakeup_sound_finished(protocol)
    )


def tts_finished(protocol: "VoiceSatelliteProtocol") -> None:
    protocol._pipeline_active = False
    protocol.state.active_wake_words.discard(protocol.state.stop_word.id)
    protocol._set_stop_word_active(False)
    protocol._run_motion_state("speaking_end", "on_speaking_end")
    protocol.send_messages([VoiceAssistantAnnounceFinished()])

    continuous_mode = protocol.state.preferences.continuous_conversation
    should_continue = continuous_mode or protocol._continue_conversation

    if should_continue:
        logger.debug(
            "Continuing conversation (our_switch=%s, ha_request=%s)", continuous_mode, protocol._continue_conversation
        )
        conv_id = get_or_create_conversation_id(protocol)
        queue_voice_request_after_wakeup(protocol, conversation_id=conv_id)
        protocol._pipeline_active = True
        protocol._reachy_on_listening()
        play_wakeup_sound(protocol)
    else:
        clear_conversation(protocol)
        protocol.unduck()
        protocol._is_streaming_audio = False
        logger.debug("Conversation finished")
        protocol._schedule_delayed_idle_return()


def cancel_delayed_idle_return(protocol: "VoiceSatelliteProtocol") -> None:
    if protocol._idle_return_timer is not None:
        protocol._idle_return_timer.cancel()
        protocol._idle_return_timer = None


def schedule_delayed_idle_return(protocol: "VoiceSatelliteProtocol", delay_s: float) -> None:
    cancel_delayed_idle_return(protocol)

    def _go_idle() -> None:
        protocol._idle_return_timer = None
        protocol._reachy_on_idle()

    protocol._idle_return_timer = threading.Timer(delay_s, _go_idle)
    protocol._idle_return_timer.daemon = True
    protocol._idle_return_timer.start()
    logger.debug("Scheduled idle transition in %.1fs", delay_s)
