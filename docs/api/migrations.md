# Migrations

## Operations

All operation classes are importable from `bitemporalorm.migration.ops`.

```python
from bitemporalorm.migration.ops import (
    CreateEntityTable,
    DropEntityTable,
    CreateFieldTables,
    DropFieldTables,
    CreateHierarchyTable,
    DropHierarchyTable,
)
```

Each operation implements three methods:

| Method | Returns | Description |
|---|---|---|
| `to_sql()` | `str` | DDL statement to execute |
| `apply_to_state(state)` | `None` | Mutates a `MigrationState` in memory |
| `describe()` | `str` | Human-readable summary (printed by CLI) |

---

### `CreateEntityTable`

Creates the root entity table (`id`, `created_at`).

```python
CreateEntityTable(entity_name: str, table_name: str)
```

| Parameter | Description |
|---|---|
| `entity_name` | Python class name (e.g. `"BusinessEntity"`) |
| `table_name` | SQL table name (e.g. `"business_entity"`) |

**SQL produced:**

```sql
CREATE TABLE "business_entity" (
    "id"         BIGSERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### `DropEntityTable`

Drops the entity table with `CASCADE`, which also drops all dependent field tables.

```python
DropEntityTable(entity_name: str, table_name: str)
```

**SQL produced:**

```sql
DROP TABLE IF EXISTS "business_entity" CASCADE;
```

!!! warning
    Irreversible. All data for this entity and all its fields is permanently deleted.

---

### `CreateFieldTables`

Creates both the audit and materialized tables for a single field, including all GiST indexes and (for `many_to_one` / `one_to_one`) the exclusion constraint.

```python
CreateFieldTables(
    entity_name:  str,
    entity_table: str,
    field_name:   str,
    sql_type:     str,
    relationship: str,
    entity_ref:   str | None = None,
    ref_table:    str | None = None,
)
```

| Parameter | Description |
|---|---|
| `entity_name` | Python class name |
| `entity_table` | SQL table name of the owning entity |
| `field_name` | Field name (e.g. `"city"`) |
| `sql_type` | SQL column type string (`"TEXT"`, `"BIGINT"`, etc.) |
| `relationship` | `"many_to_one"`, `"one_to_one"`, or `"one_to_many"` |
| `entity_ref` | Referenced entity class name (entity-reference fields only) |
| `ref_table` | Referenced entity's table name (entity-reference fields only) |

**Example — primitive field:**

```python
CreateFieldTables(
    entity_name="BusinessEntity",
    entity_table="business_entity",
    field_name="city",
    sql_type="TEXT",
    relationship="many_to_one",
)
```

**Example — entity-reference field:**

```python
CreateFieldTables(
    entity_name="RegionalOffice",
    entity_table="regional_office",
    field_name="headquarters",
    sql_type="BIGINT",
    relationship="many_to_one",
    entity_ref="BusinessEntity",
    ref_table="business_entity",
)
```

**SQL produced (materialized table, `many_to_one`):**

```sql
CREATE TABLE "business_entity_to_city" (
    "entity_id" BIGINT NOT NULL REFERENCES "business_entity"("id") ON DELETE CASCADE,
    "value"     TEXT,
    "as_of"     TSTZRANGE NOT NULL,
    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)
);
CREATE INDEX ON "business_entity_to_city" ("entity_id");
CREATE INDEX ON "business_entity_to_city" USING GIST ("as_of");
CREATE INDEX ON "business_entity_to_city" USING GIST ("entity_id", "as_of");
```

The exclusion constraint is **omitted** for `one_to_many` fields (multiple simultaneous values are allowed).

---

### `DropFieldTables`

Drops both the audit and materialized tables for a field.

```python
DropFieldTables(
    entity_name:  str,
    entity_table: str,
    field_name:   str,
)
```

**SQL produced:**

```sql
DROP TABLE IF EXISTS "business_entity_to_city_audit";
DROP TABLE IF EXISTS "business_entity_to_city";
```

---

### `CreateHierarchyTable`

Creates the `child_to_parent_entity` link table for a child entity.

```python
CreateHierarchyTable(
    entity_name:        str,
    entity_table:       str,
    parent_entity_name: str,
    parent_table:       str,
)
```

| Parameter | Description |
|---|---|
| `entity_name` | Child entity class name |
| `entity_table` | Child entity table name |
| `parent_entity_name` | Parent entity class name |
| `parent_table` | Parent entity table name |

**SQL produced:**

```sql
CREATE TABLE "regional_office_to_parent_entity" (
    "entity_id"        BIGINT NOT NULL REFERENCES "regional_office"("id") ON DELETE CASCADE,
    "parent_entity_id" BIGINT NOT NULL REFERENCES "business_entity"("id"),
    "as_of"            TSTZRANGE NOT NULL,
    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)
);
CREATE INDEX ON "regional_office_to_parent_entity" ("entity_id");
CREATE INDEX ON "regional_office_to_parent_entity" USING GIST ("as_of");
```

---

### `DropHierarchyTable`

Drops the hierarchy link table.

```python
DropHierarchyTable(entity_name: str, entity_table: str)
```

**SQL produced:**

```sql
DROP TABLE IF EXISTS "regional_office_to_parent_entity";
```

---

## `MigrationState`

Snapshot of the full schema at a point in time. Used by `SchemaDiffer` to compute diffs.

```python
from bitemporalorm.migration.state import MigrationState, EntitySnapshot, FieldSnapshot
```

### `MigrationState`

```python
@dataclass
class MigrationState:
    entities: dict[str, EntitySnapshot]
```

#### Class methods

```python
MigrationState.from_registry() -> MigrationState
```

Builds the current state from all registered entity classes.

```python
MigrationState.from_migration_history(
    migration_dir: str | Path,
) -> MigrationState
```

Replays all migration files in `migration_dir` (topological order) to reconstruct the previously-applied state.

---

### `EntitySnapshot`

```python
@dataclass
class EntitySnapshot:
    entity_name:   str
    table_name:    str
    parent_entity: str | None
    fields:        dict[str, FieldSnapshot]
```

---

### `FieldSnapshot`

```python
@dataclass
class FieldSnapshot:
    field_name:    str
    sql_type:      str
    relationship:  str
    entity_ref:    str | None
```

---

## `SchemaDiffer`

Computes the list of operations needed to go from one `MigrationState` to another.

```python
from bitemporalorm.migration.differ import SchemaDiffer, MigrationError

ops = SchemaDiffer.diff(old_state, new_state)
```

### `SchemaDiffer.diff(old, new)`

```python
@staticmethod
def diff(old: MigrationState, new: MigrationState) -> list[Operation]
```

Returns an ordered list of operations. Raises `MigrationError` for forbidden changes.

**Forbidden changes (raise `MigrationError`):**

| Change | Error message |
|---|---|
| Field SQL type changed | `Cannot change type of field 'Entity.field'` |
| Field relationship type changed | `Cannot change relationship type of 'Entity.field'` |
| Entity parent class changed | `Cannot change parent entity of 'Entity'` |

To make a forbidden change, drop the field/entity and recreate it.

---

## `MigrationRunner`

Applies pending migrations to a live database.

```python
from bitemporalorm.migration.runner import MigrationRunner

runner = MigrationRunner(pool=pool, migration_dir="migrations")
await runner.run()
```

### Constructor

```python
MigrationRunner(pool: AsyncPool, migration_dir: str | Path)
```

### Methods

| Method | Description |
|---|---|
| `await run(fake=False)` | Apply all pending migrations. `fake=True` records them without executing SQL. |
| `await plan()` | Return the SQL that `run()` would execute, without touching the database. |
| `await ensure_tracking_table()` | Create `_bitemporalorm_migrations` if it does not exist. Called automatically by `run()`. |

The tracking table `_bitemporalorm_migrations` records the name of each applied migration:

```sql
CREATE TABLE IF NOT EXISTS _bitemporalorm_migrations (
    name       TEXT NOT NULL PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## `MigrationError`

```python
from bitemporalorm.migration.differ import MigrationError
```

Raised by `SchemaDiffer.diff()` when a forbidden schema change is detected.

```python
try:
    ops = SchemaDiffer.diff(old_state, new_state)
except MigrationError as e:
    print(e)
# Cannot change type of field 'BusinessEntity.score'
```
