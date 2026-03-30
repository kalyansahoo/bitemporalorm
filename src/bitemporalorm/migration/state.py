from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class FieldSnapshot:
    name: str
    sql_type: str           # e.g. "TEXT", "BIGINT"
    relationship: str       # "many_to_one", "one_to_one", "one_to_many"
    entity_ref: str | None  # referenced entity class name if ENTITY_REF, else None


@dataclass
class EntitySnapshot:
    name: str
    table_name: str
    fields: dict[str, FieldSnapshot] = field(default_factory=dict)
    parent_entity: str | None = None  # class name of parent entity


@dataclass
class MigrationState:
    entities: dict[str, EntitySnapshot] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Build from live registry
    # ------------------------------------------------------------------

    @classmethod
    def from_registry(cls) -> MigrationState:
        from bitemporalorm.registry import registry

        state = cls()
        for entity_cls in registry.all():
            if entity_cls.__name__ == "Entity":
                continue
            snap = _snapshot_entity(entity_cls)
            state.entities[snap.name] = snap
        return state

    # ------------------------------------------------------------------
    # Build by replaying migration files
    # ------------------------------------------------------------------

    @classmethod
    def from_migration_history(cls, migrations_dir: str) -> MigrationState:
        from bitemporalorm.migration.loader import MigrationLoader

        loader = MigrationLoader(migrations_dir)
        migrations = loader.load()
        state = cls()
        for mig in migrations:
            for op in mig.operations:
                op.apply_to_state(state)
        return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snapshot_entity(entity_cls: type) -> EntitySnapshot:
    meta = entity_cls._meta
    fields: dict[str, FieldSnapshot] = {}

    # Only own fields (not inherited) for the snapshot
    for fname, fspec in meta.fields.items():
        fields[fname] = FieldSnapshot(
            name=fname,
            sql_type=fspec.sql_type.value,
            relationship=fspec.relationship.value,
            entity_ref=fspec.entity_ref,
        )

    parent_name: str | None = None
    if meta.parent_entity is not None:
        parent_name = meta.parent_entity.__name__

    return EntitySnapshot(
        name=entity_cls.__name__,
        table_name=meta.table_name,
        fields=fields,
        parent_entity=parent_name,
    )
