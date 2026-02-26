"""Entities module for Home Assistant integration.

This module handles ESPHome entity definitions:
- ESPHomeEntity: Base class for all entities
- EntityRegistry: Entity registration and management
- EventEmotionMapper: HA event to robot emotion mapping
# - EmotionKeywordDetector: LLM response emotion detection (DISABLED - moved to HA blueprint)
- Entity keys: Consistent key management
- Entity factory: Entity creation utilities
"""

# DISABLED: Emotion detection moved to Home Assistant blueprint
# from .emotion_detector import EmotionKeywordDetector
from .entity import (
    BinarySensorEntity,
    CameraEntity,
    ESPHomeEntity,
    MediaPlayerEntity,
    NumberEntity,
    TextSensorEntity,
)
from .entity_extensions import (
    ButtonEntity,
    SelectEntity,
    SensorEntity,
    SwitchEntity,
)

# Entity keys - single source of truth
from .entity_keys import (
    ENTITY_KEYS,
    get_entity_key,
    get_next_available_key,
    register_entity_key,
)
from .entity_registry import EntityRegistry
from .event_emotion_mapper import (
    DEFAULT_EVENT_EMOTION_MAP,
    EventEmotionMapper,
    EventEmotionMapping,
    EventSource,
    EventTrigger,
    load_event_mappings,
)

__all__ = [
    "DEFAULT_EVENT_EMOTION_MAP",
    # Entity keys
    "ENTITY_KEYS",
    "BinarySensorEntity",
    "ButtonEntity",
    "CameraEntity",
    # Entity base classes
    "ESPHomeEntity",
    # Emotion detection (DISABLED - moved to HA blueprint)
    # "EmotionKeywordDetector",
    # Entity registry
    "EntityRegistry",
    "EventEmotionMapper",
    "EventEmotionMapping",
    # Event emotion mapping
    "EventSource",
    "EventTrigger",
    "MediaPlayerEntity",
    "NumberEntity",
    "SelectEntity",
    "SensorEntity",
    "SwitchEntity",
    "TextSensorEntity",
    "get_entity_key",
    "get_next_available_key",
    "load_event_mappings",
    "register_entity_key",
]
