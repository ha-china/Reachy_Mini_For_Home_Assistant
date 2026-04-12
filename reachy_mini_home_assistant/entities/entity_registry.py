"""Entity registry for ESPHome entities.

This module handles the registration and management of all ESPHome entities
for the Reachy Mini voice assistant.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

from ..models import Preferences
from .entity import BinarySensorEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SwitchEntity
from .entity_keys import get_entity_key
from .runtime_entity_setup import (
    setup_behavior_entities,
    setup_camera_entities,
    setup_runtime_entities,
    setup_service_entities,
)
from .sensor_entity_setup import (
    append_defined_entities,
    setup_audio_direction_entities,
    setup_detection_entities,
    setup_diagnostic_entities,
    setup_imu_entities,
    setup_motion_entities,
    setup_robot_info_entities,
)

if TYPE_CHECKING:
    from ..reachy_controller import ReachyController
    from ..vision.camera_server import MJPEGCameraServer

_LOGGER = logging.getLogger(__name__)


class EntityRegistry:
    """Registry for managing ESPHome entities."""

    def __init__(
        self,
        server,
        reachy_controller: "ReachyController",
        camera_server: Optional["MJPEGCameraServer"] = None,
        play_emotion_callback: Callable[[str], None] | None = None,
    ):
        """Initialize the entity registry.

        Args:
            server: The VoiceSatelliteProtocol server instance
            reachy_controller: The ReachyController instance
            camera_server: Optional camera server for camera entity
            play_emotion_callback: Optional callback for playing emotions
        """
        self.server = server
        self.reachy_controller = reachy_controller
        self.camera_server = camera_server
        self._play_emotion_callback = play_emotion_callback

        # Runtime state entities
        self._services_suspended_entity: BinarySensorEntity | None = None
        self._face_detected_entity: BinarySensorEntity | None = None
        self._gesture_entity: TextSensorEntity | None = None
        self._gesture_confidence_entity: SensorEntity | None = None

        # Gesture detection state
        self._current_gesture = "none"
        self._gesture_confidence = 0.0

        # Emotion state
        self._current_emotion = "None"
        # Map emotion names to available robot emotions
        # Full list of available emotions from robot
        self._emotion_map = {
            "None": None,
            # Basic emotions
            "Happy": "cheerful1",
            "Sad": "sad1",
            "Angry": "rage1",
            "Fear": "fear1",
            "Surprise": "surprised1",
            "Disgust": "disgusted1",
            # Extended emotions
            "Laughing": "laughing1",
            "Loving": "loving1",
            "Proud": "proud1",
            "Grateful": "grateful1",
            "Enthusiastic": "enthusiastic1",
            "Curious": "curious1",
            "Amazed": "amazed1",
            "Shy": "shy1",
            "Confused": "confused1",
            "Thoughtful": "thoughtful1",
            "Anxious": "anxiety1",
            "Scared": "scared1",
            "Frustrated": "frustrated1",
            "Irritated": "irritated1",
            "Furious": "furious1",
            "Contempt": "contempt1",
            "Bored": "boredom1",
            "Tired": "tired1",
            "Exhausted": "exhausted1",
            "Lonely": "lonely1",
            "Downcast": "downcast1",
            "Resigned": "resigned1",
            "Uncertain": "uncertain1",
            "Uncomfortable": "uncomfortable1",
            "Lost": "lost1",
            "Indifferent": "indifferent1",
            # Positive actions
            "Yes": "yes1",
            "No": "no1",
            "Welcoming": "welcoming1",
            "Helpful": "helpful1",
            "Attentive": "attentive1",
            "Understanding": "understanding1",
            "Calming": "calming1",
            "Relief": "relief1",
            "Success": "success1",
            "Serenity": "serenity1",
            # Negative actions
            "Oops": "oops1",
            "Displeased": "displeased1",
            "Impatient": "impatient1",
            "Reprimand": "reprimand1",
            "GoAway": "go_away1",
            # Special
            "Come": "come1",
            "Inquiring": "inquiring1",
            "Sleep": "sleep1",
            "Dance": "dance1",
            "Electric": "electric1",
            "Dying": "dying1",
        }

    def _get_preferences(self) -> Preferences | None:
        return self.server.state.preferences

    def _get_server_state(self):
        return self.server.state

    def _save_preferences(self) -> None:
        self.server.state.save_preferences()

    def _set_preference_and_save(self, key: str, value) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, value)
            self._save_preferences()

    def _idle_behavior_allows_vision(self) -> bool:
        prefs = self._get_preferences()
        return bool(prefs.idle_behavior_enabled) if prefs is not None else False

    def _apply_vision_runtime_state(self) -> None:
        if self.camera_server is None:
            return

        prefs = self._get_preferences()
        if prefs is None:
            self.camera_server.set_face_tracking_enabled(False)
            self.camera_server.set_gesture_detection_enabled(False)
            return

        self.camera_server.set_face_tracking_enabled(bool(prefs.face_tracking_enabled))
        self.camera_server.set_gesture_detection_enabled(bool(prefs.gesture_detection_enabled))

    def _get_pref_bool(self, key: str, default: bool = False) -> bool:
        prefs = self._get_preferences()
        return bool(getattr(prefs, key, default)) if prefs is not None else default

    def _set_pref_bool(self, key: str, enabled: bool) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, bool(enabled))
            self._save_preferences()

    def _get_pref_float(self, key: str, default: float) -> float:
        prefs = self._get_preferences()
        return float(getattr(prefs, key, default)) if prefs is not None else default

    def _set_pref_float(self, key: str, value: float) -> None:
        prefs = self._get_preferences()
        if prefs is not None:
            setattr(prefs, key, float(value))
            self._save_preferences()

    def _set_idle_behavior_enabled(self, enabled: bool) -> None:
        self.reachy_controller.set_idle_behavior_enabled(enabled)

        prefs = self._get_preferences()
        if prefs is not None:
            prefs.set_idle_behavior_enabled(enabled)
            self._save_preferences()

        self._apply_vision_runtime_state()

    def _make_preference_switch(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        getter: Callable[[], bool],
        setter: Callable[[bool], None],
    ) -> SwitchEntity:
        """Create a switch entity with the common registry wiring."""
        return SwitchEntity(
            server=self.server,
            key=get_entity_key(key_name),
            name=name,
            object_id=object_id,
            icon=icon,
            entity_category=1,
            value_getter=getter,
            value_setter=setter,
        )

    def _make_stored_switch(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        pref_key: str,
        getter_transform: Callable[[bool], bool] | None = None,
        setter_transform: Callable[[bool], bool] | None = None,
        after_set: Callable[[], None] | None = None,
    ) -> SwitchEntity:
        """Create a switch backed by preferences with optional transforms/hooks."""

        def getter() -> bool:
            value = self._get_pref_bool(pref_key)
            return getter_transform(value) if getter_transform is not None else value

        def setter(enabled: bool) -> None:
            stored = setter_transform(enabled) if setter_transform is not None else enabled
            self._set_pref_bool(pref_key, stored)
            if after_set is not None:
                after_set()

        return self._make_preference_switch(
            key_name=key_name,
            name=name,
            object_id=object_id,
            icon=icon,
            getter=getter,
            setter=setter,
        )

    def _make_preference_number(
        self,
        *,
        key_name: str,
        name: str,
        object_id: str,
        icon: str,
        getter: Callable[[], float],
        setter: Callable[[float], None],
        min_value: float,
        max_value: float,
        step: float,
        mode: int = 2,
    ) -> NumberEntity:
        """Create a number entity with the common registry wiring."""
        return NumberEntity(
            server=self.server,
            key=get_entity_key(key_name),
            name=name,
            object_id=object_id,
            min_value=min_value,
            max_value=max_value,
            step=step,
            icon=icon,
            mode=mode,
            entity_category=1,
            value_getter=getter,
            value_setter=setter,
        )

    def _append_defined_entities(
        self,
        entities: list,
        definitions: list,
        callback_map: dict[str, tuple[Callable, Callable] | Callable],
    ) -> None:
        """Bind callbacks to declarative definitions and append created entities."""
        append_defined_entities(self, entities, definitions, callback_map)

    def setup_all_entities(self, entities: list) -> None:
        """Setup all entity phases."""
        self._setup_phase1_entities(entities)
        self._setup_phase2_entities(entities)
        self._setup_phase3_entities(entities)
        self._setup_phase4_entities(entities)
        self._setup_phase5_entities(entities)  # DOA for wakeup turn-to-sound
        self._setup_phase6_entities(entities)
        self._setup_phase7_entities(entities)
        self._setup_phase8_entities(entities)
        self._setup_phase9_entities(entities)
        self._setup_phase10_entities(entities)
        # Phase 11 (LED control) disabled - LEDs are inside the robot and not visible
        self._setup_phase12_entities(entities)
        # Phase 13 (Sendspin) - auto-enabled via mDNS discovery, no user entities
        # Phase 14 (head_joints, passive_joints) removed - not needed
        # Phase 20 (Tap detection) disabled - too many false triggers
        self._setup_phase21_entities(entities)
        self._setup_phase22_entities(entities)
        self._setup_phase23_entities(entities)
        self._setup_phase24_entities(entities)  # System diagnostics

        _LOGGER.info("All entities registered: %d total", len(entities))

    def _setup_phase1_entities(self, entities: list) -> None:
        setup_runtime_entities(self, entities)

    def _setup_phase2_entities(self, entities: list) -> None:
        setup_service_entities(self, entities)

    def _setup_phase3_entities(self, entities: list) -> None:
        setup_motion_entities(self, entities)

    def _setup_phase4_entities(self, entities: list) -> None:
        pass

    def _setup_phase5_entities(self, entities: list) -> None:
        setup_audio_direction_entities(self, entities)

    def _setup_phase6_entities(self, entities: list) -> None:
        setup_robot_info_entities(self, entities)

    def _setup_phase7_entities(self, entities: list) -> None:
        setup_imu_entities(self, entities)

    def _setup_phase8_entities(self, entities: list) -> None:
        setup_behavior_entities(self, entities)

    def _setup_phase9_entities(self, entities: list) -> None:
        """Setup Phase 9 entities: Audio controls."""
        _LOGGER.debug("Phase 9 entities registered: none")

    def _setup_phase10_entities(self, entities: list) -> None:
        setup_camera_entities(self, entities)

    def _setup_phase12_entities(self, entities: list) -> None:
        """Setup Phase 12 entities: Audio processing parameters."""
        _LOGGER.debug("Phase 12 entities registered: none")

    def _setup_phase21_entities(self, entities: list) -> None:
        pass

    def _setup_phase22_entities(self, entities: list) -> None:
        setup_detection_entities(self, entities)

    def _setup_phase23_entities(self, entities: list) -> None:
        pass

    def update_face_detected_state(self) -> None:
        """Push face_detected state update to Home Assistant."""
        if self._face_detected_entity:
            self._face_detected_entity.update_state()

    def update_gesture_state(self) -> None:
        """Push gesture state update to Home Assistant."""
        if self._gesture_entity:
            self._gesture_entity.update_state()
        if self._gesture_confidence_entity:
            self._gesture_confidence_entity.update_state()

    def set_services_suspended(self, is_suspended: bool) -> None:
        """Update the services suspended state and push to Home Assistant.

        Args:
            is_suspended: True if services are suspended (ML models unloaded)
        """
        if self._services_suspended_entity is not None:
            # For "running" device_class, True = running, False = not running
            # So we invert: suspended means NOT running
            self._services_suspended_entity._state = not is_suspended
            self._services_suspended_entity.update_state()
            _LOGGER.debug("Services suspended state updated: suspended=%s", is_suspended)

    def find_entity_references(self, entities: list) -> None:
        """Find and store references to special entities from existing list.

        Args:
            entities: The list of existing entities to search
        """
        # DOA entities are read-only sensors, no special references needed
        pass

    def _setup_phase24_entities(self, entities: list) -> None:
        setup_diagnostic_entities(self, entities)
