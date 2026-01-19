"""Entities module for Home Assistant integration.

This module handles ESPHome entity definitions:
- EntityRegistry: Central registry for all HA entities
- Entity types: Sensors, switches, buttons, numbers, etc.
- EventEmotionMapper: HA event to robot emotion mapping
- Entity keys: Consistent key management
"""

# Re-export main classes for backward compatibility
from ..entity_registry import EntityRegistry
from ..entity import BinarySensorEntity, CameraEntity, NumberEntity, TextSensorEntity
from ..entity_extensions import SensorEntity, SwitchEntity, SelectEntity, ButtonEntity
from .event_emotion_mapper import (
    EventSource,
    EventEmotionMapping,
    EventTrigger,
    EventEmotionMapper,
    DEFAULT_EVENT_EMOTION_MAP,
    load_event_mappings,
)
# Entity keys - single source of truth
from .entity_keys import (
    ENTITY_KEYS,
    get_entity_key,
    register_entity_key,
    get_next_available_key,
)

__all__ = [
    "EntityRegistry",
    "get_entity_key",
    "ENTITY_KEYS",
    "BinarySensorEntity",
    "CameraEntity",
    "NumberEntity",
    "TextSensorEntity",
    "SensorEntity",
    "SwitchEntity",
    "SelectEntity",
    "ButtonEntity",
    # Event emotion mapping
    "EventSource",
    "EventEmotionMapping",
    "EventTrigger",
    "EventEmotionMapper",
    "DEFAULT_EVENT_EMOTION_MAP",
    "load_event_mappings",
    # Entity keys
    "register_entity_key",
    "get_next_available_key",
]
