"""ESPHome entity definitions."""

from abc import abstractmethod
from collections.abc import Iterable
from typing import Callable, List, Optional, Union
import logging

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ListEntitiesBinarySensorResponse,
    ListEntitiesCameraResponse,
    ListEntitiesMediaPlayerResponse,
    ListEntitiesNumberResponse,
    ListEntitiesRequest,
    ListEntitiesTextSensorResponse,
    BinarySensorStateResponse,
    CameraImageRequest,
    CameraImageResponse,
    MediaPlayerCommandRequest,
    MediaPlayerStateResponse,
    NumberCommandRequest,
    NumberStateResponse,
    SubscribeHomeAssistantStatesRequest,
    SubscribeStatesRequest,
    TextSensorStateResponse,
)
from aioesphomeapi.model import MediaPlayerCommand, MediaPlayerState, MediaPlayerEntityFeature
from google.protobuf import message

from .api_server import APIServer
from .audio_player import AudioPlayer
from .util import call_all

logger = logging.getLogger(__name__)


class ESPHomeEntity:
    """Base class for ESPHome entities."""

    def __init__(self, server: APIServer) -> None:
        self.server = server

    @abstractmethod
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        pass


class MediaPlayerEntity(ESPHomeEntity):
    """Media player entity for ESPHome."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        music_player: AudioPlayer,
        announce_player: AudioPlayer,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.state = MediaPlayerState.IDLE
        self.volume = 1.0
        self.muted = False
        self.music_player = music_player
        self.announce_player = announce_player

    def play(
        self,
        url: Union[str, List[str]],
        announcement: bool = False,
        done_callback: Optional[Callable[[], None]] = None,
    ) -> Iterable[message.Message]:
        if announcement:
            if self.music_player.is_playing:
                # Announce, resume music
                self.music_player.pause()
                self.announce_player.play(
                    url,
                    done_callback=lambda: call_all(
                        self.music_player.resume, done_callback
                    ),
                )
            else:
                # Announce, idle
                self.announce_player.play(
                    url,
                    done_callback=lambda: call_all(
                        lambda: self.server.send_messages(
                            [self._update_state(MediaPlayerState.IDLE)]
                        ),
                        done_callback,
                    ),
                )
        else:
            # Music
            self.music_player.play(
                url,
                done_callback=lambda: call_all(
                    lambda: self.server.send_messages(
                        [self._update_state(MediaPlayerState.IDLE)]
                    ),
                    done_callback,
                ),
            )

        yield self._update_state(MediaPlayerState.PLAYING)

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, MediaPlayerCommandRequest) and (msg.key == self.key):
            if msg.has_media_url:
                announcement = msg.has_announcement and msg.announcement
                yield from self.play(msg.media_url, announcement=announcement)
            elif msg.has_command:
                if msg.command == MediaPlayerCommand.PAUSE:
                    self.music_player.pause()
                    yield self._update_state(MediaPlayerState.PAUSED)
                elif msg.command == MediaPlayerCommand.PLAY:
                    self.music_player.resume()
                    yield self._update_state(MediaPlayerState.PLAYING)
            elif msg.has_volume:
                volume = int(msg.volume * 100)
                self.music_player.set_volume(volume)
                self.announce_player.set_volume(volume)
                self.volume = msg.volume
                yield self._update_state(self.state)
        elif isinstance(msg, ListEntitiesRequest):
            # Set feature flags for Music Assistant compatibility
            # PLAY_MEDIA (512) is required for Music Assistant to recognize the player
            feature_flags = (
                MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.PLAY_MEDIA
                | MediaPlayerEntityFeature.VOLUME_SET
                | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
            )
            yield ListEntitiesMediaPlayerResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                supports_pause=True,
                feature_flags=feature_flags,
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            yield self._get_state_message()

    def _update_state(self, new_state: MediaPlayerState) -> MediaPlayerStateResponse:
        self.state = new_state
        return self._get_state_message()

    def _get_state_message(self) -> MediaPlayerStateResponse:
        return MediaPlayerStateResponse(
            key=self.key,
            state=self.state,
            volume=self.volume,
            muted=self.muted,
        )


class TextSensorEntity(ESPHomeEntity):
    """Text sensor entity for ESPHome (read-only string values)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        icon: str = "",
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        value_getter: Optional[Callable[[], str]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.entity_category = entity_category
        self._value_getter = value_getter
        self._value = ""

    @property
    def value(self) -> str:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: str) -> None:
        self._value = new_value

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesTextSensorResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()

    def _get_state_message(self) -> TextSensorStateResponse:
        return TextSensorStateResponse(
            key=self.key,
            state=self.value,
            missing_state=False,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class BinarySensorEntity(ESPHomeEntity):
    """Binary sensor entity for ESPHome (read-only boolean values)."""

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
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.device_class = device_class
        self.entity_category = entity_category
        self._value_getter = value_getter
        self._value = False

    @property
    def value(self) -> bool:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: bool) -> None:
        self._value = new_value

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesBinarySensorResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                device_class=self.device_class,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()

    def _get_state_message(self) -> BinarySensorStateResponse:
        return BinarySensorStateResponse(
            key=self.key,
            state=self.value,
            missing_state=False,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class NumberEntity(ESPHomeEntity):
    """Number entity for ESPHome (read-write numeric values)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        min_value: float = 0.0,
        max_value: float = 100.0,
        step: float = 1.0,
        icon: str = "",
        unit_of_measurement: str = "",
        mode: int = 0,  # 0 = auto, 1 = box, 2 = slider
        entity_category: int = 0,  # 0 = none, 1 = config, 2 = diagnostic
        value_getter: Optional[Callable[[], float]] = None,
        value_setter: Optional[Callable[[float], None]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.icon = icon
        self.unit_of_measurement = unit_of_measurement
        self.mode = mode
        self.entity_category = entity_category
        self._value_getter = value_getter
        self._value_setter = value_setter
        self._value = min_value

    @property
    def value(self) -> float:
        if self._value_getter:
            return self._value_getter()
        return self._value

    @value.setter
    def value(self, new_value: float) -> None:
        # Clamp value to valid range
        new_value = max(self.min_value, min(self.max_value, new_value))
        if self._value_setter:
            self._value_setter(new_value)
        self._value = new_value

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesNumberResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
                min_value=self.min_value,
                max_value=self.max_value,
                step=self.step,
                unit_of_measurement=self.unit_of_measurement,
                mode=self.mode,
                entity_category=self.entity_category,
            )
        elif isinstance(msg, (SubscribeHomeAssistantStatesRequest, SubscribeStatesRequest)):
            yield self._get_state_message()
        elif isinstance(msg, NumberCommandRequest) and msg.key == self.key:
            self.value = msg.state
            yield self._get_state_message()

    def _get_state_message(self) -> NumberStateResponse:
        return NumberStateResponse(
            key=self.key,
            state=self.value,
            missing_state=False,
        )

    def update_state(self) -> None:
        """Send state update to Home Assistant."""
        self.server.send_messages([self._get_state_message()])


class CameraEntity(ESPHomeEntity):
    """Camera entity for ESPHome (provides image snapshots)."""

    def __init__(
        self,
        server: APIServer,
        key: int,
        name: str,
        object_id: str,
        icon: str = "mdi:camera",
        image_getter: Optional[Callable[[], Optional[bytes]]] = None,
    ) -> None:
        ESPHomeEntity.__init__(self, server)
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self._image_getter = image_getter

    def get_image(self) -> Optional[bytes]:
        """Get the current camera image as JPEG bytes."""
        if self._image_getter:
            return self._image_getter()
        return None

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesCameraResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon=self.icon,
            )
        elif isinstance(msg, CameraImageRequest):
            # CameraImageRequest doesn't have a key field - it's a global request
            # Return camera image for any camera request
            image_data = self.get_image()
            if image_data:
                yield CameraImageResponse(
                    key=self.key,
                    data=image_data,
                    done=True,
                )
            else:
                # Return empty response if no image available
                yield CameraImageResponse(
                    key=self.key,
                    data=b"",
                    done=True,
                )
