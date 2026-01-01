"""Entity management for Home Assistant."""

import logging
from typing import Dict, List, Optional

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (  # type: ignore[attr-defined]
    ListEntitiesMediaPlayersResponse,
    MediaPlayerCommandRequest,
    TextSensorStateResponse,
)
from aioesphomeapi.model import MediaPlayerState

from .models import Entity

_LOGGER = logging.getLogger(__name__)


class MediaPlayerEntity(Entity):
    """Media player entity for voice assistant."""

    def __init__(
        self, server, key: int, name: str, object_id: str, music_player, announce_player
    ):
        """Initialize media player entity."""
        super().__init__(key=key, name=name, state="idle", attributes={})
        self.server = server
        self.object_id = object_id
        self.music_player = music_player
        self.announce_player = announce_player
        self._volume = 1.0
        self._position = 0
        self._duration = 0

    def handle_message(self, msg):
        """Handle a message."""
        if isinstance(msg, ListEntitiesMediaPlayersResponse):
            yield self.get_list_entities_response()
        elif isinstance(msg, MediaPlayerCommandRequest):
            self.handle_command(msg)

    def get_list_entities_response(self):
        """Get list entities response."""
        from aioesphomeapi.api_pb2 import ListEntitiesMediaPlayersResponse

        return ListEntitiesMediaPlayersResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
        )

    def handle_command(self, msg):
        """Handle a media player command."""
        if msg.command == MediaPlayerCommandRequest.PLAY:
            if msg.url:
                self.play([msg.url])
        elif msg.command == MediaPlayerCommandRequest.PAUSE:
            self.music_player.stop()
        elif msg.command == MediaPlayerCommandRequest.STOP:
            self.music_player.stop()
        elif msg.command == MediaPlayerCommandRequest.VOLUME_SET:
            self._volume = msg.volume / 255.0
        elif msg.command == MediaPlayerCommandRequest.MUTE:
            self._volume = 0.0 if msg.mute else 1.0

    def play(self, urls, announcement=False, done_callback=None):
        """Play media."""
        _LOGGER.debug("Playing: %s", urls)
        player = self.announce_player if announcement else self.music_player

        for url in urls:
            try:
                from urllib.request import urlopen

                with urlopen(url) as response:
                    audio_data = response.read()
                player.play(audio_data)
            except Exception as e:
                _LOGGER.error("Error playing %s: %s", url, e)

        if done_callback:
            done_callback()

    def duck(self):
        """Duck the volume."""
        _LOGGER.debug("Ducking media player")
        # Reduce volume by 50%
        # self._volume *= 0.5

    def unduck(self):
        """Unduck the volume."""
        _LOGGER.debug("Unducking media player")
        # Restore volume
        # self._volume = min(1.0, self._volume * 2.0)