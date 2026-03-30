from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bitemporalorm.entity import Entity


class EntityRegistry:
    """Global singleton registry of all Entity subclasses."""

    def __init__(self) -> None:
        self._entities: dict[str, type[Entity]] = {}

    def register(self, entity: type[Entity]) -> None:
        name = entity.__name__
        if name in self._entities and self._entities[name] is not entity:
            raise ValueError(f"An entity named '{name}' is already registered.")
        self._entities[name] = entity

    def get(self, name: str) -> type[Entity]:
        try:
            return self._entities[name]
        except KeyError:
            raise LookupError(f"No entity named '{name}' is registered. "
                               "Make sure all entity modules are imported before querying.") from None

    def all(self) -> list[type[Entity]]:
        return list(self._entities.values())

    def clear(self) -> None:
        self._entities.clear()

    def snapshot(self) -> dict[str, type[Entity]]:
        return dict(self._entities)

    def restore(self, snap: dict[str, type[Entity]]) -> None:
        self._entities = snap


registry: EntityRegistry = EntityRegistry()
