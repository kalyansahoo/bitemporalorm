from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bitemporalorm.migration.state import MigrationState


class Operation(ABC):
    @abstractmethod
    def to_sql(self) -> str: ...

    @abstractmethod
    def apply_to_state(self, state: MigrationState) -> None: ...

    @abstractmethod
    def describe(self) -> str: ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.describe()})"


# ---------------------------------------------------------------------------
# CreateEntityTable
# ---------------------------------------------------------------------------


class CreateEntityTable(Operation):
    """CREATE TABLE for the entity's root table."""

    def __init__(self, entity_name: str, table_name: str) -> None:
        self.entity_name = entity_name
        self.table_name = table_name

    def to_sql(self) -> str:
        return (
            f'CREATE TABLE IF NOT EXISTS "{self.table_name}" (\n'
            f'    "id"         BIGSERIAL NOT NULL PRIMARY KEY,\n'
            f'    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()\n'
            f");"
        )

    def apply_to_state(self, state: MigrationState) -> None:
        from bitemporalorm.migration.state import EntitySnapshot

        state.entities[self.entity_name] = EntitySnapshot(
            name=self.entity_name,
            table_name=self.table_name,
        )

    def describe(self) -> str:
        return f"Create entity table '{self.table_name}'"


# ---------------------------------------------------------------------------
# DropEntityTable
# ---------------------------------------------------------------------------


class DropEntityTable(Operation):
    def __init__(self, entity_name: str, table_name: str) -> None:
        self.entity_name = entity_name
        self.table_name = table_name

    def to_sql(self) -> str:
        return f'DROP TABLE IF EXISTS "{self.table_name}" CASCADE;'

    def apply_to_state(self, state: MigrationState) -> None:
        state.entities.pop(self.entity_name, None)

    def describe(self) -> str:
        return f"Drop entity table '{self.table_name}'"


# ---------------------------------------------------------------------------
# CreateFieldTables
# ---------------------------------------------------------------------------


class CreateFieldTables(Operation):
    """
    Creates both the audit table and the materialized table for one field.
    Also creates all required indexes.
    """

    def __init__(
        self,
        entity_name: str,
        entity_table: str,
        field_name: str,
        sql_type: str,
        relationship: str,  # "many_to_one" | "one_to_one" | "one_to_many"
        entity_ref: str | None = None,
        ref_table: str | None = None,  # table name of entity_ref (if entity ref)
    ) -> None:
        self.entity_name = entity_name
        self.entity_table = entity_table
        self.field_name = field_name
        self.sql_type = sql_type
        self.relationship = relationship
        self.entity_ref = entity_ref
        self.ref_table = ref_table

    def _audit_table(self) -> str:
        return f"{self.entity_table}_to_{self.field_name}_audit"

    def _mat_table(self) -> str:
        return f"{self.entity_table}_to_{self.field_name}"

    def _value_col_ddl(self) -> str:
        fk_clause = ""
        if self.entity_ref and self.ref_table:
            fk_clause = f' REFERENCES "{self.ref_table}"("id")'
        return f'"value" {self.sql_type}{fk_clause}'

    def to_sql(self) -> str:
        audit_table = self._audit_table()
        mat_table = self._mat_table()
        val_col = self._value_col_ddl()

        # Exclusion constraint for many-to-one / one-to-one
        # (not for one-to-many — multiple values at same time are OK)
        excl = ""
        if self.relationship in ("many_to_one", "one_to_one"):
            excl = ',\n    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)'

        parts: list[str] = []

        # Audit table
        parts.append(
            f'CREATE TABLE IF NOT EXISTS "{audit_table}" (\n'
            f'    "id"         BIGSERIAL NOT NULL PRIMARY KEY,\n'
            f'    "entity_id"  BIGINT NOT NULL REFERENCES "{self.entity_table}"("id") ON DELETE CASCADE,\n'
            f"    {val_col},\n"
            f'    "as_of"      TSTZRANGE NOT NULL,\n'
            f'    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()\n'
            f");"
        )
        parts.append(f'CREATE INDEX IF NOT EXISTS ON "{audit_table}" ("entity_id");')
        parts.append(f'CREATE INDEX IF NOT EXISTS ON "{audit_table}" USING GIST ("as_of");')
        parts.append(
            f'CREATE INDEX IF NOT EXISTS ON "{audit_table}" USING GIST ("entity_id", "as_of");'
        )

        # Materialized table
        parts.append(
            f'CREATE TABLE IF NOT EXISTS "{mat_table}" (\n'
            f'    "entity_id" BIGINT NOT NULL REFERENCES "{self.entity_table}"("id") ON DELETE CASCADE,\n'
            f"    {val_col},\n"
            f'    "as_of"     TSTZRANGE NOT NULL{excl}\n'
            f");"
        )
        parts.append(f'CREATE INDEX IF NOT EXISTS ON "{mat_table}" ("entity_id");')
        parts.append(f'CREATE INDEX IF NOT EXISTS ON "{mat_table}" USING GIST ("as_of");')
        parts.append(
            f'CREATE INDEX IF NOT EXISTS ON "{mat_table}" USING GIST ("entity_id", "as_of");'
        )

        return "\n".join(parts)

    def apply_to_state(self, state: MigrationState) -> None:
        from bitemporalorm.migration.state import FieldSnapshot

        if self.entity_name not in state.entities:
            return
        snap = state.entities[self.entity_name]
        snap.fields[self.field_name] = FieldSnapshot(
            name=self.field_name,
            sql_type=self.sql_type,
            relationship=self.relationship,
            entity_ref=self.entity_ref,
        )

    def describe(self) -> str:
        return f"Create field tables '{self.entity_table}_to_{self.field_name}[_audit]'"


# ---------------------------------------------------------------------------
# DropFieldTables
# ---------------------------------------------------------------------------


class DropFieldTables(Operation):
    def __init__(self, entity_name: str, entity_table: str, field_name: str) -> None:
        self.entity_name = entity_name
        self.entity_table = entity_table
        self.field_name = field_name

    def to_sql(self) -> str:
        audit = f"{self.entity_table}_to_{self.field_name}_audit"
        mat = f"{self.entity_table}_to_{self.field_name}"
        return f'DROP TABLE IF EXISTS "{audit}" CASCADE;\nDROP TABLE IF EXISTS "{mat}" CASCADE;'

    def apply_to_state(self, state: MigrationState) -> None:
        if self.entity_name in state.entities:
            state.entities[self.entity_name].fields.pop(self.field_name, None)

    def describe(self) -> str:
        return f"Drop field tables '{self.entity_table}_to_{self.field_name}[_audit]'"


# ---------------------------------------------------------------------------
# CreateHierarchyTable
# ---------------------------------------------------------------------------


class CreateHierarchyTable(Operation):
    """CREATE TABLE child_to_parent_entity."""

    def __init__(
        self,
        entity_name: str,
        entity_table: str,
        parent_entity_name: str,
        parent_table: str,
    ) -> None:
        self.entity_name = entity_name
        self.entity_table = entity_table
        self.parent_entity_name = parent_entity_name
        self.parent_table = parent_table

    def _hier_table(self) -> str:
        return f"{self.entity_table}_to_parent_entity"

    def to_sql(self) -> str:
        hier = self._hier_table()
        return (
            f'CREATE TABLE IF NOT EXISTS "{hier}" (\n'
            f'    "entity_id"        BIGINT NOT NULL REFERENCES "{self.entity_table}"("id") ON DELETE CASCADE,\n'
            f'    "parent_entity_id" BIGINT NOT NULL REFERENCES "{self.parent_table}"("id"),\n'
            f'    "as_of"            TSTZRANGE NOT NULL,\n'
            f'    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)\n'
            f");\n"
            f'CREATE INDEX IF NOT EXISTS ON "{hier}" ("entity_id");\n'
            f'CREATE INDEX IF NOT EXISTS ON "{hier}" USING GIST ("as_of");'
        )

    def apply_to_state(self, state: MigrationState) -> None:
        if self.entity_name in state.entities:
            state.entities[self.entity_name].parent_entity = self.parent_entity_name

    def describe(self) -> str:
        return (
            f"Create hierarchy table '{self._hier_table()}' "
            f"({self.entity_name} → {self.parent_entity_name})"
        )


# ---------------------------------------------------------------------------
# DropHierarchyTable
# ---------------------------------------------------------------------------


class DropHierarchyTable(Operation):
    def __init__(self, entity_name: str, entity_table: str) -> None:
        self.entity_name = entity_name
        self.entity_table = entity_table

    def to_sql(self) -> str:
        return f'DROP TABLE IF EXISTS "{self.entity_table}_to_parent_entity" CASCADE;'

    def apply_to_state(self, state: MigrationState) -> None:
        if self.entity_name in state.entities:
            state.entities[self.entity_name].parent_entity = None

    def describe(self) -> str:
        return f"Drop hierarchy table '{self.entity_table}_to_parent_entity'"
