# Saving Data

## The `.save()` method

```python
@classmethod
async def save(cls, df: pl.DataFrame) -> pl.DataFrame
```

`.save()` accepts a Polars DataFrame and persists each row as a bitemporal event. It returns the same DataFrame with the `entity_id` column populated for all rows.

### Required columns

| Column | Type | Description |
|---|---|---|
| `as_of_start` | `datetime` | Start of the valid-time range |

### Optional columns

| Column | Type | Default | Description |
|---|---|---|---|
| `as_of_end` | `datetime` | `infinity` | End of the valid-time range (exclusive). Omit for open-ended records. |
| `entity_id` | `int` | `None` | Entity to update. Absent = insert new entity. |
| `<field_name>` | varies | — | Value for any declared field. Only fields present in the DataFrame are saved. |
| `parent_entity_id` | `int` | — | For child entities: links to the parent entity instance. |

---

## What happens on each `.save()` call

For every row in the DataFrame, `.save()`:

1. **Inserts a new entity** if `entity_id` is absent — `INSERT INTO entity_table DEFAULT VALUES RETURNING id`. The generated `id` is written back into the DataFrame.

2. **For each field column present in the row**:

   a. **Audit insert** — appends one row to `entity_to_<field>_audit`:

   ```sql
   INSERT INTO "business_entity_to_city_audit" (entity_id, value, as_of)
   VALUES ($1, $2, '[2023-01-01+00,infinity)'::tstzrange)
   ```

   b. **Materialized update** — incrementally updates `entity_to_<field>`:

---

## The materialized update algorithm

For a new event `(entity_id=X, value=V, range=[start, end))`:

**Step 1** — Find all existing rows that overlap with the new range:

```sql
SELECT lower(as_of) AS lo, upper(as_of) AS hi, value
FROM "business_entity_to_city"
WHERE entity_id = X AND as_of && '[start,end)'::tstzrange
```

**Step 2** — Delete those rows.

**Step 3** — Re-insert a **left remnant** if an existing row started before `start`:

```
existing:  [────────────────────────────────────)
new:               [──────────────────────────)
remnant:   [───────)
```

```sql
INSERT INTO "business_entity_to_city" (entity_id, value, as_of)
VALUES (X, old_value, '[old_lower, start)')
```

**Step 4** — Re-insert a **right remnant** if an existing row ended after `end` (only relevant when `end != infinity`):

```
existing:             [──────────────────────────────────)
new:       [──────────────────────────)
remnant:                              [──────────────────)
```

```sql
INSERT INTO "business_entity_to_city" (entity_id, value, as_of)
VALUES (X, old_value, '[end, old_upper)')
```

**Step 5** — Insert the new row:

```sql
INSERT INTO "business_entity_to_city" (entity_id, value, as_of)
VALUES (X, V, '[start, end)')
```

---

## Example: retroactive correction

Initial state (London, effective 2020 onward):

```
entity 1 city: [2020-01-01, ∞)  →  "London"
```

Save a correction: Bristol during 2021:

```python
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [1],
    "as_of_start": [datetime(2021, 1, 1, tzinfo=timezone.utc)],
    "as_of_end":   [datetime(2022, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Bristol"],
}))
```

The existing row `[2020, ∞)` overlaps the new range `[2021, 2022)`:

1. Delete `[2020, ∞) → London`.
2. Re-insert left remnant `[2020, 2021) → London`.
3. Re-insert right remnant `[2022, ∞) → London`.
4. Insert new row `[2021, 2022) → Bristol`.

Final state:

```
entity 1 city:
  [2020-01-01, 2021-01-01)  →  "London"
  [2021-01-01, 2022-01-01)  →  "Bristol"
  [2022-01-01, ∞)           →  "London"
```

---

## One-to-many fields

For `OneToManyField` (e.g., `director`), there is **no exclusion constraint** and no splitting logic. `.save()` simply appends a new row to the materialized table:

```python
# Two directors for entity 1
await BusinessEntity.save(pl.DataFrame({
    "as_of_start": [
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2020, 1, 1, tzinfo=timezone.utc),
    ],
    "director": ["Alice Smith", "Bob Jones"],
    # entity_id absent → inserts two rows but only creates ONE entity
    # (same entity_id is used for both rows)
}))
```

!!! note
    When saving a one-to-many field, use separate rows in the DataFrame for each value (exploded format). This matches the exploded format returned by `.filter()`.

---

## Partial updates

You only need to include the field columns you want to update. Unincluded fields are left unchanged:

```python
# Only update city — phone_number and director are untouched
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [entity_id],
    "as_of_start": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Manchester"],
}))
```
