"""API server for Home Assistant integration."""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from .models import ServerState

_LOGGER = logging.getLogger(__name__)


class APIServer:
    """API server for Home Assistant."""

    def __init__(self, state: ServerState):
        """Initialize API server."""
        self.state = state
        self._handlers: Dict[str, callable] = {
            "hello": self._handle_hello,
            "list_entities": self._handle_list_entities,
            "get_state": self._handle_get_state,
            "subscribe_states": self._handle_subscribe_states,
        }

    async def handle_request(self, command: str, payload: dict) -> dict:
        """Handle an API request."""
        handler = self._handlers.get(command)
        if handler:
            try:
                return await handler(payload)
            except Exception as e:
                _LOGGER.error("Error handling request %s: %s", command, e)
                return {"error": str(e)}
        else:
            return {"error": f"Unknown command: {command}"}

    async def _handle_hello(self, payload: dict) -> dict:
        """Handle hello request."""
        return {
            "name": self.state.name,
            "mac_address": self.state.mac_address,
            "version": "1.0.0",
        }

    async def _handle_list_entities(self, payload: dict) -> dict:
        """Handle list_entities request."""
        entities = []
        for entity in self.state.entities:
            entities.append(
                {
                    "key": entity.key,
                    "name": entity.name,
                    "state": entity.state,
                    "attributes": entity.attributes,
                }
            )
        return {"entities": entities}

    async def _handle_get_state(self, payload: dict) -> dict:
        """Handle get_state request."""
        key = payload.get("key")
        entity = next((e for e in self.state.entities if e.key == key), None)
        if entity:
            return {
                "key": entity.key,
                "state": entity.state,
                "attributes": entity.attributes,
            }
        return {"error": "Entity not found"}

    async def _handle_subscribe_states(self, payload: dict) -> dict:
        """Handle subscribe_states request."""
        return {"result": "ok"}