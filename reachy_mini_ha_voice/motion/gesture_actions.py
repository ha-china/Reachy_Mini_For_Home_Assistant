"""Gesture to action mapping for Reachy Mini.

This module maps detected gestures to robot actions and emotions,
providing immediate visual feedback for user gestures.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class GestureAction(Enum):
    """Available actions that can be triggered by gestures."""
    EMOTION = "emotion"           # Play an emotion animation
    SOUND = "sound"               # Play a sound
    START_LISTENING = "start_listening"  # Trigger voice assistant
    STOP_SPEAKING = "stop_speaking"      # Interrupt TTS
    PAUSE_MOTION = "pause_motion"        # Pause all motion
    HA_EVENT = "ha_event"         # Send event to Home Assistant
    NONE = "none"                 # No action


@dataclass
class GestureMapping:
    """Configuration for a gesture-to-action mapping."""
    gesture_name: str
    action: GestureAction
    emotion: Optional[str] = None      # For EMOTION action
    sound: Optional[str] = None        # For SOUND action
    ha_event_name: Optional[str] = None  # For HA_EVENT action
    cooldown: float = 2.0              # Seconds before same gesture triggers again


# Default gesture mappings based on HaGRID gesture set
DEFAULT_GESTURE_MAPPINGS: Dict[str, GestureMapping] = {
    # Positive gestures
    "like": GestureMapping(
        gesture_name="like",
        action=GestureAction.EMOTION,
        emotion="cheerful1",
        ha_event_name="gesture_like",
    ),
    "ok": GestureMapping(
        gesture_name="ok",
        action=GestureAction.EMOTION,
        emotion="yes1",
        ha_event_name="gesture_ok",
    ),
    "peace": GestureMapping(
        gesture_name="peace",
        action=GestureAction.EMOTION,
        emotion="enthusiastic1",
        ha_event_name="gesture_peace",
    ),

    # Negative gestures
    "dislike": GestureMapping(
        gesture_name="dislike",
        action=GestureAction.EMOTION,
        emotion="sad1",
        ha_event_name="gesture_dislike",
    ),
    "stop": GestureMapping(
        gesture_name="stop",
        action=GestureAction.STOP_SPEAKING,
        emotion="surprised1",
        ha_event_name="gesture_stop",
    ),

    # Interactive gestures
    "call": GestureMapping(
        gesture_name="call",
        action=GestureAction.START_LISTENING,
        ha_event_name="gesture_call",
    ),
    "palm": GestureMapping(
        gesture_name="palm",
        action=GestureAction.PAUSE_MOTION,
        ha_event_name="gesture_palm",
    ),

    # Alerting gestures
    "fist": GestureMapping(
        gesture_name="fist",
        action=GestureAction.EMOTION,
        emotion="rage1",
        ha_event_name="gesture_fist",
    ),

    # Pointing gestures - just send HA events
    "one": GestureMapping(
        gesture_name="one",
        action=GestureAction.HA_EVENT,
        ha_event_name="gesture_one",
    ),
    "two_up": GestureMapping(
        gesture_name="two_up",
        action=GestureAction.HA_EVENT,
        ha_event_name="gesture_two",
    ),
    "three": GestureMapping(
        gesture_name="three",
        action=GestureAction.HA_EVENT,
        ha_event_name="gesture_three",
    ),
    "four": GestureMapping(
        gesture_name="four",
        action=GestureAction.HA_EVENT,
        ha_event_name="gesture_four",
    ),
}


class GestureActionMapper:
    """Maps detected gestures to robot actions.

    This class handles:
    - Mapping gestures to actions based on configuration
    - Cooldown management to prevent rapid re-triggering
    - Callback invocation for different action types

    Usage:
        mapper = GestureActionMapper()
        mapper.set_emotion_callback(play_emotion)
        mapper.set_ha_event_callback(send_ha_event)

        # When gesture detected:
        mapper.handle_gesture("like", confidence=0.85)
    """

    def __init__(
        self,
        mappings: Optional[Dict[str, GestureMapping]] = None,
        min_confidence: float = 0.7,
    ):
        """Initialize the gesture action mapper.

        Args:
            mappings: Custom gesture mappings. Uses defaults if None.
            min_confidence: Minimum confidence to trigger action.
        """
        self._mappings = mappings or DEFAULT_GESTURE_MAPPINGS.copy()
        self._min_confidence = min_confidence

        # Cooldown tracking
        self._last_trigger_times: Dict[str, float] = {}

        # Callbacks
        self._emotion_callback: Optional[Callable[[str], None]] = None
        self._sound_callback: Optional[Callable[[str], None]] = None
        self._start_listening_callback: Optional[Callable[[], None]] = None
        self._stop_speaking_callback: Optional[Callable[[], None]] = None
        self._pause_motion_callback: Optional[Callable[[], None]] = None
        self._ha_event_callback: Optional[Callable[[str], None]] = None

        # Time function (can be overridden for testing)
        import time
        self._now = time.monotonic

    def set_emotion_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for emotion actions."""
        self._emotion_callback = callback

    def set_sound_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for sound actions."""
        self._sound_callback = callback

    def set_start_listening_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for start listening action."""
        self._start_listening_callback = callback

    def set_stop_speaking_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for stop speaking action."""
        self._stop_speaking_callback = callback

    def set_pause_motion_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for pause motion action."""
        self._pause_motion_callback = callback

    def set_ha_event_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for Home Assistant events."""
        self._ha_event_callback = callback

    def handle_gesture(
        self,
        gesture_name: str,
        confidence: float,
    ) -> bool:
        """Handle a detected gesture.

        Args:
            gesture_name: Name of the detected gesture
            confidence: Detection confidence (0-1)

        Returns:
            True if an action was triggered, False otherwise
        """
        # Check confidence threshold
        if confidence < self._min_confidence:
            return False

        # Check if gesture has mapping
        gesture_lower = gesture_name.lower()
        if gesture_lower not in self._mappings:
            logger.debug(f"No mapping for gesture: {gesture_name}")
            return False

        mapping = self._mappings[gesture_lower]

        # Check cooldown
        now = self._now()
        last_trigger = self._last_trigger_times.get(gesture_lower, 0)
        if now - last_trigger < mapping.cooldown:
            logger.debug(f"Gesture {gesture_name} in cooldown")
            return False

        # Update cooldown
        self._last_trigger_times[gesture_lower] = now

        # Execute action
        return self._execute_action(mapping)

    def _execute_action(self, mapping: GestureMapping) -> bool:
        """Execute the action for a gesture mapping."""
        action = mapping.action

        if action == GestureAction.EMOTION:
            if mapping.emotion and self._emotion_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> emotion {mapping.emotion}")
                self._emotion_callback(mapping.emotion)
                return True

        elif action == GestureAction.SOUND:
            if mapping.sound and self._sound_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> sound {mapping.sound}")
                self._sound_callback(mapping.sound)
                return True

        elif action == GestureAction.START_LISTENING:
            if self._start_listening_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> start listening")
                self._start_listening_callback()
                return True

        elif action == GestureAction.STOP_SPEAKING:
            if self._stop_speaking_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> stop speaking")
                self._stop_speaking_callback()
                # Also play emotion if configured
                if mapping.emotion and self._emotion_callback:
                    self._emotion_callback(mapping.emotion)
                return True

        elif action == GestureAction.PAUSE_MOTION:
            if self._pause_motion_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> pause motion")
                self._pause_motion_callback()
                return True

        elif action == GestureAction.HA_EVENT:
            if mapping.ha_event_name and self._ha_event_callback:
                logger.info(f"Gesture {mapping.gesture_name} -> HA event {mapping.ha_event_name}")
                self._ha_event_callback(mapping.ha_event_name)
                return True

        return False

    def add_mapping(self, mapping: GestureMapping) -> None:
        """Add or update a gesture mapping."""
        self._mappings[mapping.gesture_name.lower()] = mapping

    def remove_mapping(self, gesture_name: str) -> None:
        """Remove a gesture mapping."""
        self._mappings.pop(gesture_name.lower(), None)

    def get_mappings(self) -> Dict[str, GestureMapping]:
        """Get all current mappings."""
        return self._mappings.copy()

    def load_from_json(self, json_path: Path) -> bool:
        """Load gesture mappings from a JSON file.

        Args:
            json_path: Path to the JSON configuration file

        Returns:
            True if loaded successfully, False otherwise
        """
        if not json_path.exists():
            logger.warning(f"Gesture mappings file not found: {json_path}")
            return False

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load settings
            settings = data.get("settings", {})
            self._min_confidence = settings.get("min_confidence", 0.7)
            default_cooldown = settings.get("default_cooldown", 2.0)

            # Load mappings
            mappings_data = data.get("mappings", {})
            for gesture_name, config in mappings_data.items():
                action_str = config.get("action", "none")
                try:
                    action = GestureAction(action_str)
                except ValueError:
                    logger.warning(f"Unknown action '{action_str}' for gesture '{gesture_name}'")
                    action = GestureAction.NONE

                mapping = GestureMapping(
                    gesture_name=gesture_name,
                    action=action,
                    emotion=config.get("emotion"),
                    sound=config.get("sound"),
                    ha_event_name=config.get("ha_event"),
                    cooldown=config.get("cooldown", default_cooldown),
                )
                self._mappings[gesture_name.lower()] = mapping

            logger.info(f"Loaded {len(mappings_data)} gesture mappings from {json_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in gesture mappings file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading gesture mappings: {e}")
            return False


def load_gesture_mappings(json_path: Optional[Path] = None) -> Dict[str, GestureMapping]:
    """Load gesture mappings from JSON file or return defaults.

    Args:
        json_path: Path to JSON file. If None, uses default location.

    Returns:
        Dictionary of gesture name to GestureMapping
    """
    if json_path is None:
        # Default path relative to this module
        module_dir = Path(__file__).parent.parent
        json_path = module_dir / "animations" / "gesture_mappings.json"

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            mappings = {}
            default_cooldown = data.get("settings", {}).get("default_cooldown", 2.0)

            for gesture_name, config in data.get("mappings", {}).items():
                action_str = config.get("action", "none")
                try:
                    action = GestureAction(action_str)
                except ValueError:
                    action = GestureAction.NONE

                mappings[gesture_name.lower()] = GestureMapping(
                    gesture_name=gesture_name,
                    action=action,
                    emotion=config.get("emotion"),
                    sound=config.get("sound"),
                    ha_event_name=config.get("ha_event"),
                    cooldown=config.get("cooldown", default_cooldown),
                )

            logger.info(f"Loaded {len(mappings)} gesture mappings from {json_path}")
            return mappings

        except Exception as e:
            logger.warning(f"Failed to load gesture mappings from {json_path}: {e}")

    # Return defaults
    return DEFAULT_GESTURE_MAPPINGS.copy()
