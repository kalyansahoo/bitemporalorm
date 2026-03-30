# Migrations

bitemporalorm ships a Django-style migration system that tracks schema changes as versioned Python files. Run `make_migration` when your models change; run `migrate` to apply pending changes to the database.

---

## `make_migration`

```bash
bitemporalorm make_migration [NAME] [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `NAME` | `auto` | Migration name (auto-derived from first operation if omitted) |
| `--models` / `-m` | `models` | Python module path to import (e.g. `myapp.models`) |
| `--migrations-dir` / `-d` | `migrations` | Directory to read/write migration files |

### What it does

1. Imports your models module so all entities register themselves.
2. Builds `MigrationState.from_registry()` — the current model state.
3. Builds `MigrationState.from_migration_history()` — replays existing migration files to get the previous state.
4. Diffs the two states with `SchemaDiffer`.
5. Writes a new numbered `.py` file if there are changes; exits cleanly if there are none.

```bash
bitemporalorm make_migration --models myapp.models
# Created migrations/0001_initial.py
#   • Create entity table 'business_entity'
#   • Create field tables 'business_entity_to_city[_audit]'
#   • Create field tables 'business_entity_to_phone_number[_audit]'
#   • Create field tables 'business_entity_to_director[_audit]'
```

---

## `migrate`

```bash
bitemporalorm migrate [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--db-url` | `$DATABASE_URL` | PostgreSQL DSN |
| `--models` / `-m` | `models` | Python module path to import |
| `--migrations-dir` / `-d` | `migrations` | Directory to read migration files from |
| `--plan` | `False` | Print SQL without executing |
| `--fake` | `False` | Mark as applied without running SQL |

### What it does

1. Ensures the `_bitemporalorm_migrations` tracking table exists.
2. Loads all migration files from `--migrations-dir` in topological order.
3. Filters to only unapplied migrations (not in `_bitemporalorm_migrations`).
4. Applies each pending migration and records its name.

```bash
bitemporalorm migrate --db-url "postgresql://postgres:secret@localhost/mydb"
# Applying 0001_initial ... OK
```

### Preview with `--plan`

```bash
bitemporalorm migrate --plan --db-url ...
```

Prints the SQL that would run, without touching the database.

### Fake migrations

```bash
bitemporalorm migrate --fake --db-url ...
```

Marks migrations as applied without executing SQL. Useful when you've created tables manually and want to sync the migration history.

---

## Migration file anatomy

```python
# migrations/0002_add_industry_to_business_entity.py

dependencies = ["0001_initial"]

operations = [
    CreateFieldTables(
        entity_name="BusinessEntity",
        entity_table="business_entity",
        field_name="industry",
        sql_type="TEXT",
        relationship="many_to_one",
    ),
]
```

| Section | Description |
|---|---|
| `dependencies` | Migration names that must be applied first |
| `operations` | Ordered list of `Operation` instances |

---

## Available operations

### `CreateEntityTable`

Creates the root entity table (`id`, `created_at`).

```python
CreateEntityTable(entity_name="BusinessEntity", table_name="business_entity")
```

---

### `DropEntityTable`

Drops the entity table (with `CASCADE` — also drops all dependent field tables).

```python
DropEntityTable(entity_name="BusinessEntity", table_name="business_entity")
```

!!! warning
    Irreversible. All data for this entity and all its fields is permanently deleted.

---

### `CreateFieldTables`

Creates both the audit and materialized tables for one field, with all indexes.

```python
CreateFieldTables(
    entity_name="BusinessEntity",
    entity_table="business_entity",
    field_name="city",
    sql_type="TEXT",
    relationship="many_to_one",   # or "one_to_one" / "one_to_many"
)
```

For entity-reference fields, also pass:

```python
CreateFieldTables(
    ...
    entity_ref="Country",         # referenced entity class name
    ref_table="country",          # referenced entity's table name
)
```

---

### `DropFieldTables`

Drops both the audit and materialized tables for one field.

```python
DropFieldTables(
    entity_name="BusinessEntity",
    entity_table="business_entity",
    field_name="city",
)
```

---

### `CreateHierarchyTable`

Creates the `child_to_parent_entity` link table.

```python
CreateHierarchyTable(
    entity_name="RegionalOffice",
    entity_table="regional_office",
    parent_entity_name="BusinessEntity",
    parent_table="business_entity",
)
```

---

### `DropHierarchyTable`

Drops the hierarchy link table.

```python
DropHierarchyTable(
    entity_name="RegionalOffice",
    entity_table="regional_office",
)
```

---

## Forbidden schema changes

The following changes raise `MigrationError` in `SchemaDiffer` and must be resolved manually:

| Change | Error |
|---|---|
| Change a field's SQL type | `Cannot change type of field 'Entity.field'` |
| Change a field's relationship type | `Cannot change relationship type of 'Entity.field'` |
| Change an entity's parent class | `Cannot change parent entity of 'Entity'` |

To make these changes, drop the field/entity and recreate it:

```bash
# 1. Remove the field from the model and run make_migration → DropFieldTables
# 2. Add the field back with the new type and run make_migration → CreateFieldTables
```

---

## Dependency resolution

The migration loader uses Kahn's algorithm (topological sort) on the `dependencies` graph. Migrations can be applied in any dependency-valid order, which supports parallel feature branches:

```
0001_initial
     │
     ├── 0002_add_industry       (feature/industry)
     └── 0003_add_regional_office (feature/offices)
              │
              └── 0004_add_office_capacity
```

All four can coexist. The loader resolves the correct application order regardless of filename sort.
