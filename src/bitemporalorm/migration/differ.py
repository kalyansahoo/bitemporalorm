from __future__ import annotations

from bitemporalorm.migration.ops import (
    CreateEntityTable,
    CreateFieldTables,
    CreateHierarchyTable,
    DropEntityTable,
    DropFieldTables,
    DropHierarchyTable,
    Operation,
)
from bitemporalorm.migration.state import MigrationState


class MigrationError(Exception):
    """Raised when an unsupported schema change is detected."""


class SchemaDiffer:
    """Compares two MigrationState snapshots and emits a list of Operations."""

    def diff(self, old: MigrationState, new: MigrationState) -> list[Operation]:
        ops: list[Operation] = []

        old_entities = old.entities
        new_entities = new.entities

        all_names = set(old_entities) | set(new_entities)

        # Order: create new entities before modifying existing ones,
        # drop old entities after processing existing ones.
        new_names     = [n for n in new_entities if n not in old_entities]
        dropped_names = [n for n in old_entities if n not in new_entities]
        kept_names    = [n for n in new_entities if n in old_entities]

        # ---- New entities ------------------------------------------------
        for name in new_names:
            snap = new_entities[name]
            ops.append(CreateEntityTable(name, snap.table_name))

            # Hierarchy
            if snap.parent_entity:
                parent_snap = new_entities.get(snap.parent_entity) or old_entities.get(snap.parent_entity)
                if parent_snap is None:
                    raise MigrationError(
                        f"Entity '{name}' references unknown parent '{snap.parent_entity}'."
                    )
                ops.append(CreateHierarchyTable(
                    entity_name=name,
                    entity_table=snap.table_name,
                    parent_entity_name=snap.parent_entity,
                    parent_table=parent_snap.table_name,
                ))

            for fname, fsnap in snap.fields.items():
                ref_table = _resolve_ref_table(fsnap.entity_ref, new_entities, old_entities)
                ops.append(CreateFieldTables(
                    entity_name=name,
                    entity_table=snap.table_name,
                    field_name=fname,
                    sql_type=fsnap.sql_type,
                    relationship=fsnap.relationship,
                    entity_ref=fsnap.entity_ref,
                    ref_table=ref_table,
                ))

        # ---- Kept entities — diff fields ----------------------------------
        for name in kept_names:
            old_snap = old_entities[name]
            new_snap = new_entities[name]

            # Parent entity change is forbidden
            if old_snap.parent_entity != new_snap.parent_entity:
                raise MigrationError(
                    f"Cannot change parent entity of '{name}' from "
                    f"'{old_snap.parent_entity}' to '{new_snap.parent_entity}'. "
                    "Drop and recreate the entity instead."
                )

            old_fields = old_snap.fields
            new_fields = new_snap.fields

            # New fields
            for fname in new_fields:
                if fname not in old_fields:
                    fsnap = new_fields[fname]
                    ref_table = _resolve_ref_table(fsnap.entity_ref, new_entities, old_entities)
                    ops.append(CreateFieldTables(
                        entity_name=name,
                        entity_table=new_snap.table_name,
                        field_name=fname,
                        sql_type=fsnap.sql_type,
                        relationship=fsnap.relationship,
                        entity_ref=fsnap.entity_ref,
                        ref_table=ref_table,
                    ))

            # Dropped fields
            for fname in old_fields:
                if fname not in new_fields:
                    ops.append(DropFieldTables(
                        entity_name=name,
                        entity_table=new_snap.table_name,
                        field_name=fname,
                    ))

            # Changed field types — forbidden
            for fname in new_fields:
                if fname in old_fields:
                    old_f = old_fields[fname]
                    new_f = new_fields[fname]
                    if old_f.sql_type != new_f.sql_type:
                        raise MigrationError(
                            f"Cannot change type of field '{name}.{fname}' "
                            f"from '{old_f.sql_type}' to '{new_f.sql_type}'. "
                            "Drop and recreate the field instead."
                        )
                    if old_f.relationship != new_f.relationship:
                        raise MigrationError(
                            f"Cannot change relationship type of '{name}.{fname}' "
                            f"from '{old_f.relationship}' to '{new_f.relationship}'."
                        )

        # ---- Dropped entities --------------------------------------------
        for name in dropped_names:
            snap = old_entities[name]
            # CASCADE on entity table also drops field tables
            ops.append(DropEntityTable(name, snap.table_name))

        return ops


def _resolve_ref_table(
    entity_ref: str | None,
    new_entities: dict,
    old_entities: dict,
) -> str | None:
    if entity_ref is None:
        return None
    snap = new_entities.get(entity_ref) or old_entities.get(entity_ref)
    if snap:
        return snap.table_name
    # Fall back: registry
    try:
        from bitemporalorm.registry import registry
        cls = registry.get(entity_ref)
        return cls._meta.table_name
    except Exception:
        return None
