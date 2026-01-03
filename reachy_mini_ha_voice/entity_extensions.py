"""Extended ESPHome entity types for Reachy Mini control."""

from collections.abc import Iterable
from typing import Callable, List, Optional
import logging

from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ListEntitiesButtonResponse,
    ListEntitiesRequest,
    ListEntitiesSelectResponse,
    ListEntitiesSensorResponse,
    ListEntitiesSwitchResponse,
    ButtonCommandRequest,
    SelectCommandRequest,
    SelectStateResponse,
    SensorStateResponse,
    SubscribeHomeAssistantStatesRequest,
    SubscribeStatesRequest,
    SwitchCommandRequest,
    SwitchStateResponse,
)
from google.protobuf import message

from .api_server import APIServer
from .entity import ESPHomeEntity

logger = logging.getLogger(__name__)


class SensorStateClass:
    """ESPHome SensorStateClass enum values."""
    NONE = 0
    MEASUREMENT = 1
    TOTAL_INCREASING = 2
    TOTAL = 3


class SensorEntity(ESPHomeEntity):
    """Sensor entity for ESPHome (read-only numeric values)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        icon: str = "",
        unit_of_measurement: str = "",
        accuracy_decimals: int = 2,
        device_class: str = "",
        state_class: int = SensorStateClass.NONE,
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        value_getter: Optional[Callable[[], float]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.unit_of_measurement = unit_of_measurement
        self.accuracy_decimals = accuracy_decimals
        self.device_class = device_class
        self.entity_category = entity_category
        # Convert string state_class to int if needed (for backward compatibility)
        if isinstance(state_class, str):
            state_class_map = {
                "": SensorStateClass.NONE,
                "measurement": SensorStateClass.MEASUREMENT,
                "total_increasing": SensorStateClass.TOTAL_INCREASING,
                "total": SensorStateClass.TOTAL,
            }
            self.state_class = state_class_map.get(state_class.lower(), SensorStateClass.NONE)
        else:
            self.state_class = state_class
        self._value_getter = value_getter
        self._value = 0.0

    @property
    def value(self) -> float:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: float) -> None:
        self._value = new_value

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSensorResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                unit_of_measurement=self.unit_of_measurement,
                accuracy_decimals=self.accuracy_decimals,
                device_class=self.device_class,
                state_class=self.state_class,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()

    def _get_state_message(self) -> SensorStateResponse:
        return SensorStateResponse(
            key=self.key,
            state=self.value,
            missing_state=False,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class SwitchEntity(ESPHomeEntity):
    """Switch entity for ESPHome (read-write boolean values)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        icon: str = "",
        device_class: str = "",
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        value_getter: Optional[Callable[[], bool]] = None,
        value_setter: Optional[Callable[[bool], None]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.device_class = device_class
        self.entity_category = entity_category
        self._value_getter = value_getter
        self._value_setter = value_setter
        self._value = False

    @property
    def value(self) -> bool:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: bool) -> None:
        if self._value_setter:
            self._value_setter(new_value)
        self._value = new_value

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSwitchResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                device_class=self.device_class,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()
        elif isinstance(msg, SwitchCommandRequest) and msg.key == self.key:
            self.value = msg.state
            yield self._get_state_message()

    def _get_state_message(self) -> SwitchStateResponse:
        return SwitchStateResponse(
            key=self.key,
            state=self.value,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class SelectEntity(ESPHomeEntity):
    """Select entity for ESPHome (read-write string selection)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        options: List[str],
        icon: str = "",
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        value_getter: Optional[Callable[[], str]] = None,
        value_setter: Optional[Callable[[str], None]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.options = options
        self.icon = icon
        self.entity_category = entity_category
        self._value_getter = value_getter
        self._value_setter = value_setter
        self._value = options[0] if options else ""

    @property
    def value(self) -> str:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: str) -> None:
        if new_value in self.options:
            if self._value_setter:
                self._value_setter(new_value)
            self._value = new_value
        else:
            logger.warning(f"Invalid option '{new_value}' for {self.name}")

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSelectResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                options=self.options,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()
        elif isinstance(msg, SelectCommandRequest) and msg.key == self.key:
            self.value = msg.state
            yield self._get_state_message()

    def _get_state_message(self) -> SelectStateResponse:
        return SelectStateResponse(
            key=self.key,
            state=self.value,
            missing_state=False,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class ButtonEntity(ESPHomeEntity):
    """Button entity for ESPHome (trigger actions)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        icon: str = "",
        device_class: str = "",
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        on_press: Optional[Callable[[], None]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.device_class = device_class
        self.entity_category = entity_category
        self._on_press = on_press

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesButtonResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                device_class=self.device_class,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, ButtonCommandRequest) and msg.key == self.key:
            if self._on_press:
                try:
                    self._on_press()
                    logger.info(f"Button '{self.name}' pressed")
                except Exception as e:
                    logger.error(f"Error executing button '{self.name}': {e}")
            # Buttons don't have state responses
            return
            yield  # Make this a generator
