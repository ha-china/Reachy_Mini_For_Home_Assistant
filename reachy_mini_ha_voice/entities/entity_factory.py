"""Entity factory for creating ESPHome entities.

This module provides factory functions for creating entities in a declarative way,
reducing boilerplate code in entity_registry.py.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..entity import BinarySensorEntity, CameraEntity, NumberEntity, TextSensorEntity
from ..entity_extensions import SensorEntity, SwitchEntity, SelectEntity, ButtonEntity
from .entity_keys import get_entity_key

_LOGGER = logging.getLogger(__name__)


class EntityType(Enum):
    """Supported entity types."""
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    TEXT_SENSOR = "text_sensor"
    SWITCH = "switch"
    SELECT = "select"
    BUTTON = "button"
    NUMBER = "number"
    CAMERA = "camera"


@dataclass
class EntityDefinition:
    """Definition for an entity to be created."""
    entity_type: EntityType
    key_name: str
    name: str
    object_id: str
    icon: str = "mdi:information"

    # Common optional fields
    entity_category: Optional[int] = None  # 0=None, 1=config, 2=diagnostic

    # Sensor specific
    unit_of_measurement: Optional[str] = None
    accuracy_decimals: Optional[int] = None
    state_class: Optional[str] = None
    device_class: Optional[str] = None

    # Number specific
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    mode: Optional[int] = None  # 0=auto, 1=box, 2=slider

    # Select specific
    options: Optional[List[str]] = None

    # Callbacks (set at runtime)
    value_getter: Optional[Callable] = None
    command_handler: Optional[Callable] = None

    # Additional kwargs
    extra: Dict[str, Any] = field(default_factory=dict)


def create_entity(server, definition: EntityDefinition) -> Any:
    """Create an entity from a definition.

    Args:
        server: The VoiceSatelliteProtocol server instance
        definition: The entity definition

    Returns:
        The created entity instance
    """
    key = get_entity_key(definition.key_name)

    common_args = {
        "server": server,
        "key": key,
        "name": definition.name,
        "object_id": definition.object_id,
        "icon": definition.icon,
    }

    if definition.entity_category is not None:
        common_args["entity_category"] = definition.entity_category

    if definition.entity_type == EntityType.SENSOR:
        args = {**common_args}
        if definition.unit_of_measurement:
            args["unit_of_measurement"] = definition.unit_of_measurement
        if definition.accuracy_decimals is not None:
            args["accuracy_decimals"] = definition.accuracy_decimals
        if definition.state_class:
            args["state_class"] = definition.state_class
        if definition.device_class:
            args["device_class"] = definition.device_class
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        args.update(definition.extra)
        return SensorEntity(**args)

    elif definition.entity_type == EntityType.BINARY_SENSOR:
        args = {**common_args}
        if definition.device_class:
            args["device_class"] = definition.device_class
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        args.update(definition.extra)
        return BinarySensorEntity(**args)

    elif definition.entity_type == EntityType.TEXT_SENSOR:
        args = {**common_args}
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        args.update(definition.extra)
        return TextSensorEntity(**args)

    elif definition.entity_type == EntityType.SWITCH:
        args = {**common_args}
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        if definition.command_handler:
            args["command_handler"] = definition.command_handler
        args.update(definition.extra)
        return SwitchEntity(**args)

    elif definition.entity_type == EntityType.SELECT:
        args = {**common_args}
        if definition.options:
            args["options"] = definition.options
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        if definition.command_handler:
            args["command_handler"] = definition.command_handler
        args.update(definition.extra)
        return SelectEntity(**args)

    elif definition.entity_type == EntityType.BUTTON:
        args = {**common_args}
        if definition.command_handler:
            args["command_handler"] = definition.command_handler
        args.update(definition.extra)
        return ButtonEntity(**args)

    elif definition.entity_type == EntityType.NUMBER:
        args = {**common_args}
        if definition.min_value is not None:
            args["min_value"] = definition.min_value
        if definition.max_value is not None:
            args["max_value"] = definition.max_value
        if definition.step is not None:
            args["step"] = definition.step
        if definition.mode is not None:
            args["mode"] = definition.mode
        if definition.unit_of_measurement:
            args["unit_of_measurement"] = definition.unit_of_measurement
        if definition.value_getter:
            args["value_getter"] = definition.value_getter
        if definition.command_handler:
            # NumberEntity uses value_setter instead of command_handler
            args["value_setter"] = definition.command_handler
        args.update(definition.extra)
        return NumberEntity(**args)

    elif definition.entity_type == EntityType.CAMERA:
        args = {**common_args}
        args.update(definition.extra)
        return CameraEntity(**args)

    else:
        raise ValueError(f"Unknown entity type: {definition.entity_type}")


def create_entities(server, definitions: List[EntityDefinition]) -> List[Any]:
    """Create multiple entities from definitions.

    Args:
        server: The VoiceSatelliteProtocol server instance
        definitions: List of entity definitions

    Returns:
        List of created entity instances
    """
    entities = []
    for definition in definitions:
        try:
            entity = create_entity(server, definition)
            entities.append(entity)
        except Exception as e:
            _LOGGER.error("Failed to create entity %s: %s", definition.key_name, e)
    return entities


# ============================================================================
# Predefined entity definition groups
# ============================================================================

def get_diagnostic_sensor_definitions() -> List[EntityDefinition]:
    """Get definitions for diagnostic sensor entities."""
    return [
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_cpu_percent",
            name="System CPU Usage",
            object_id="sys_cpu_percent",
            icon="mdi:cpu-64-bit",
            unit_of_measurement="%",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_cpu_temperature",
            name="CPU Temperature",
            object_id="sys_cpu_temperature",
            icon="mdi:thermometer",
            unit_of_measurement="°C",
            accuracy_decimals=1,
            device_class="temperature",
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_memory_percent",
            name="System Memory Usage",
            object_id="sys_memory_percent",
            icon="mdi:memory",
            unit_of_measurement="%",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_memory_used",
            name="System Memory Used",
            object_id="sys_memory_used",
            icon="mdi:memory",
            unit_of_measurement="GB",
            accuracy_decimals=2,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_disk_percent",
            name="System Disk Usage",
            object_id="sys_disk_percent",
            icon="mdi:harddisk",
            unit_of_measurement="%",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_disk_free",
            name="System Disk Free",
            object_id="sys_disk_free",
            icon="mdi:harddisk",
            unit_of_measurement="GB",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_uptime",
            name="System Uptime",
            object_id="sys_uptime",
            icon="mdi:clock-outline",
            unit_of_measurement="h",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_process_cpu",
            name="App CPU Usage",
            object_id="sys_process_cpu",
            icon="mdi:application-cog",
            unit_of_measurement="%",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="sys_process_memory",
            name="App Memory Usage",
            object_id="sys_process_memory",
            icon="mdi:application-cog",
            unit_of_measurement="MB",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
    ]


def get_imu_sensor_definitions() -> List[EntityDefinition]:
    """Get definitions for IMU sensor entities."""
    definitions = []

    # Accelerometer
    for axis in ["x", "y", "z"]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name=f"imu_accel_{axis}",
            name=f"IMU Accel {axis.upper()}",
            object_id=f"imu_accel_{axis}",
            icon=f"mdi:axis-{axis}-arrow",
            unit_of_measurement="m/s²",
            accuracy_decimals=3,
            state_class="measurement",
        ))

    # Gyroscope
    for axis in ["x", "y", "z"]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name=f"imu_gyro_{axis}",
            name=f"IMU Gyro {axis.upper()}",
            object_id=f"imu_gyro_{axis}",
            icon="mdi:rotate-3d-variant",
            unit_of_measurement="rad/s",
            accuracy_decimals=3,
            state_class="measurement",
        ))

    # Temperature
    definitions.append(EntityDefinition(
        entity_type=EntityType.SENSOR,
        key_name="imu_temperature",
        name="IMU Temperature",
        object_id="imu_temperature",
        icon="mdi:thermometer",
        unit_of_measurement="°C",
        accuracy_decimals=1,
        device_class="temperature",
        state_class="measurement",
    ))

    return definitions


def get_robot_info_definitions() -> List[EntityDefinition]:
    """Get definitions for robot info entities."""
    return [
        EntityDefinition(
            entity_type=EntityType.SENSOR,
            key_name="control_loop_frequency",
            name="Control Loop Frequency",
            object_id="control_loop_frequency",
            icon="mdi:speedometer",
            unit_of_measurement="Hz",
            accuracy_decimals=1,
            state_class="measurement",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.TEXT_SENSOR,
            key_name="sdk_version",
            name="SDK Version",
            object_id="sdk_version",
            icon="mdi:information",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.TEXT_SENSOR,
            key_name="robot_name",
            name="Robot Name",
            object_id="robot_name",
            icon="mdi:robot",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.BINARY_SENSOR,
            key_name="wireless_version",
            name="Wireless Version",
            object_id="wireless_version",
            icon="mdi:wifi",
            device_class="connectivity",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.BINARY_SENSOR,
            key_name="simulation_mode",
            name="Simulation Mode",
            object_id="simulation_mode",
            icon="mdi:virtual-reality",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.TEXT_SENSOR,
            key_name="wlan_ip",
            name="WLAN IP",
            object_id="wlan_ip",
            icon="mdi:ip-network",
            entity_category=2,
        ),
        EntityDefinition(
            entity_type=EntityType.TEXT_SENSOR,
            key_name="error_message",
            name="Error Message",
            object_id="error_message",
            icon="mdi:alert-circle",
            entity_category=2,
        ),
    ]


def get_pose_control_definitions() -> List[EntityDefinition]:
    """Get definitions for pose control entities (Phase 3)."""
    definitions = []

    # Head position controls (X, Y, Z in mm)
    for axis in ["x", "y", "z"]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.NUMBER,
            key_name=f"head_{axis}",
            name=f"Head {axis.upper()} Position",
            object_id=f"head_{axis}",
            icon=f"mdi:axis-{axis}-arrow",
            min_value=-50.0,
            max_value=50.0,
            step=1.0,
            unit_of_measurement="mm",
            mode=2,  # slider
        ))

    # Head orientation controls (Roll, Pitch in degrees)
    for orient in ["roll", "pitch"]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.NUMBER,
            key_name=f"head_{orient}",
            name=f"Head {orient.capitalize()}",
            object_id=f"head_{orient}",
            icon="mdi:rotate-3d-variant",
            min_value=-40.0,
            max_value=40.0,
            step=1.0,
            unit_of_measurement="°",
            mode=2,
        ))

    # Head yaw (wider range)
    definitions.append(EntityDefinition(
        entity_type=EntityType.NUMBER,
        key_name="head_yaw",
        name="Head Yaw",
        object_id="head_yaw",
        icon="mdi:rotate-3d-variant",
        min_value=-180.0,
        max_value=180.0,
        step=1.0,
        unit_of_measurement="°",
        mode=2,
    ))

    # Body yaw control
    definitions.append(EntityDefinition(
        entity_type=EntityType.NUMBER,
        key_name="body_yaw",
        name="Body Yaw",
        object_id="body_yaw",
        icon="mdi:rotate-3d-variant",
        min_value=-160.0,
        max_value=160.0,
        step=1.0,
        unit_of_measurement="°",
        mode=2,
    ))

    # Antenna controls
    for side, label in [("left", "L"), ("right", "R")]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.NUMBER,
            key_name=f"antenna_{side}",
            name=f"Antenna({label})",
            object_id=f"antenna_{side}",
            icon="mdi:antenna",
            min_value=-90.0,
            max_value=90.0,
            step=1.0,
            unit_of_measurement="°",
            mode=2,
        ))

    return definitions


def get_look_at_definitions() -> List[EntityDefinition]:
    """Get definitions for look-at control entities (Phase 4)."""
    definitions = []

    for axis in ["x", "y", "z"]:
        definitions.append(EntityDefinition(
            entity_type=EntityType.NUMBER,
            key_name=f"look_at_{axis}",
            name=f"Look At {axis.upper()}",
            object_id=f"look_at_{axis}",
            icon="mdi:crosshairs-gps",
            min_value=-2.0,
            max_value=2.0,
            step=0.1,
            unit_of_measurement="m",
            mode=1,  # Box mode for precise input
        ))

    return definitions
