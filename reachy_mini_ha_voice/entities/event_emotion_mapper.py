"""Home Assistant event listener and emotion mapping for Reachy Mini.

This module enables the robot to react emotionally to Home Assistant events,
creating a more engaging and context-aware experience.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class EventSource(Enum):
    """Source of HA events."""

    BINARY_SENSOR = "binary_sensor"
    SENSOR = "sensor"
    SWITCH = "switch"
    INPUT_BOOLEAN = "input_boolean"
    WEATHER = "weather"
    AUTOMATION = "automation"
    CUSTOM = "custom"


@dataclass
class EventEmotionMapping:
    """Mapping from HA event to robot emotion."""

    entity_id: str
    state_value: str  # The state that triggers the emotion
    emotion: str  # Emotion animation name
    cooldown: float = 60.0  # Minimum seconds between triggers
    priority: int = 50  # Higher = more important (0-100)
    description: Optional[str] = None


@dataclass
class EventTrigger:
    """Record of a triggered event."""

    entity_id: str
    old_state: str
    new_state: str
    timestamp: float
    emotion: Optional[str] = None


# Default emotion mappings based on common HA entities
DEFAULT_EVENT_EMOTION_MAP: Dict[str, List[EventEmotionMapping]] = {
    # Door/window sensors
    "binary_sensor.front_door": [
        EventEmotionMapping(
            entity_id="binary_sensor.front_door",
            state_value="on",
            emotion="curious1",
            cooldown=30.0,
            priority=70,
            description="Someone at the door",
        ),
    ],

    # Motion sensors
    "binary_sensor.living_room_motion": [
        EventEmotionMapping(
            entity_id="binary_sensor.living_room_motion",
            state_value="on",
            emotion="surprised1",
            cooldown=60.0,
            priority=50,
            description="Motion detected",
        ),
    ],

    # Time-based triggers (via input_boolean)
    "input_boolean.morning_routine": [
        EventEmotionMapping(
            entity_id="input_boolean.morning_routine",
            state_value="on",
            emotion="cheerful1",
            cooldown=3600.0,  # Once per hour
            priority=60,
            description="Good morning!",
        ),
    ],
    "input_boolean.bedtime_routine": [
        EventEmotionMapping(
            entity_id="input_boolean.bedtime_routine",
            state_value="on",
            emotion="sleep1",
            cooldown=3600.0,
            priority=60,
            description="Bedtime",
        ),
    ],
}


class EventEmotionMapper:
    """Maps Home Assistant events to robot emotions.

    This class handles:
    - Event to emotion mapping based on configuration
    - Cooldown management to prevent spam
    - Priority handling for conflicting emotions

    Usage:
        mapper = EventEmotionMapper()
        mapper.set_emotion_callback(play_emotion)

        # When HA state changes:
        mapper.handle_state_change("binary_sensor.front_door", "off", "on")
    """

    def __init__(
        self,
        mappings: Optional[Dict[str, List[EventEmotionMapping]]] = None,
        max_triggers_per_minute: int = 3,
    ):
        """Initialize the event emotion mapper.

        Args:
            mappings: Custom event mappings. Uses defaults if None.
            max_triggers_per_minute: Rate limit for emotion triggers
        """
        self._mappings: Dict[str, List[EventEmotionMapping]] = {}
        self._last_trigger_times: Dict[str, float] = {}
        self._emotion_callback: Optional[Callable[[str], None]] = None
        self._trigger_history: List[EventTrigger] = []
        self._max_history = 100
        self._triggers_this_minute = 0
        self._minute_start_time = time.monotonic()
        self._max_triggers_per_minute = max_triggers_per_minute
        self._lock = threading.Lock()

        # Load default or custom mappings
        if mappings:
            self._mappings = mappings
        else:
            self._mappings = DEFAULT_EVENT_EMOTION_MAP.copy()

        # Time function (can be overridden for testing)
        self._now = time.monotonic

    def set_emotion_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for emotion triggers.

        The callback receives the emotion name to play.
        """
        self._emotion_callback = callback

    def add_mapping(self, mapping: EventEmotionMapping) -> None:
        """Add or update an event mapping."""
        entity_id = mapping.entity_id
        with self._lock:
            if entity_id not in self._mappings:
                self._mappings[entity_id] = []
            # Remove existing mapping for same state
            self._mappings[entity_id] = [
                m for m in self._mappings[entity_id]
                if m.state_value != mapping.state_value
            ]
            self._mappings[entity_id].append(mapping)
        logger.debug("Added event mapping: %s -> %s", entity_id, mapping.emotion)

    def remove_mapping(self, entity_id: str, state_value: Optional[str] = None) -> None:
        """Remove event mapping(s)."""
        with self._lock:
            if entity_id in self._mappings:
                if state_value:
                    self._mappings[entity_id] = [
                        m for m in self._mappings[entity_id]
                        if m.state_value != state_value
                    ]
                else:
                    del self._mappings[entity_id]

    def handle_state_change(
        self,
        entity_id: str,
        old_state: str,
        new_state: str,
    ) -> Optional[str]:
        """Handle a Home Assistant state change.

        Args:
            entity_id: Entity ID that changed
            old_state: Previous state value
            new_state: New state value

        Returns:
            Emotion name if triggered, None otherwise
        """
        now = self._now()

        # Rate limiting
        if not self._check_rate_limit(now):
            logger.debug("Rate limit exceeded, skipping event")
            return None

        # Find matching mappings
        with self._lock:
            if entity_id not in self._mappings:
                return None

            mappings = self._mappings[entity_id]

        # Find mapping for new state
        matching = [m for m in mappings if m.state_value == new_state]
        if not matching:
            return None

        # Get highest priority mapping
        mapping = max(matching, key=lambda m: m.priority)

        # Check cooldown
        key = f"{entity_id}:{mapping.state_value}"
        last_trigger = self._last_trigger_times.get(key, 0)
        if now - last_trigger < mapping.cooldown:
            logger.debug("Event %s in cooldown (%.0fs remaining)",
                        entity_id, mapping.cooldown - (now - last_trigger))
            return None

        # Update cooldown and trigger
        self._last_trigger_times[key] = now
        self._triggers_this_minute += 1

        # Record trigger
        trigger = EventTrigger(
            entity_id=entity_id,
            old_state=old_state,
            new_state=new_state,
            timestamp=now,
            emotion=mapping.emotion,
        )
        self._record_trigger(trigger)

        # Execute callback
        if self._emotion_callback and mapping.emotion:
            logger.info("Event %s triggered emotion: %s", entity_id, mapping.emotion)
            try:
                self._emotion_callback(mapping.emotion)
            except Exception as e:
                logger.error("Error executing emotion callback: %s", e)

        return mapping.emotion

    def _check_rate_limit(self, now: float) -> bool:
        """Check if within rate limit."""
        # Reset counter every minute
        if now - self._minute_start_time >= 60.0:
            self._minute_start_time = now
            self._triggers_this_minute = 0

        return self._triggers_this_minute < self._max_triggers_per_minute

    def _record_trigger(self, trigger: EventTrigger) -> None:
        """Record a trigger in history."""
        self._trigger_history.append(trigger)
        if len(self._trigger_history) > self._max_history:
            self._trigger_history.pop(0)

    def get_trigger_history(self) -> List[EventTrigger]:
        """Get recent trigger history."""
        return self._trigger_history.copy()

    def get_mappings(self) -> Dict[str, List[EventEmotionMapping]]:
        """Get all current mappings."""
        with self._lock:
            return {k: v.copy() for k, v in self._mappings.items()}

    def load_from_json(self, json_path: Path) -> bool:
        """Load event mappings from a JSON file.

        Args:
            json_path: Path to JSON configuration file

        Returns:
            True if loaded successfully
        """
        if not json_path.exists():
            logger.warning("Event mappings file not found: %s", json_path)
            return False

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            settings = data.get("settings", {})
            self._max_triggers_per_minute = settings.get(
                "max_triggers_per_minute",
                self._max_triggers_per_minute
            )

            mappings_data = data.get("mappings", {})
            for entity_id, states in mappings_data.items():
                for state_config in states:
                    mapping = EventEmotionMapping(
                        entity_id=entity_id,
                        state_value=state_config.get("state", "on"),
                        emotion=state_config.get("emotion", ""),
                        cooldown=state_config.get("cooldown", 60.0),
                        priority=state_config.get("priority", 50),
                        description=state_config.get("description"),
                    )
                    self.add_mapping(mapping)

            logger.info("Loaded %d event mappings from %s",
                       sum(len(v) for v in self._mappings.values()), json_path)
            return True

        except Exception as e:
            logger.error("Failed to load event mappings: %s", e)
            return False


def load_event_mappings(json_path: Optional[Path] = None) -> Dict[str, List[EventEmotionMapping]]:
    """Load event mappings from JSON file or return defaults.

    Args:
        json_path: Path to JSON file. If None, uses default location.

    Returns:
        Dictionary of entity_id to list of EventEmotionMapping
    """
    if json_path is None:
        # Default path relative to this module
        module_dir = Path(__file__).parent.parent
        json_path = module_dir / "animations" / "event_mappings.json"

    if json_path.exists():
        mapper = EventEmotionMapper()
        if mapper.load_from_json(json_path):
            return mapper.get_mappings()

    return DEFAULT_EVENT_EMOTION_MAP.copy()
