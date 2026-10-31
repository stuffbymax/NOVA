"""Entity identity and storage for simulation objects."""

from dataclasses import dataclass, field
from typing import Any


EntityId = int


@dataclass
class Entity:
    """A stable entity with extensible component data."""

    entity_id: EntityId
    components: dict[str, Any] = field(default_factory=dict)


class EntityManager:
    """Creates, retrieves, and removes entities."""

    def __init__(self) -> None:
        self._next_id = 1
        self._entities: dict[EntityId, Entity] = {}

    def create(self, **components: Any) -> Entity:
        entity = Entity(self._next_id, components)
        self._next_id += 1
        self._entities[entity.entity_id] = entity
        return entity

    def get(self, entity_id: EntityId) -> Entity:
        try:
            return self._entities[entity_id]
        except KeyError as error:
            raise KeyError(f"Unknown entity id: {entity_id}") from error

    def remove(self, entity_id: EntityId) -> None:
        self._entities.pop(entity_id, None)

    def all(self) -> tuple[Entity, ...]:
        return tuple(self._entities.values())

    def clear(self) -> None:
        self._entities.clear()
