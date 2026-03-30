# Getting Started

Get bitemporalorm running in five minutes.

---

## Prerequisites

- Python 3.12+
- PostgreSQL 14+ (with the `btree_gist` extension for exclusion constraints)

Enable the extension once per database:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

---

## Install

=== "uv"

    ```bash
    uv add bitemporalorm
    ```

=== "pip"

    ```bash
    pip install bitemporalorm
    ```

---

## 1. Define a model

Create `models.py`:

```python
from bitemporalorm import Entity, ManyToOneField, OneToOneField, OneToManyField

class BusinessEntity(Entity):
    city:         ManyToOneField[str]   # many businesses can share the same city
    phone_number: OneToOneField[str]    # one number per entity at any time
    director:     OneToManyField[str]   # multiple directors → exploded rows
```

---

## 2. Generate a migration

```bash
bitemporalorm make_migration \
    --models models \
    --migrations-dir migrations
```

This diffs the current model state against the migration history and writes `migrations/0001_initial.py`.

---

## 3. Apply the migration

```bash
bitemporalorm migrate \
    --db-url "postgresql://postgres:secret@localhost:5432/mydb" \
    --models models
```

Creates the following tables in PostgreSQL:

```
business_entity
business_entity_to_city          business_entity_to_city_audit
business_entity_to_phone_number  business_entity_to_phone_number_audit
business_entity_to_director      business_entity_to_director_audit
```

Preview the SQL first with `--plan`:

```bash
bitemporalorm migrate --plan --db-url ...
```

---

## 4. Connect

```python
from bitemporalorm import ConnectionConfig, DBExecutor, register_executor

config = ConnectionConfig(
    host="localhost",
    port=5432,
    database="mydb",
    user="postgres",
    password="secret",
)

executor = DBExecutor(config)
register_executor(executor)
await executor.connect()
```

---

## 5. Save your first entity

```python
from datetime import datetime, timezone
import polars as pl

df = await BusinessEntity.save(pl.DataFrame({
    "as_of_start":  [datetime(2020, 1, 1, tzinfo=timezone.utc)],
    "city":         ["London"],
    "phone_number": ["+44123456789"],
    "director":     ["Alice Smith"],
}))

entity_id = df["entity_id"][0]
print(f"Created entity id={entity_id}")
```

---

## 6. Query

```python
result = await BusinessEntity.filter(
    as_of=datetime(2021, 6, 1, tzinfo=timezone.utc),
)
print(result)
# shape: (1, 4)
# ┌───────────┬────────┬───────────────┬─────────────┐
# │ entity_id ┆ city   ┆ phone_number  ┆ director    │
# │ i64       ┆ str    ┆ str           ┆ str         │
# ╞═══════════╪════════╪═══════════════╪═════════════╡
# │ 1         ┆ London ┆ +44123456789  ┆ Alice Smith │
# └───────────┴────────┴───────────────┴─────────────┘
```

---

## Next steps

- [Tutorial](tutorial.md) — build a complete business registry with inheritance
- [Concepts: Bitemporal Data](concepts/bitemporal.md) — understand the data model
- [Concepts: Saving Data](concepts/save.md) — how retroactive updates work
