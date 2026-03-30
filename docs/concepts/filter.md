# Querying

## The `.filter()` classmethod

```python
@classmethod
async def filter(cls, as_of: datetime, *exprs: pl.Expr) -> pl.DataFrame
```

Returns a Polars DataFrame containing the state of all entities (of this type) at the specified point in time.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `as_of` | `datetime` | The point in time to query. **Required.** |
| `*exprs` | `pl.Expr` | Optional Polars filter expressions for additional WHERE conditions |

### Returns

`pl.DataFrame` with columns:
- `entity_id` — the entity's primary key
- One column per declared field (own + inherited)

---

## The `as_of` parameter

`as_of` is a **point-in-time datetime** — not a range. It is translated to a PostgreSQL `@>` (contains) condition on the `as_of` column of each field table:

```sql
LEFT JOIN "business_entity_to_city" AS "f_city"
    ON "f_city".entity_id = e.id
   AND "f_city".as_of @> '2021-06-01T00:00:00+00:00'::timestamptz
```

Only one value is returned per entity per field — the one whose `as_of` range contains the query timestamp.

### Restriction: no range queries on `as_of`

`as_of` must be a single `datetime`. Range queries (`as_of > some_date`) are not supported. To get the state at multiple points in time, call `.filter()` multiple times.

```python
# Allowed
await BusinessEntity.filter(as_of=datetime(2021, 1, 1, tzinfo=timezone.utc))

# Not allowed — will raise TypeError at the Python level
await BusinessEntity.filter(as_of=(datetime(2020), datetime(2022)))  # ✗
```

---

## Additional Polars expressions

Pass any Polars expression as positional arguments after `as_of`. Multiple expressions are AND-combined.

```python
import polars as pl

# Single filter
await BusinessEntity.filter(
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
    pl.col("city") == "London",
)

# Multiple filters (AND)
await BusinessEntity.filter(
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
    pl.col("city") == "London",
    pl.col("head_count") > 10,
)
```

### Supported expressions

| Polars expression | SQL equivalent |
|---|---|
| `pl.col("city") == "London"` | `"f_city".value = 'London'` |
| `pl.col("count") > 10` | `"f_count".value > 10` |
| `pl.col("code").is_null()` | `"f_code".value IS NULL` |
| `pl.col("code").is_not_null()` | `"f_code".value IS NOT NULL` |
| `pl.col("status").is_in(["a", "b"])` | `"f_status".value IN ('a', 'b')` |
| `pl.col("count").is_between(5, 50)` | `"f_count".value BETWEEN 5 AND 50` |
| `pl.col("name").str.contains("Ltd")` | `"f_name".value LIKE '%Ltd%'` |
| `pl.col("name").str.starts_with("Acme")` | `"f_name".value LIKE 'Acme%'` |
| `pl.col("name").str.ends_with("Inc")` | `"f_name".value LIKE '%Inc'` |
| `expr1 & expr2` | `expr1 AND expr2` |
| `expr1 \| expr2` | `expr1 OR expr2` |
| `~expr` | `NOT expr` |

---

## Result shape for one-to-many fields

When an entity has a `OneToManyField` (e.g., `director`), the result is **exploded** — one row per `(entity, value)` combination. Other field columns are duplicated across these rows:

```python
df = await BusinessEntity.filter(
    as_of=datetime(2022, 1, 1, tzinfo=timezone.utc),
)
print(df)
# ┌───────────┬────────┬───────────────┬──────────────┐
# │ entity_id ┆ city   ┆ phone_number  ┆ director     │
# ╞═══════════╪════════╪═══════════════╪══════════════╡
# │ 1         ┆ London ┆ +44123456789  ┆ Alice Smith  │
# │ 1         ┆ London ┆ +44123456789  ┆ Bob Jones    │
# │ 2         ┆ Paris  ┆ +33987654321  ┆ Claire Dupont│
# └───────────┴────────┴───────────────┴──────────────┘
```

Entity 1 appears twice because it has two directors. To get unique entities, filter on `entity_id` or use Polars `.unique()` on the `entity_id` column.

---

## Inheritance — querying child entities

When called on a child entity class (`RegionalOffice`), `.filter()` returns own fields **and** all inherited parent fields in the same row:

```python
df = await RegionalOffice.filter(
    as_of=datetime(2022, 1, 1, tzinfo=timezone.utc),
)
print(df.columns)
# ["entity_id", "branch_code", "head_count", "city", "phone_number", "director"]
```

The generated SQL joins the hierarchy table and the parent entity's field tables:

```sql
SELECT e.id AS entity_id,
       "f_branch_code".value AS branch_code,
       "f_head_count".value  AS head_count,
       "f_city".value        AS city,
       "f_phone_number".value AS phone_number,
       "f_director".value    AS director
FROM "regional_office" AS e
LEFT JOIN "regional_office_to_parent_entity" AS cpe
    ON cpe.entity_id = e.id
   AND cpe.as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
LEFT JOIN "regional_office_to_branch_code" AS "f_branch_code"
    ON "f_branch_code".entity_id = e.id
   AND "f_branch_code".as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
LEFT JOIN "regional_office_to_head_count" AS "f_head_count"
    ON "f_head_count".entity_id = e.id
   AND "f_head_count".as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
LEFT JOIN "business_entity_to_city" AS "f_city"
    ON "f_city".entity_id = cpe.parent_entity_id
   AND "f_city".as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
LEFT JOIN "business_entity_to_phone_number" AS "f_phone_number"
    ON "f_phone_number".entity_id = cpe.parent_entity_id
   AND "f_phone_number".as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
LEFT JOIN "business_entity_to_director" AS "f_director"
    ON "f_director".entity_id = cpe.parent_entity_id
   AND "f_director".as_of @> '2022-01-01T00:00:00+00:00'::timestamptz
```

---

## Post-processing with Polars

`.filter()` returns a plain `pl.DataFrame`. Use any Polars operation after the call:

```python
df = await BusinessEntity.filter(
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
)

# Count directors per entity
director_counts = (
    df
    .group_by("entity_id")
    .agg(pl.col("director").count().alias("n_directors"))
)

# Unique entities only
unique_entities = df.unique("entity_id")

# Join with another DataFrame
merged = df.join(metadata_df, on="entity_id", how="left")
```
