# Filter & Query

## `Entity.filter()`

```python
@classmethod
async def filter(cls, as_of: datetime, *exprs: pl.Expr) -> pl.DataFrame
```

See [Entity API](entity.md#entityfilter--point-in-time-query) for the full signature.

---

## `ExprTranslator`

`ExprTranslator` converts Polars `pl.Expr` objects to SQL `WHERE` fragments by walking the Polars JSON AST (`expr.meta.serialize(format="json")`).

```python
from bitemporalorm.query.builder import ExprTranslator

translator = ExprTranslator(alias_map={"city": "f_city", "score": "f_score"})
sql_fragment = translator.translate(pl.col("city") == "London")
# → '("f_city".value = \'London\')'
```

### Constructor

```python
ExprTranslator(alias_map: dict[str, str])
```

`alias_map` maps field names to their JOIN alias (e.g. `"city"` → `"f_city"`). The value column is accessed as `"f_city".value`.

### `translate(expr: pl.Expr) → str`

Translates a Polars expression to a SQL string. Raises `FilterError` for unsupported node types.

### Supported AST nodes

| Polars | SQL output |
|---|---|
| `pl.col("city")` | `"f_city".value` |
| `pl.col("entity_id")` | `e.id` |
| String literal | `'London'` |
| Integer literal | `42` |
| Float literal | `3.14` |
| Boolean literal | `TRUE` / `FALSE` |
| `==` | `=` |
| `!=` | `!=` |
| `<`, `<=`, `>`, `>=` | same |
| `&` | `AND` |
| `\|` | `OR` |
| `~` | `NOT` |
| `.is_null()` | `IS NULL` |
| `.is_not_null()` | `IS NOT NULL` |
| `.is_in([...])` | `IN (...)` |
| `.is_between(a, b)` | `BETWEEN a AND b` |
| `.str.contains("x")` | `LIKE '%x%'` |
| `.str.starts_with("x")` | `LIKE 'x%'` |
| `.str.ends_with("x")` | `LIKE '%x'` |
| `.str.to_lowercase()` | `LOWER(...)` |

---

## `FilterError`

```python
from bitemporalorm.query.builder import FilterError
```

Raised by `ExprTranslator.translate()` when:

- A column name is not in the entity's declared fields (or `entity_id`).
- A Polars AST node type has no SQL equivalent (e.g. `map_elements`, complex casts).

```python
try:
    await BusinessEntity.filter(
        as_of=datetime(2022, 1, 1, tzinfo=timezone.utc),
        pl.col("nonexistent_field") == "x",
    )
except FilterError as e:
    print(e)
# Unknown column 'nonexistent_field'. Must be a declared field name or 'entity_id'.
```

---

## `build_filter_sql()`

Internal function used by `Entity.filter()`. Exposed for advanced use cases.

```python
from bitemporalorm.query.builder import build_filter_sql

sql, params = build_filter_sql(
    entity_cls=BusinessEntity,
    as_of=datetime(2022, 6, 1, tzinfo=timezone.utc),
    exprs=[pl.col("city") == "London"],
)
print(sql)
```

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `entity_cls` | `type[Entity]` | The entity class to query |
| `as_of` | `datetime` | Point-in-time timestamp |
| `exprs` | `list[pl.Expr]` | Additional filter expressions |

### Returns

`(sql: str, params: list)` — always returns an empty `params` list (the timestamp is embedded as a literal in the SQL string for connectorx compatibility).
