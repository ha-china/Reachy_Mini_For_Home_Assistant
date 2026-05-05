"""Entity setup helpers for runtime/control related entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .entity import BinarySensorEntity, CameraEntity, NumberEntity, TextSensorEntity
from .entity_extensions import SelectEntity, SensorEntity, SwitchEntity
from .entity_keys import get_entity_key

if TYPE_CHECKING:
    from .entity_registry import EntityRegistry

_LOGGER = logging.getLogger(__name__)


def setup_runtime_entities(registry: "EntityRegistry", entities: list) -> None:
    rc = registry.reachy_controller

    entities.append(
        TextSensorEntity(
            server=registry.server,
            key=get_entity_key("daemon_state"),
            name="Daemon State",
            object_id="daemon_state",
            icon="mdi:robot",
            value_getter=rc.get_daemon_state,
        )
    )
    entities.append(
        BinarySensorEntity(
            server=registry.server,
            key=get_entity_key("backend_ready"),
            name="Backend Ready",
            object_id="backend_ready",
            icon="mdi:check-circle",
            device_class="connectivity",
            value_getter=rc.get_backend_ready,
        )
    )
    entities.append(
        NumberEntity(
            server=registry.server,
            key=get_entity_key("speaker_volume"),
            name="Speaker Volume",
            object_id="speaker_volume",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            icon="mdi:volume-high",
            unit_of_measurement="%",
            mode=2,
            entity_category=1,
            value_getter=rc.get_speaker_volume,
            value_setter=rc.set_speaker_volume,
        )
    )

    def get_muted() -> bool:
        state = registry._get_server_state()
        return bool(state.is_muted)

    def set_muted(muted: bool) -> None:
        state = registry._get_server_state()
        state.is_muted = muted
        voice_assistant = registry.server._voice_assistant_service
        if muted:
            voice_assistant._suspend_voice_services(reason="mute")
        else:
            voice_assistant._resume_voice_services(reason="mute")

    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("mute"),
            name="Mute",
            object_id="mute",
            icon="mdi:microphone-off",
            entity_category=1,
            value_getter=get_muted,
            value_setter=set_muted,
        )
    )

    def get_camera_disabled() -> bool:
        state = registry._get_server_state()
        return not state.camera_enabled if state is not None else False

    def set_camera_disabled(disabled: bool) -> None:
        state = registry._get_server_state()
        if state is None:
            return
        state.camera_enabled = not disabled
        if registry.camera_server:
            if disabled:
                registry.camera_server.suspend()
            else:
                registry.camera_server.resume_from_suspend()

    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("camera_disabled"),
            name="Disable Camera",
            object_id="camera_disabled",
            icon="mdi:camera-off",
            entity_category=1,
            value_getter=get_camera_disabled,
            value_setter=set_camera_disabled,
        )
    )

    entities.append(
        registry._make_preference_switch(
            key_name="idle_behavior_enabled",
            name="Idle Behavior",
            object_id="idle_behavior_enabled",
            icon="mdi:motion-play",
            getter=lambda: bool(registry._get_preferences().idle_behavior_enabled)
            if registry._get_preferences()
            else False,
            setter=registry._set_idle_behavior_enabled,
        )
    )

    def sync_sendspin() -> None:
        registry.server._voice_assistant_service.set_sendspin_enabled(registry._get_pref_bool("sendspin_enabled"))

    entities.append(
        registry._make_stored_switch(
            key_name="sendspin_enabled",
            name="Sendspin",
            object_id="sendspin_enabled",
            icon="mdi:speaker-wireless",
            pref_key="sendspin_enabled",
            after_set=sync_sendspin,
        )
    )
    registry._face_tracking_switch_entity = registry._make_stored_switch(
        key_name="face_tracking_enabled",
        name="Face Tracking",
        object_id="face_tracking_enabled",
        icon="mdi:face-recognition",
        pref_key="face_tracking_enabled",
        after_set=registry._apply_vision_runtime_state,
    )
    entities.append(registry._face_tracking_switch_entity)

    registry._gesture_detection_switch_entity = registry._make_stored_switch(
        key_name="gesture_detection_enabled",
        name="Gesture Detection",
        object_id="gesture_detection_enabled",
        icon="mdi:hand-wave",
        pref_key="gesture_detection_enabled",
        after_set=registry._apply_vision_runtime_state,
    )
    entities.append(registry._gesture_detection_switch_entity)

    def get_face_confidence_threshold() -> float:
        return registry._get_pref_float("face_confidence_threshold", 0.5)

    def set_face_confidence_threshold(value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        registry._set_pref_float("face_confidence_threshold", value)
        if registry.camera_server is not None:
            registry.camera_server.set_face_confidence_threshold(value)

    entities.append(
        registry._make_preference_number(
            key_name="face_confidence_threshold",
            name="Face Confidence",
            object_id="face_confidence_threshold",
            icon="mdi:target",
            getter=get_face_confidence_threshold,
            setter=set_face_confidence_threshold,
            min_value=0.0,
            max_value=1.0,
            step=0.01,
        )
    )

    _LOGGER.debug("Phase 1 entities registered")


def setup_service_entities(registry: "EntityRegistry", entities: list) -> None:
    registry._services_suspended_entity = BinarySensorEntity(
        server=registry.server,
        key=get_entity_key("services_suspended"),
        name="Services Suspended",
        object_id="services_suspended",
        icon="mdi:pause-circle",
        device_class="running",
    )
    entities.append(registry._services_suspended_entity)
    _LOGGER.debug("Service state entities registered")


def setup_behavior_entities(registry: "EntityRegistry", entities: list) -> None:
    def get_emotion() -> str:
        return registry._current_emotion

    def set_emotion(emotion: str) -> None:
        registry._current_emotion = emotion
        emotion_name = registry._emotion_map.get(emotion)
        if emotion_name and registry._play_emotion_callback:
            registry._play_emotion_callback(emotion_name)
            registry._current_emotion = "None"

    entities.append(
        SelectEntity(
            server=registry.server,
            key=get_entity_key("emotion"),
            name="Emotion",
            object_id="emotion",
            options=list(registry._emotion_map.keys()),
            icon="mdi:emoticon",
            value_getter=get_emotion,
            value_setter=set_emotion,
        )
    )

    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("continuous_conversation"),
            name="Continuous Conversation",
            object_id="continuous_conversation",
            icon="mdi:message-reply-text",
            device_class="switch",
            entity_category=1,
            value_getter=lambda: registry._get_pref_bool("continuous_conversation"),
            value_setter=lambda enabled: registry._set_pref_bool("continuous_conversation", enabled),
        )
    )
    _LOGGER.debug("Behavior entities registered")


def setup_camera_entities(registry: "EntityRegistry", entities: list) -> None:
    def get_camera_image() -> bytes | None:
        if registry.camera_server:
            try:
                return registry.camera_server.get_snapshot()
            except Exception as e:
                _LOGGER.debug("Failed to get camera snapshot: %s", e)
        return None

    entities.append(
        CameraEntity(
            server=registry.server,
            key=get_entity_key("camera"),
            name="Camera",
            object_id="camera",
            icon="mdi:camera",
            image_getter=get_camera_image,
        )
    )
