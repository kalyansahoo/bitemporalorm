# Concepts

These pages explain the design decisions and internal mechanics of bitemporalorm.

---

## Overview

| Page | Summary |
|---|---|
| [Bitemporal Data](bitemporal.md) | What bitemporality means, valid time vs transaction time, how the two-table design captures both |
| [Entities & Fields](entities.md) | Entity definition, field relationship types, type annotations, single inheritance |
| [Table Structure](tables.md) | The audit table, the materialized table, indexes, and the exclusion constraint |
| [Saving Data](save.md) | How `.save()` appends to audit and incrementally updates the materialized table |
| [Querying](filter.md) | Point-in-time `filter()`, Polars expression translation, inherited field joins |
| [Migrations](migrations.md) | `make_migration`, `migrate`, all operations, forbidden changes |

---

## The core idea

Traditional databases record the *current* state of data. If you correct a record, the previous value is gone.

bitemporalorm stores **every version of every field value** with an explicit time range. Each field lives in its own pair of tables:

- **Audit table** — an immutable log of every event that was ever recorded.
- **Materialized table** — a maintained, non-overlapping view of "what was true at each point in time", derived from the audit log.

When you query with `Entity.filter(as_of=datetime(...))`, you ask: *"What did we know about this entity at exactly this moment in history?"* The answer is always available, even for times far in the past.
