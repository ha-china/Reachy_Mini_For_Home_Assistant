"""Entity setup helpers for sensors, diagnostics, and motion control entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..core.system_diagnostics import get_system_diagnostics
from .entity import BinarySensorEntity, TextSensorEntity
from .entity_extensions import SensorEntity, SwitchEntity
from .entity_factory import (
    create_entity,
    get_diagnostic_sensor_definitions,
    get_imu_sensor_definitions,
    get_look_at_definitions,
    get_pose_control_definitions,
    get_robot_info_definitions,
)
from .entity_keys import get_entity_key

if TYPE_CHECKING:
    from .entity_registry import EntityRegistry

_LOGGER = logging.getLogger(__name__)


def append_defined_entities(registry: "EntityRegistry", entities: list, definitions: list, callback_map: dict) -> None:
    for definition in definitions:
        callbacks = callback_map.get(definition.key_name)
        if isinstance(callbacks, tuple):
            definition.value_getter = callbacks[0]
            definition.command_handler = callbacks[1]
        elif callbacks is not None:
            definition.value_getter = callbacks
        entities.append(create_entity(registry.server, definition))


def setup_motion_entities(registry: "EntityRegistry", entities: list) -> None:
    rc = registry.reachy_controller
    append_defined_entities(
        registry,
        entities,
        get_pose_control_definitions(),
        {
            "head_x": (rc.get_head_x, rc.set_head_x),
            "head_y": (rc.get_head_y, rc.set_head_y),
            "head_z": (rc.get_head_z, rc.set_head_z),
            "head_roll": (rc.get_head_roll, rc.set_head_roll),
            "head_pitch": (rc.get_head_pitch, rc.set_head_pitch),
            "head_yaw": (rc.get_head_yaw, rc.set_head_yaw),
            "body_yaw": (rc.get_body_yaw, rc.set_body_yaw),
            "antenna_left": (rc.get_antenna_left, rc.set_antenna_left),
            "antenna_right": (rc.get_antenna_right, rc.set_antenna_right),
        },
    )
    append_defined_entities(
        registry,
        entities,
        get_look_at_definitions(),
        {
            "look_at_x": (rc.get_look_at_x, rc.set_look_at_x),
            "look_at_y": (rc.get_look_at_y, rc.set_look_at_y),
            "look_at_z": (rc.get_look_at_z, rc.set_look_at_z),
        },
    )
    _LOGGER.debug("Motion entities registered")


def setup_audio_direction_entities(registry: "EntityRegistry", entities: list) -> None:
    rc = registry.reachy_controller
    entities.append(
        SensorEntity(
            server=registry.server,
            key=get_entity_key("doa_angle"),
            name="DOA Angle",
            object_id="doa_angle",
            icon="mdi:surround-sound",
            unit_of_measurement="°",
            accuracy_decimals=1,
            state_class="measurement",
            value_getter=rc.get_doa_angle_degrees,
        )
    )
    entities.append(
        BinarySensorEntity(
            server=registry.server,
            key=get_entity_key("speech_detected"),
            name="Speech Detected",
            object_id="speech_detected",
            icon="mdi:account-voice",
            device_class="sound",
            value_getter=rc.get_speech_detected,
        )
    )
    entities.append(
        SwitchEntity(
            server=registry.server,
            key=get_entity_key("doa_tracking_enabled"),
            name="DOA Sound Tracking",
            object_id="doa_tracking_enabled",
            icon="mdi:ear-hearing",
            value_getter=rc.get_doa_enabled,
            value_setter=rc.set_doa_enabled,
        )
    )


def setup_robot_info_entities(registry: "EntityRegistry", entities: list) -> None:
    rc = registry.reachy_controller
    append_defined_entities(
        registry,
        entities,
        get_robot_info_definitions(),
        {
            "control_loop_frequency": rc.get_control_loop_frequency,
            "sdk_version": rc.get_sdk_version,
            "robot_name": rc.get_robot_name,
            "wireless_version": rc.get_wireless_version,
            "simulation_mode": rc.get_simulation_mode,
            "wlan_ip": rc.get_wlan_ip,
            "error_message": rc.get_error_message,
        },
    )


def setup_imu_entities(registry: "EntityRegistry", entities: list) -> None:
    rc = registry.reachy_controller
    append_defined_entities(
        registry,
        entities,
        get_imu_sensor_definitions(),
        {
            "imu_accel_x": rc.get_imu_accel_x,
            "imu_accel_y": rc.get_imu_accel_y,
            "imu_accel_z": rc.get_imu_accel_z,
            "imu_gyro_x": rc.get_imu_gyro_x,
            "imu_gyro_y": rc.get_imu_gyro_y,
            "imu_gyro_z": rc.get_imu_gyro_z,
            "imu_temperature": rc.get_imu_temperature,
        },
    )


def setup_detection_entities(registry: "EntityRegistry", entities: list) -> None:
    def get_gesture() -> str:
        return registry.camera_server.get_current_gesture() if registry.camera_server else "none"

    def get_gesture_confidence() -> float:
        return registry.camera_server.get_gesture_confidence() if registry.camera_server else 0.0

    registry._gesture_entity = TextSensorEntity(
        server=registry.server,
        key=get_entity_key("gesture_detected"),
        name="Gesture Detected",
        object_id="gesture_detected",
        icon="mdi:hand-wave",
        value_getter=get_gesture,
    )
    entities.append(registry._gesture_entity)

    registry._gesture_confidence_entity = SensorEntity(
        server=registry.server,
        key=get_entity_key("gesture_confidence"),
        name="Gesture Confidence",
        object_id="gesture_confidence",
        icon="mdi:percent",
        unit_of_measurement="%",
        accuracy_decimals=1,
        state_class="measurement",
        value_getter=get_gesture_confidence,
    )
    entities.append(registry._gesture_confidence_entity)

    registry._face_detected_entity = BinarySensorEntity(
        server=registry.server,
        key=get_entity_key("face_detected"),
        name="Face Detected",
        object_id="face_detected",
        icon="mdi:face-recognition",
        device_class="occupancy",
        value_getter=lambda: registry.camera_server.is_face_detected() if registry.camera_server else False,
    )
    entities.append(registry._face_detected_entity)


def setup_diagnostic_entities(registry: "EntityRegistry", entities: list) -> None:
    diag = get_system_diagnostics()
    append_defined_entities(
        registry,
        entities,
        get_diagnostic_sensor_definitions(),
        {
            "sys_cpu_percent": diag.get_cpu_percent,
            "sys_cpu_temperature": diag.get_cpu_temperature,
            "sys_memory_percent": diag.get_memory_percent,
            "sys_memory_used": diag.get_memory_used_gb,
            "sys_disk_percent": diag.get_disk_percent,
            "sys_disk_free": diag.get_disk_free_gb,
            "sys_uptime": diag.get_uptime_hours,
            "sys_process_cpu": diag.get_process_cpu_percent,
            "sys_process_memory": diag.get_process_memory_mb,
        },
    )
