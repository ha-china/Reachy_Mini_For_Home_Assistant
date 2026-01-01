"""Entity management for Home Assistant."""

import logging
from typing import Dict, List

from .models import Entity

_LOGGER = logging.getLogger(__name__)


class EntityManager:
    """Manage Home Assistant entities."""

    def __init__(self):
        """Initialize entity manager."""
        self._entities: Dict[str, Entity] = {}

    def add_entity(self, entity: Entity) -> None:
        """Add an entity."""
        self._entities[entity.key] = entity
        _LOGGER.debug("Added entity: %s", entity.key)

    def update_entity(self, key: str, state: str, attributes: Dict[str, str]) -> None:
        """Update an entity."""
        if key in self._entities:
            self._entities[key].state = state
            self._entities[key].attributes.update(attributes)
            _LOGGER.debug("Updated entity: %s", key)

    def get_entity(self, key: str) -> Entity:
        """Get an entity by key."""
        return self._entities.get(key)

    def list_entities(self) -> List[Entity]:
        """List all entities."""
        return list(self._entities.values())