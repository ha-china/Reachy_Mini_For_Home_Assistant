"""Entity and Home Assistant bridge helpers for `VoiceSatelliteProtocol`."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .. import __version__
from ..entities.entity import MediaPlayerEntity
from ..entities.entity_registry import EntityRegistry, get_entity_key
from ..entities.event_emotion_mapper import EventEmotionMapper

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import HomeAssistantStateResponse  # type: ignore[attr-defined]
    from .satellite import VoiceSatelliteProtocol

_LOGGER = logging.getLogger(__name__)


def create_entity_registry(protocol: "VoiceSatelliteProtocol") -> EntityRegistry:
    return EntityRegistry(
        server=protocol,
        reachy_controller=protocol.reachy_controller,
        camera_server=protocol.camera_server,
        play_emotion_callback=protocol._play_emotion,
    )


def bind_camera_callbacks(protocol: "VoiceSatelliteProtocol", camera_server) -> None:
    if not camera_server:
        return
    camera_server.set_gesture_state_callback(protocol._entity_registry.update_gesture_state)
    camera_server.set_face_state_callback(protocol._entity_registry.update_face_detected_state)


def initialize_entities(protocol: "VoiceSatelliteProtocol") -> None:
    try:
        _LOGGER.info("Checking entity initialization state...")
        if not protocol.state._entities_initialized:
            _LOGGER.info("Setting up entities for first time...")
            if protocol.state.media_player_entity is None:
                _LOGGER.info("Creating MediaPlayerEntity...")
                protocol.state.media_player_entity = MediaPlayerEntity(
                    server=protocol,
                    key=get_entity_key("reachy_mini_media_player"),
                    name="Media Player",
                    object_id="reachy_mini_media_player",
                    music_player=protocol.state.music_player,
                    announce_player=protocol.state.tts_player,
                )
                protocol.state.entities.append(protocol.state.media_player_entity)
                _LOGGER.info("MediaPlayerEntity created")

            _LOGGER.info("Setting up all entities via registry...")
            protocol._entity_registry.setup_all_entities(protocol.state.entities)
            protocol.state._entities_initialized = True
            _LOGGER.info("Entities initialized: %d total", len(protocol.state.entities))
        else:
            _LOGGER.info("Entities already initialized, updating server references")
            for entity in protocol.state.entities:
                entity.server = protocol
            _LOGGER.info("Server references updated for %d entities", len(protocol.state.entities))
    except Exception as e:
        _LOGGER.error("Error during entity setup: %s", e, exc_info=True)
        raise


def update_camera_server(protocol: "VoiceSatelliteProtocol", camera_server) -> None:
    protocol._entity_registry.camera_server = camera_server
    bind_camera_callbacks(protocol, camera_server)
    _LOGGER.debug("Camera server reference updated in entity registry")


def load_optional_mappings(protocol: "VoiceSatelliteProtocol") -> None:
    if protocol._optional_mappings_loaded:
        return

    unified_behaviors_file = Path(__file__).resolve().parent.parent / "animations" / "conversation_animations.json"
    if unified_behaviors_file.exists():
        try:
            protocol._event_emotion_mapper.load_from_json(unified_behaviors_file)
        except Exception as e:
            _LOGGER.error("Failed to load HA event behaviors from %s: %s", unified_behaviors_file, e)

    protocol._optional_mappings_loaded = True


def on_authenticated(protocol: "VoiceSatelliteProtocol") -> None:
    for entity in protocol.state.entities:
        try:
            entity.update_state()
        except Exception as e:
            _LOGGER.debug("Failed to replay state for %s: %s", getattr(entity, "object_id", entity), e)


def handle_ha_state_change(protocol: "VoiceSatelliteProtocol", msg: "HomeAssistantStateResponse") -> None:
    try:
        entity_id = msg.entity_id
        new_state = msg.state
        old_state = protocol._ha_entity_states.get(entity_id, "unknown")
        protocol._ha_entity_states[entity_id] = new_state
        _LOGGER.debug("HA state change: %s: %s -> %s", entity_id, old_state, new_state)
        emotion = protocol._behavior_controller.handle_ha_state_change(entity_id, old_state, new_state)
        if emotion:
            _LOGGER.info("HA event triggered emotion: %s from %s", emotion, entity_id)
    except Exception as e:
        _LOGGER.error("Error handling HA state change: %s", e)


def schedule_ha_connected_callback(protocol: "VoiceSatelliteProtocol") -> None:
    if protocol._on_ha_connected_callback:
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(protocol._on_ha_connected_callback())
            _ = task
        except Exception as e:
            _LOGGER.error("Error in HA connected callback: %s", e)


def run_ha_disconnected_callback(protocol: "VoiceSatelliteProtocol") -> None:
    if protocol._on_ha_disconnected_callback:
        try:
            protocol._on_ha_disconnected_callback()
        except Exception as e:
            _LOGGER.error("Error in HA disconnected callback: %s", e)
