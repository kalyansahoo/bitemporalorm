# Table Structure

For each entity and each of its fields, bitemporalorm creates a specific set of tables. Understanding this structure helps with debugging, direct SQL queries, and capacity planning.

---

## Entity table

Every `Entity` subclass gets a root table:

```sql
CREATE TABLE "business_entity" (
    "id"         BIGSERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This table only stores the entity's identity and creation time. All data lives in the per-field tables.

---

## Field audit table — `<entity>_to_<field>_audit`

An **append-only** event log. Rows are inserted on every `.save()` call and never modified.

```sql
CREATE TABLE "business_entity_to_city_audit" (
    "id"         BIGSERIAL NOT NULL PRIMARY KEY,
    "entity_id"  BIGINT NOT NULL REFERENCES "business_entity"("id") ON DELETE CASCADE,
    "value"      TEXT,
    "as_of"      TSTZRANGE NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Column | Description |
|---|---|
| `entity_id` | The entity this event belongs to |
| `value` | The field value at the time of this event |
| `as_of` | The valid-time range claimed by the event (as submitted to `.save()`) |
| `created_at` | Transaction time — when this event was recorded in the database |

### Indexes on audit tables

```sql
CREATE INDEX ON "business_entity_to_city_audit" ("entity_id");
CREATE INDEX ON "business_entity_to_city_audit" USING GIST ("as_of");
CREATE INDEX ON "business_entity_to_city_audit" USING GIST ("entity_id", "as_of");
```

---

## Field materialized table — `<entity>_to_<field>`

A **maintained view** that contains non-overlapping `tstzrange` rows representing the complete valid-time history of a field for each entity. Updated on every `.save()` call.

```sql
CREATE TABLE "business_entity_to_city" (
    "entity_id" BIGINT NOT NULL REFERENCES "business_entity"("id") ON DELETE CASCADE,
    "value"     TEXT,
    "as_of"     TSTZRANGE NOT NULL,
    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)  -- M:1 and 1:1 only
);
```

| Column | Description |
|---|---|
| `entity_id` | The entity this row belongs to |
| `value` | The field value for this time period |
| `as_of` | The valid-time range `[start, end)` during which `value` was the current value |

### Exclusion constraint

For `ManyToOneField` and `OneToOneField`, the exclusion constraint `EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)` ensures:

- No two rows for the same entity can have overlapping `as_of` ranges.
- The database enforces that the materialized view is always consistent.

For `OneToManyField`, this constraint is **omitted** — multiple rows for the same entity at the same time are valid (e.g., multiple directors simultaneously).

### Indexes on materialized tables

```sql
CREATE INDEX ON "business_entity_to_city" ("entity_id");
CREATE INDEX ON "business_entity_to_city" USING GIST ("as_of");
CREATE INDEX ON "business_entity_to_city" USING GIST ("entity_id", "as_of");
```

The `(entity_id, as_of)` GiST index is the key performance index for point-in-time queries.

---

## Hierarchy table — `<child>_to_parent_entity`

For entities with a parent (single inheritance), a hierarchy table records the parent-child link with its own valid-time range:

```sql
CREATE TABLE "regional_office_to_parent_entity" (
    "entity_id"        BIGINT NOT NULL REFERENCES "regional_office"("id") ON DELETE CASCADE,
    "parent_entity_id" BIGINT NOT NULL REFERENCES "business_entity"("id"),
    "as_of"            TSTZRANGE NOT NULL,
    EXCLUDE USING GIST ("entity_id" WITH =, "as_of" WITH &&)
);
CREATE INDEX ON "regional_office_to_parent_entity" ("entity_id");
CREATE INDEX ON "regional_office_to_parent_entity" USING GIST ("as_of");
```

This allows the parent-child relationship itself to be bitemporal — a regional office could theoretically be reassigned to a different parent entity over time.

---

## Full table picture for the hierarchy example

```
business_entity                          ← id, created_at
  business_entity_to_city                ← entity_id, value, as_of
  business_entity_to_city_audit          ← id, entity_id, value, as_of, created_at
  business_entity_to_phone_number        ← entity_id, value, as_of
  business_entity_to_phone_number_audit  ← id, entity_id, value, as_of, created_at
  business_entity_to_director            ← entity_id, value, as_of  (no EXCLUDE)
  business_entity_to_director_audit      ← id, entity_id, value, as_of, created_at

regional_office                          ← id, created_at
  regional_office_to_branch_code         ← entity_id, value, as_of
  regional_office_to_branch_code_audit
  regional_office_to_head_count          ← entity_id, value, as_of
  regional_office_to_head_count_audit
  regional_office_to_parent_entity       ← entity_id, parent_entity_id, as_of

_bitemporalorm_migrations                ← migration tracking
```

---

## Direct SQL queries

Since the schema is predictable, you can always query the tables directly:

```sql
-- What city was entity 1 in on 2021-06-01?
SELECT value
FROM business_entity_to_city
WHERE entity_id = 1
  AND as_of @> '2021-06-01 00:00:00+00'::timestamptz;

-- Full audit trail for entity 1's city
SELECT value, as_of, created_at
FROM business_entity_to_city_audit
WHERE entity_id = 1
ORDER BY created_at;
```
