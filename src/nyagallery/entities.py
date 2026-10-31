from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Entity:
    type: str
    id: str
    name: str
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type.strip() or not self.id.strip() or not self.name.strip():
            raise ValueError("entity type, id and name are required")

    def to_dict(self) -> dict[str, object]:
        return {"type": self.type, "id": self.id, "name": self.name, "metadata": dict(self.metadata)}


class EntityLinks:
    """Deterministic in-memory many-to-many links for API/import pipelines."""

    def __init__(self) -> None:
        self._entities: dict[tuple[str, str], Entity] = {}
        self._assets: dict[tuple[str, str], set[str]] = {}

    def add_entity(self, entity: Entity) -> Entity:
        key = (entity.type, entity.id)
        self._entities[key] = entity
        self._assets.setdefault(key, set())
        return entity

    def link(self, entity_type: str, entity_id: str, asset_key: str) -> None:
        key = (entity_type, entity_id)
        if key not in self._entities:
            raise KeyError(f"unknown entity: {entity_type}/{entity_id}")
        if not asset_key.strip():
            raise ValueError("asset_key is required")
        self._assets.setdefault(key, set()).add(asset_key)

    def unlink(self, entity_type: str, entity_id: str, asset_key: str) -> bool:
        assets = self._assets.get((entity_type, entity_id), set())
        if asset_key not in assets:
            return False
        assets.remove(asset_key)
        return True

    def assets_for(self, entity_type: str, entity_id: str) -> tuple[str, ...]:
        return tuple(sorted(self._assets.get((entity_type, entity_id), set())))

    def entities_for_asset(self, asset_key: str) -> tuple[Entity, ...]:
        return tuple(sorted((self._entities[key] for key, assets in self._assets.items() if asset_key in assets), key=lambda item: (item.type, item.id)))

    def iter_entities(self) -> Iterable[Entity]:
        return tuple(sorted(self._entities.values(), key=lambda item: (item.type, item.id)))
