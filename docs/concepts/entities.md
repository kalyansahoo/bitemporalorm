# Entities & Fields

## Defining an entity

An entity is a Python class that subclasses `Entity`. Field annotations declare what data is tracked.

```python
from bitemporalorm import Entity, ManyToOneField, OneToOneField, OneToManyField

class BusinessEntity(Entity):
    city:         ManyToOneField[str]
    phone_number: OneToOneField[str]
    director:     OneToManyField[str]
```

Each annotated field generates two database tables (audit + materialized). Non-field annotations (anything not typed as a bitemporal field) are ignored.

---

## Field relationship types

The relationship type controls two things:
1. Whether an entity can have multiple values for the field at the same point in time.
2. Whether the materialized table has an exclusion constraint.

### `ManyToOneField`

Many entities share the same value space; each entity has **one value at any given time**.

```python
city: ManyToOneField[str]
```

- Example: city, country, industry, status
- Multiple business entities can all have `city = "London"` simultaneously
- One business entity can only be in one city at a time
- Exclusion constraint: enforced

### `OneToOneField`

A unique value per entity at any given time. Semantically stricter than `ManyToOneField`.

```python
phone_number: OneToOneField[str]
```

- Example: phone number, registration number, primary email
- Exclusion constraint: enforced (no two rows for same entity with overlapping time)

### `OneToManyField`

An entity can have **multiple values simultaneously**.

```python
director: OneToManyField[str]
```

- Example: directors, tags, product categories, subsidiary offices
- Queries return **exploded rows** — one row per `(entity, value)` pair
- No exclusion constraint — multiple rows for the same entity at the same time are allowed

---

## Value types

Field type arguments can be primitive Python types or forward references to other entities.

### Primitive types

| Annotation | SQL column type |
|---|---|
| `ManyToOneField[str]` | `TEXT` |
| `ManyToOneField[int]` | `BIGINT` |
| `ManyToOneField[float]` | `DOUBLE PRECISION` |
| `ManyToOneField[datetime]` | `TIMESTAMPTZ` |

### Entity references

Use a string forward reference to another entity class name:

```python
class Country(Entity):
    code: OneToOneField[str]

class BusinessEntity(Entity):
    country: ManyToOneField["Country"]  # BIGINT FK → country.id
```

The `value` column becomes `BIGINT` with a foreign key constraint to the referenced entity's table.

---

## The `Meta` inner class

Override the default table name:

```python
class BusinessEntity(Entity):
    city: ManyToOneField[str]

    class Meta:
        table_name = "biz_entity"   # default: "business_entity"
```

---

## Single inheritance

Extend an entity by subclassing it. Only **one entity parent** is allowed.

```python
class RegionalOffice(BusinessEntity):
    branch_code: OneToOneField[str]
    head_count:  ManyToOneField[int]
```

### What this creates

- `RegionalOffice` gets its own entity table (`regional_office`) and its own field tables (`regional_office_to_branch_code[_audit]`, etc.).
- A hierarchy table `regional_office_to_parent_entity` links each `RegionalOffice` instance to a specific `BusinessEntity` instance, with a `tstzrange` as_of range.
- When querying `RegionalOffice.filter(as_of=...)`, the result includes **both** own fields (`branch_code`, `head_count`) **and** inherited fields (`city`, `phone_number`, `director`) via a JOIN on `regional_office_to_parent_entity`.

### Hierarchy constraints

- **Single parent only.** Attempting `class Child(P1, P2)` where both are `Entity` subclasses raises `TypeError`.
- **Parent cannot change.** Once a migration is applied, you cannot change which entity class a subclass inherits from. `SchemaDiffer` raises `MigrationError` if you try.

### Accessing own vs inherited fields

```python
RegionalOffice._meta.fields        # {"branch_code": ..., "head_count": ...}  own only
RegionalOffice._meta.all_fields()  # {"city": ..., "phone_number": ..., "director": ...,
                                   #  "branch_code": ..., "head_count": ...}  all
RegionalOffice._meta.parent_entity # BusinessEntity class
RegionalOffice._meta.hierarchy()   # [BusinessEntity]
```

---

## EntityMeta internals

All of the above is handled by `EntityMeta`, a Python metaclass that runs at class creation time:

1. Reads `cls.__annotations__` (Python 3.14 PEP 749 compatible — uses the descriptor, not `vars(cls)`).
2. For each annotation typed as a bitemporal field, creates a `FieldSpec` with the resolved SQL type and relationship.
3. Detects entity parent(s) from `bases`; raises `TypeError` for multiple entity parents.
4. Builds `EntityOptions` and attaches it as `cls._meta`.
5. Registers the class in the global `EntityRegistry`.
