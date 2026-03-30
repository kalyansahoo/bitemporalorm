# bitemporalorm

**Bitemporal data storage for PostgreSQL — with Polars DataFrames and Django-style migrations.**

bitemporalorm lets you define entities whose fields are tracked across time. Every change is stored with an explicit *valid-time range* (`as_of`), so you can query the state of your data at any point in history and retroactively correct past records — without ever losing the original audit trail.

---

<div class="feature-grid">
<div class="feature-card">
<h3>⏱ Bitemporal by design</h3>
Every field change is stored with a PostgreSQL <code>tstzrange</code>. Query the exact state of any entity at any moment in the past.
</div>
<div class="feature-card">
<h3>📊 Polars DataFrames</h3>
All reads and writes use Polars DataFrames. No ORM objects — just vectorised data you can transform directly.
</div>
<div class="feature-card">
<h3>🔄 Django-style migrations</h3>
<code>make_migration</code> diffs your models against history. <code>migrate</code> applies changes. Field type changes are forbidden — data integrity first.
</div>
<div class="feature-card">
<h3>🌲 Single inheritance</h3>
Extend entities via Python class inheritance. Child entities inherit all parent fields and join them transparently at query time.
</div>
</div>

---

## Quick example

```python
from bitemporalorm import Entity, ManyToOneField, OneToOneField, OneToManyField

class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]
```

```python
from datetime import datetime, timezone
import polars as pl

# Insert a new entity (no entity_id → auto-assigned)
df = await BusinessEntity.save(pl.DataFrame({
    "as_of_start":  [datetime(2020, 1, 1, tzinfo=timezone.utc)],
    "city":         ["London"],
    "phone_number": ["+44123456789"],
    "director":     ["Alice Smith"],
}))
entity_id = df["entity_id"][0]

# Retroactively move to Manchester from 2023
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [entity_id],
    "as_of_start": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Manchester"],
}))

# Point-in-time query — London is still the answer for 2021
result = await BusinessEntity.filter(
    as_of=datetime(2021, 6, 1, tzinfo=timezone.utc),
    pl.col("city") == "London",
)
# result is a pl.DataFrame with columns: entity_id, city, phone_number, director
```

---

## Install

```bash
uv add bitemporalorm
# or
pip install bitemporalorm
```

Requires Python 3.12+ and PostgreSQL 14+ (for `tstzrange` exclusion constraints).

---

## At a glance

| Concept | Summary |
|---|---|
| [Getting Started](getting-started.md) | Install, define a model, run migrations, first query |
| [Tutorial](tutorial.md) | End-to-end business registry with hierarchy |
| [Bitemporal Data](concepts/bitemporal.md) | What bitemporality means and why it matters |
| [Entities & Fields](concepts/entities.md) | Field types, type annotations, single inheritance |
| [Table Structure](concepts/tables.md) | Audit table, materialized table, indexes |
| [Saving Data](concepts/save.md) | How `.save()` updates the materialized table |
| [Querying](concepts/filter.md) | Point-in-time filter, Polars expressions, inheritance joins |
| [Migrations](concepts/migrations.md) | `make_migration`, `migrate`, operations, constraints |
