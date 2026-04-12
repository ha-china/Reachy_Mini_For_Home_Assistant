"""Message dispatch helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ButtonCommandRequest,
    CameraImageRequest,
    DeviceInfoRequest,
    DeviceInfoResponse,
    HomeAssistantStateResponse,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    NumberCommandRequest,
    SelectCommandRequest,
    SubscribeHomeAssistantStatesRequest,
    SubscribeStatesRequest,
    SwitchCommandRequest,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantFeature, VoiceAssistantTimerEventType
from google.protobuf import message

from .. import __version__
from .entity_bridge import handle_ha_state_change, load_optional_mappings, schedule_ha_connected_callback
from .voice_pipeline import handle_timer_event, handle_voice_event

if TYPE_CHECKING:
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


def handle_message(protocol: "VoiceSatelliteProtocol", msg: message.Message) -> Iterable[message.Message]:
    if isinstance(msg, VoiceAssistantEventResponse):
        data: dict[str, str] = {}
        for arg in msg.data:
            data[arg.name] = arg.value
        handle_voice_event(protocol, VoiceAssistantEventType(msg.event_type), data)
        return []

    if isinstance(msg, VoiceAssistantAnnounceRequest):
        _LOGGER.debug("Announcing: %s", msg.text)
        assert protocol.state.media_player_entity is not None
        urls = []
        if msg.preannounce_media_id:
            urls.append(msg.preannounce_media_id)
        urls.append(msg.media_id)
        protocol.state.active_wake_words.add(protocol.state.stop_word.id)
        protocol._set_stop_word_active(True)
        protocol._continue_conversation = msg.start_conversation
        protocol.duck()
        return list(protocol.state.media_player_entity.play(urls, announcement=True, done_callback=protocol._tts_finished))

    if isinstance(msg, VoiceAssistantTimerEventResponse):
        handle_timer_event(protocol, VoiceAssistantTimerEventType(msg.event_type), msg)
        return []

    if isinstance(msg, HomeAssistantStateResponse):
        handle_ha_state_change(protocol, msg)
        return []

    if isinstance(msg, DeviceInfoRequest):
        return [
            DeviceInfoResponse(
                uses_password=False,
                name=protocol.state.name,
                friendly_name=protocol.state.name,
                project_name="ha-china.Reachy Mini For Home Assistant",
                project_version=__version__,
                esphome_version=protocol._aioesphomeapi_version,
                mac_address=protocol.state.mac_address,
                manufacturer="ha-china",
                model="Reachy Mini Home Assistant Voice",
                voice_assistant_feature_flags=(
                    VoiceAssistantFeature.VOICE_ASSISTANT
                    | VoiceAssistantFeature.API_AUDIO
                    | VoiceAssistantFeature.ANNOUNCE
                    | VoiceAssistantFeature.START_CONVERSATION
                    | VoiceAssistantFeature.TIMERS
                ),
            )
        ]

    if isinstance(
        msg,
        (
            ListEntitiesRequest,
            SubscribeHomeAssistantStatesRequest,
            SubscribeStatesRequest,
            MediaPlayerCommandRequest,
            NumberCommandRequest,
            SwitchCommandRequest,
            SelectCommandRequest,
            ButtonCommandRequest,
            CameraImageRequest,
        ),
    ):
        responses = []
        for entity in protocol.state.entities:
            responses.extend(entity.handle_message(msg))
        if isinstance(msg, ListEntitiesRequest):
            responses.append(ListEntitiesDoneResponse())
        return responses

    if isinstance(msg, VoiceAssistantConfigurationRequest):
        available_wake_words = [
            VoiceAssistantWakeWord(
                id=ww.id,
                wake_word=ww.wake_word,
                trained_languages=ww.trained_languages,
            )
            for ww in protocol.state.available_wake_words.values()
        ]
        for eww in msg.external_wake_words:
            if eww.model_type != "micro":
                continue
            available_wake_words.append(
                VoiceAssistantWakeWord(
                    id=eww.id,
                    wake_word=eww.wake_word,
                    trained_languages=eww.trained_languages,
                )
            )
            protocol._external_wake_words[eww.id] = eww
        load_optional_mappings(protocol)
        _LOGGER.info("Connected to Home Assistant")
        schedule_ha_connected_callback(protocol)
        return [
            VoiceAssistantConfigurationResponse(
                available_wake_words=available_wake_words,
                active_wake_words=[ww.id for ww in protocol.state.wake_words.values() if ww.id in protocol.state.active_wake_words],
                max_active_wake_words=2,
            )
        ]

    if isinstance(msg, VoiceAssistantSetConfiguration):
        active_wake_words: set[str] = set()
        for wake_word_id in msg.active_wake_words:
            if wake_word_id in protocol.state.wake_words:
                active_wake_words.add(wake_word_id)
                continue
            model_info = protocol.state.available_wake_words.get(wake_word_id)
            if not model_info:
                external_wake_word = protocol._external_wake_words.get(wake_word_id)
                if not external_wake_word:
                    _LOGGER.warning("Wake word not found: %s", wake_word_id)
                    continue
                model_info = protocol._download_external_wake_word(external_wake_word)
                if not model_info:
                    continue
                protocol.state.available_wake_words[wake_word_id] = model_info
            _LOGGER.debug("Loading wake word: %s", model_info.wake_word_path)
            loaded_model = model_info.load()
            loaded_model.id = wake_word_id
            protocol.state.wake_words[wake_word_id] = loaded_model
            _LOGGER.info("Wake word loaded: %s", wake_word_id)
            active_wake_words.add(wake_word_id)
        protocol.state.active_wake_words = active_wake_words
        _LOGGER.debug("Active wake words: %s", active_wake_words)
        protocol.state.preferences.active_wake_words = list(active_wake_words)
        protocol.state.save_preferences()
        protocol.state.wake_words_changed = True
        return []

    return []
