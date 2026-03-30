# Fields

## `ManyToOneField`

```python
from bitemporalorm import ManyToOneField
```

Many entities can share the same value; each entity has one value at any given time.

```python
class BusinessEntity(Entity):
    city: ManyToOneField[str]
    score: ManyToOneField[int]
```

- Exclusion constraint: **enforced** — no two rows for the same entity with overlapping `as_of`
- Relationship type: `"many_to_one"`

---

## `OneToOneField`

```python
from bitemporalorm import OneToOneField
```

Exactly one value per entity at any given time; semantically stricter than `ManyToOneField`.

```python
class BusinessEntity(Entity):
    phone_number: OneToOneField[str]
    registration_number: OneToOneField[str]
```

- Exclusion constraint: **enforced**
- Relationship type: `"one_to_one"`

---

## `OneToManyField`

```python
from bitemporalorm import OneToManyField
```

Multiple values per entity at the same time. Query results are exploded (one row per value).

```python
class BusinessEntity(Entity):
    director: OneToManyField[str]
    tag: OneToManyField[str]
```

- Exclusion constraint: **not enforced** — multiple simultaneous values allowed
- Relationship type: `"one_to_many"`

---

## Annotation syntax

### Class-getitem (recommended)

```python
city: ManyToOneField[str]            # primitive
country: ManyToOneField["Country"]   # entity reference (string forward ref)
```

### Direct instantiation

```python
city: ManyToOneField = ManyToOneField(str)
```

---

## Type argument mapping

| Python type | SQL column type |
|---|---|
| `str` | `TEXT` |
| `int` | `BIGINT` |
| `float` | `DOUBLE PRECISION` |
| `datetime.datetime` | `TIMESTAMPTZ` |
| `"EntityName"` (string) | `BIGINT` (FK to entity table) |
| `EntityClass` (direct ref) | `BIGINT` (FK to entity table) |

---

## `FieldType` enum

```python
from bitemporalorm import FieldType
```

| Member | SQL type |
|---|---|
| `FieldType.TEXT` | `TEXT` |
| `FieldType.INT` | `BIGINT` |
| `FieldType.FLOAT` | `DOUBLE PRECISION` |
| `FieldType.DATETIME` | `TIMESTAMPTZ` |
| `FieldType.ENTITY_REF` | `BIGINT` |

---

## class `FieldSpec`

Resolved field metadata attached to `EntityOptions.fields`. Read-only.

```python
fspec = BusinessEntity._meta.fields["city"]

fspec.name          # "city"
fspec.relationship  # RelationshipType.MANY_TO_ONE
fspec.sql_type      # FieldType.TEXT
fspec.sql_type_str  # "TEXT"
fspec.entity_ref    # None  (or "Country" for entity-reference fields)
```

### Attributes

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Field name (matches annotation key) |
| `relationship` | `RelationshipType` | `MANY_TO_ONE`, `ONE_TO_ONE`, or `ONE_TO_MANY` |
| `sql_type` | `FieldType` | SQL column type enum |
| `sql_type_str` | `str` | SQL type string (e.g. `"TEXT"`) |
| `entity_ref` | `str \| None` | Referenced entity class name, or `None` |
