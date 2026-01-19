"""Entities module for Home Assistant integration.

This module handles ESPHome entity definitions:
- EventEmotionMapper: HA event to robot emotion mapping
- EmotionKeywordDetector: LLM response emotion detection
- Entity keys: Consistent key management
- Entity factory: Entity creation utilities

Note: EntityRegistry is in the parent package to avoid circular imports.
Import it directly: from reachy_mini_ha_voice.entity_registry import EntityRegistry
"""

from .event_emotion_mapper import (
    EventSource,
    EventEmotionMapping,
    EventTrigger,
    EventEmotionMapper,
    DEFAULT_EVENT_EMOTION_MAP,
    load_event_mappings,
)
from .emotion_detector import EmotionKeywordDetector

# Entity keys - single source of truth
from .entity_keys import (
    ENTITY_KEYS,
    get_entity_key,
    register_entity_key,
    get_next_available_key,
)

__all__ = [
    # Event emotion mapping
    "EventSource",
    "EventEmotionMapping",
    "EventTrigger",
    "EventEmotionMapper",
    "DEFAULT_EVENT_EMOTION_MAP",
    "load_event_mappings",
    # Emotion detection
    "EmotionKeywordDetector",
    # Entity keys
    "ENTITY_KEYS",
    "get_entity_key",
    "register_entity_key",
    "get_next_available_key",
]
