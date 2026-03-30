# Tutorial — Business Registry

Build a complete business registry that tracks companies and their regional offices over time. You will:

1. Define entities with all three field relationship types
2. Use single inheritance (`RegionalOffice` extends `BusinessEntity`)
3. Insert, update, and retroactively correct data
4. Query point-in-time snapshots and filter by field values
5. Add a new field via a second migration

---

## Step 1 — Project setup

```bash
mkdir business_registry && cd business_registry
uv init
uv add bitemporalorm
```

Enable the PostgreSQL extension (once per database):

```sql
CREATE DATABASE business_registry;
\c business_registry
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

---

## Step 2 — Define models

```python title="models.py"
from bitemporalorm import Entity, ManyToOneField, OneToOneField, OneToManyField


class BusinessEntity(Entity):
    """A legal business entity.

    Fields:
      city         — the city the entity is based in (many businesses per city)
      phone_number — main contact number (one per entity at any time)
      director     — board directors (one-to-many → exploded rows in query results)
    """
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]


class RegionalOffice(BusinessEntity):
    """A regional office that belongs to a parent BusinessEntity.

    Inherits: city, phone_number, director (from BusinessEntity)
    Adds:     branch_code, head_count

    The parent-child link is stored bitemporally in:
      regional_office_to_parent_entity
    """
    branch_code: OneToOneField[str]
    head_count:  ManyToOneField[int]
```

---

## Step 3 — Create and apply the initial migration

```bash
bitemporalorm make_migration --models models
bitemporalorm migrate --db-url "postgresql://postgres:secret@localhost:5432/business_registry" --models models
```

Tables created:

```
business_entity
  business_entity_to_city[_audit]
  business_entity_to_phone_number[_audit]
  business_entity_to_director[_audit]

regional_office
  regional_office_to_branch_code[_audit]
  regional_office_to_head_count[_audit]
  regional_office_to_parent_entity          ← hierarchy link
```

---

## Step 4 — Connect and insert data

```python title="main.py"
import asyncio
from datetime import datetime, timezone
import polars as pl
from bitemporalorm import ConnectionConfig, DBExecutor, register_executor
from models import BusinessEntity, RegionalOffice

async def main():
    config = ConnectionConfig(
        host="localhost", port=5432,
        database="business_registry",
        user="postgres", password="secret",
    )
    executor = DBExecutor(config)
    register_executor(executor)
    await executor.connect()

    # ── Insert HQ BusinessEntity ─────────────────────────────────────────────
    # Two rows because Alice and Bob are both directors (one-to-many → exploded)
    hq_df = await BusinessEntity.save(pl.DataFrame({
        "as_of_start":  [
            datetime(2018, 1, 1, tzinfo=timezone.utc),
            datetime(2018, 1, 1, tzinfo=timezone.utc),
        ],
        "city":         ["London",        "London"],
        "phone_number": ["+44123456789",  "+44123456789"],
        "director":     ["Alice Smith",   "Bob Jones"],
    }))
    hq_id = hq_df["entity_id"][0]
    print(f"HQ id={hq_id}")

    # ── Insert a second BusinessEntity ────────────────────────────────────────
    paris_df = await BusinessEntity.save(pl.DataFrame({
        "as_of_start":  [datetime(2019, 6, 1, tzinfo=timezone.utc)],
        "city":         ["Paris"],
        "phone_number": ["+33987654321"],
        "director":     ["Claire Dupont"],
    }))
    paris_id = paris_df["entity_id"][0]
    print(f"Paris entity id={paris_id}")

    # ── Insert a RegionalOffice child linked to HQ ────────────────────────────
    office_df = await RegionalOffice.save(pl.DataFrame({
        "as_of_start":      [datetime(2020, 3, 1, tzinfo=timezone.utc)],
        "branch_code":      ["LON-001"],
        "head_count":       [42],
        "parent_entity_id": [hq_id],
    }))
    office_id = office_df["entity_id"][0]
    print(f"RegionalOffice id={office_id}")

    await executor.disconnect()

asyncio.run(main())
```

---

## Step 5 — Point-in-time queries

```python
# All BusinessEntities as of 2020-01-01
df = await BusinessEntity.filter(
    as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
)
print(df)
# ┌───────────┬────────┬───────────────┬──────────────┐
# │ entity_id ┆ city   ┆ phone_number  ┆ director     │
# ╞═══════════╪════════╪═══════════════╪══════════════╡
# │ 1         ┆ London ┆ +44123456789  ┆ Alice Smith  │
# │ 1         ┆ London ┆ +44123456789  ┆ Bob Jones    │  ← exploded 1:M
# └───────────┴────────┴───────────────┴──────────────┘

# Filter by city
london = await BusinessEntity.filter(
    as_of=datetime(2020, 1, 1, tzinfo=timezone.utc),
    pl.col("city") == "London",
)

# RegionalOffice merges own fields + inherited parent fields
office_df = await RegionalOffice.filter(
    as_of=datetime(2021, 1, 1, tzinfo=timezone.utc),
)
# Columns: entity_id, branch_code, head_count, city, phone_number, director
print(office_df.columns)
```

---

## Step 6 — Retroactive updates

Move the HQ to Manchester, effective 2023-01-01:

```python
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [hq_id],
    "as_of_start": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Manchester"],
}))
```

The original London record is preserved in the audit table and in the materialized table for all times before 2023-01-01:

```python
# Still London before the change
before = await BusinessEntity.filter(
    as_of=datetime(2022, 12, 31, tzinfo=timezone.utc),
    pl.col("entity_id") == hq_id,
)
# → city = "London"

# Manchester after the change
after = await BusinessEntity.filter(
    as_of=datetime(2023, 6, 1, tzinfo=timezone.utc),
    pl.col("entity_id") == hq_id,
)
# → city = "Manchester"
```

Because `RegionalOffice` joins the parent entity's field tables at query time, the regional office automatically reflects the change too:

```python
office_2023 = await RegionalOffice.filter(
    as_of=datetime(2023, 6, 1, tzinfo=timezone.utc),
)
# → city = "Manchester"  (inherited from the updated HQ)
```

---

## Step 7 — Add a new field

Add `industry` to `BusinessEntity`:

```python title="models.py"
class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]
    industry:     ManyToOneField[str]   # ← new
```

Generate and apply the migration:

```bash
bitemporalorm make_migration --models models
# Created migrations/0002_create_field_tables_business_entity_to_industry_audit_.py

bitemporalorm migrate --db-url "postgresql://..." --models models
# Applying 0002_... OK
```

The new migration creates `business_entity_to_industry` and `business_entity_to_industry_audit`. Existing entities simply have no `industry` value until you save one.

---

## Step 8 — Dropping a field

Remove `industry` from the model. `make_migration` generates a `DropFieldTables` operation:

```bash
bitemporalorm make_migration --models models
# • Drop field tables 'business_entity_to_industry[_audit]'
```

!!! warning
    `DropFieldTables` drops both the materialized and audit tables. All historical data for that field is permanently lost. Preview with `--plan` before applying.

---

## What's next

- [Concepts: Bitemporal Data](concepts/bitemporal.md) — deeper understanding of valid time and the audit/materialized split
- [Concepts: Saving Data](concepts/save.md) — exactly what happens to the materialized table on every save
- [API Reference: Entity](api/entity.md) — full `save()` and `filter()` signatures
