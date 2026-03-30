# Entity

## class `Entity`

Base class for all bitemporal entities. Subclass it and declare fields as type annotations.

```python
from bitemporalorm import Entity, ManyToOneField, OneToOneField, OneToManyField

class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]
```

---

### `Entity.save()` — persist events

```python
@classmethod
async def save(cls, df: pl.DataFrame) -> pl.DataFrame
```

Persists a DataFrame of bitemporal events. For each row, inserts into the audit table and updates the materialized table. Returns the DataFrame with `entity_id` populated.

**Required columns**

| Column | Type | Description |
|---|---|---|
| `as_of_start` | `datetime` | Start of the valid-time range |

**Optional columns**

| Column | Type | Default | Description |
|---|---|---|---|
| `as_of_end` | `datetime` | `infinity` | End of the valid-time range (exclusive) |
| `entity_id` | `int` | `None` | Entity to update. Absent = insert new entity. |
| `parent_entity_id` | `int` | — | For child entities: ID of the parent entity instance |
| `<field_name>` | varies | — | Any declared field. Only fields present in df are saved. |

**Returns** — `pl.DataFrame` with `entity_id` populated for all rows.

```python
# Insert (entity_id absent → auto-assigned)
df = await BusinessEntity.save(pl.DataFrame({
    "as_of_start":  [datetime(2020, 1, 1, tzinfo=timezone.utc)],
    "city":         ["London"],
    "phone_number": ["+44123456789"],
    "director":     ["Alice Smith"],
}))
entity_id = df["entity_id"][0]

# Update (provide entity_id)
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [entity_id],
    "as_of_start": [datetime(2023, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Manchester"],
}))

# Bounded range (e.g. temporary change)
await BusinessEntity.save(pl.DataFrame({
    "entity_id":   [entity_id],
    "as_of_start": [datetime(2021, 1, 1, tzinfo=timezone.utc)],
    "as_of_end":   [datetime(2022, 1, 1, tzinfo=timezone.utc)],
    "city":        ["Bristol"],
}))
```

---

### `Entity.filter()` — point-in-time query

```python
@classmethod
async def filter(cls, as_of: datetime, *exprs: pl.Expr) -> pl.DataFrame
```

Returns a Polars DataFrame with the state of all entities at `as_of`.

**Parameters**

| Parameter | Type | Description |
|---|---|---|
| `as_of` | `datetime` | Point-in-time to query. Required. |
| `*exprs` | `pl.Expr` | Additional Polars filter expressions (AND-combined) |

**Returns** — `pl.DataFrame` with columns `entity_id` + one column per declared field (own + inherited for child entities).

For `OneToManyField`: one row per `(entity, value)` combination (exploded).

```python
# All entities as of a date
df = await BusinessEntity.filter(
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
)

# With Polars expression filters
df = await BusinessEntity.filter(
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
    pl.col("city") == "London",
    pl.col("director").is_not_null(),
)
```

---

## class `EntityOptions`

Attached to every `Entity` subclass as `cls._meta`. Do not instantiate directly.

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `table_name` | `str` | Database table name |
| `fields` | `dict[str, FieldSpec]` | Own fields only (not inherited) |
| `parent_entity` | `type[Entity] \| None` | Direct parent entity class |

### Methods

| Method | Returns | Description |
|---|---|---|
| `all_fields()` | `dict[str, FieldSpec]` | Own fields + all inherited fields (flattened) |
| `hierarchy()` | `list[type[Entity]]` | `[parent, grandparent, ...]` walking up the chain |

```python
RegionalOffice._meta.table_name    # "regional_office"
RegionalOffice._meta.fields        # {"branch_code": ..., "head_count": ...}
RegionalOffice._meta.all_fields()  # {"city": ..., "phone_number": ..., "director": ...,
                                   #  "branch_code": ..., "head_count": ...}
RegionalOffice._meta.parent_entity # BusinessEntity
RegionalOffice._meta.hierarchy()   # [BusinessEntity]
```

---

## class `EntityRegistry`

Global singleton registry. Available as `bitemporalorm.registry`.

| Method | Description |
|---|---|
| `register(entity)` | Register a class (called automatically by `EntityMeta`) |
| `get(name: str)` | Look up by class name. Raises `LookupError` if not found. |
| `all()` | Return all registered classes |
| `clear()` | Remove all registrations (useful in tests) |
| `snapshot()` | Return a copy of the current registry dict |
| `restore(snap)` | Restore registry from a snapshot |

```python
from bitemporalorm import registry

registry.get("BusinessEntity")   # → BusinessEntity class
registry.all()                   # → [BusinessEntity, RegionalOffice, ...]
```
