# Bitemporal Data

## What is bitemporality?

Most databases record only the *current* state of data. If a company moves from London to Manchester, you update the row and London is gone. This is fine for simple use cases but fails whenever you need to answer questions like:

- "What city was this entity in on 1 Jan 2022?"
- "When did we first learn that Alice was a director?"
- "What was the full state of this entity three years ago?"

**Bitemporality** addresses this by tracking two independent time dimensions for every piece of data:

| Dimension | Question answered | In bitemporalorm |
|---|---|---|
| **Valid time** | When was this fact true in the real world? | The `as_of` column (`tstzrange`) |
| **Transaction time** | When did we record this fact in the database? | The `created_at` column in the audit table |

bitemporalorm makes the valid time dimension explicit on every field. Transaction time is always available via the audit table.

---

## Valid time ranges

Every field value is associated with a half-open interval `[start, end)`:

<div class="timeline">
time ──────────────────────────────────────────────────────────►
        [2018-01-01, 2023-01-01)           [2023-01-01, ∞)
        city = "London"                    city = "Manchester"
</div>

This means:
- From 2018-01-01 onwards, the city was London.
- From 2023-01-01 onwards, the city is Manchester.
- Querying with `as_of=datetime(2021, 6, 1)` returns London.
- Querying with `as_of=datetime(2023, 6, 1)` returns Manchester.

The end of infinity is stored as PostgreSQL's `'infinity'` timestamp.

---

## Retroactive corrections

Because valid time is explicit, you can record facts about the past at any time. If you discover that the company was actually in Bristol during 2019 (not London), you can save:

```python
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [entity_id],
    "as_of_start": [datetime(2019, 1, 1, tzinfo=timezone.utc)],
    "as_of_end":   [datetime(2020, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Bristol"],
}))
```

The materialized table is updated to reflect this correction:

<div class="timeline">
time ──────────────────────────────────────────────────────────►
  [2018-01-01, 2019-01-01)  [2019-01-01, 2020-01-01)  [2020-01-01, 2023-01-01)  [2023-01-01, ∞)
  city = "London"           city = "Bristol"           city = "London"           city = "Manchester"
</div>

The original audit record (London, covering the full 2018–2023 range) is still in the `_audit` table — it was never modified.

---

## The two-table design

bitemporalorm uses two tables per field to cleanly separate these concerns:

### Audit table (`entity_to_<field>_audit`)

- **Append-only.** Rows are never updated or deleted.
- Records every event exactly as submitted: the value, the claimed valid-time range, and when we recorded it (`created_at`).
- This is the source of truth for transaction time queries: "what did we believe at time T?"

### Materialized table (`entity_to_<field>`)

- **Maintained.** Updated on every `.save()` call.
- Contains non-overlapping `tstzrange` rows that together represent the complete valid-time history for each entity.
- Enforces an exclusion constraint (no two rows for the same entity may have overlapping `as_of` ranges) for `ManyToOneField` and `OneToOneField`.
- This is what `.filter(as_of=...)` queries — it is optimised for point-in-time lookups via GiST indexes.

---

## Why PostgreSQL `tstzrange`?

PostgreSQL's range types provide:

- **`@>` (contains)** — `as_of @> '2021-06-01'::timestamptz` — O(1) with a GiST index.
- **`&&` (overlaps)** — used internally to find existing rows to split on update.
- **`EXCLUDE USING GIST`** — a database-enforced constraint that prevents overlapping valid-time ranges for the same entity (for 1:1 and M:1 fields).
- **`'infinity'` timestamp** — a first-class value in PostgreSQL, so open-ended ranges are handled natively.
