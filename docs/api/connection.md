# Connection

## `ConnectionConfig`

```python
from bitemporalorm import ConnectionConfig
```

Holds connection parameters for both the async write path (asyncpg) and the bulk read path (connectorx).

```python
@dataclass
class ConnectionConfig:
    host:     str = "localhost"
    port:     int = 5432
    database: str = "postgres"
    user:     str = "postgres"
    password: str = ""
```

### Derived properties

| Property | Format | Used by |
|---|---|---|
| `asyncpg_dsn` | `postgresql://user:pass@host:port/db` | `AsyncPool` |
| `connectorx_uri` | `postgresql://user:pass@host:port/db` | `DBExecutor.read_as_dataframe()` |
| `psycopg2_dsn` | `host=... port=... dbname=... user=... password=...` | CLI / sync helpers |

```python
config = ConnectionConfig(
    host="localhost",
    port=5432,
    database="mydb",
    user="postgres",
    password="secret",
)

print(config.asyncpg_dsn)
# postgresql://postgres:secret@localhost:5432/mydb
```

---

## `AsyncPool`

```python
from bitemporalorm.connection.pool import AsyncPool
```

Thin wrapper around an asyncpg connection pool.

### Constructor

```python
AsyncPool(config: ConnectionConfig)
```

### Methods

| Method | Description |
|---|---|
| `await connect()` | Open the connection pool |
| `await disconnect()` | Close the connection pool |
| `await execute(sql, *args)` | Execute a statement, discard result |
| `await fetch(sql, *args)` | Fetch all rows as a list of `asyncpg.Record` |
| `await fetchrow(sql, *args)` | Fetch one row (or `None`) |
| `await fetchval(sql, *args)` | Fetch the first column of the first row |
| `await execute_ddl(sql)` | Execute a DDL statement (no parameters) |

```python
pool = AsyncPool(config)
await pool.connect()

rows = await pool.fetch("SELECT id FROM business_entity WHERE id = $1", 42)
await pool.execute("DELETE FROM business_entity WHERE id = $1", 42)

await pool.disconnect()
```

### Context manager

```python
async with AsyncPool(config) as pool:
    rows = await pool.fetch("SELECT id FROM business_entity")
```

---

## `DBExecutor`

```python
from bitemporalorm import DBExecutor
```

High-level executor that handles both writes (asyncpg) and bulk reads (connectorx). All `Entity.save()` and `Entity.filter()` calls are delegated to a `DBExecutor`.

### Constructor

```python
DBExecutor(pool: AsyncPool)
```

### Methods

#### `save_entity(entity_cls, df)`

```python
async def save_entity(
    entity_cls: type[Entity],
    df: pl.DataFrame,
) -> pl.DataFrame
```

Persists a DataFrame of bitemporal events. Delegates to the internal save pipeline:

1. Allocate `entity_id` for rows without one.
2. Insert audit rows for each field column present in `df`.
3. Run the split-and-reinsert materialized update for each field.

Returns `df` with `entity_id` populated.

#### `read_as_dataframe(sql)`

```python
def read_as_dataframe(sql: str) -> pl.DataFrame
```

Executes `sql` via connectorx and returns a Polars DataFrame. Used by `Entity.filter()`.

!!! note
    This is a synchronous method. connectorx manages its own thread pool internally.

---

## Global executor registry

Executors are registered globally by alias so that `Entity.save()` and `Entity.filter()` can resolve the correct executor without being passed one explicitly.

```python
from bitemporalorm import register_executor, get_executor
```

### `register_executor(executor, alias="default")`

```python
def register_executor(executor: DBExecutor, alias: str = "default") -> None
```

Register `executor` under `alias`. The alias `"default"` is used unless overridden.

### `get_executor(alias="default")`

```python
def get_executor(alias: str = "default") -> DBExecutor
```

Retrieve a registered executor. Raises `KeyError` if `alias` is not registered.

---

## Typical setup

```python
import asyncio
from bitemporalorm import ConnectionConfig, DBExecutor, register_executor
from bitemporalorm.connection.pool import AsyncPool

async def startup():
    config = ConnectionConfig(
        host="localhost",
        database="mydb",
        user="postgres",
        password="secret",
    )
    pool = AsyncPool(config)
    await pool.connect()

    executor = DBExecutor(pool)
    register_executor(executor)          # registered as "default"

async def shutdown():
    get_executor().pool.disconnect()
```

After `register_executor()`, all `Entity.save()` and `Entity.filter()` calls will use the default executor automatically.

### Multiple databases

```python
register_executor(executor_a, alias="primary")
register_executor(executor_b, alias="replica")

# Entity.filter() uses "default" unless you override it at the Entity level
register_executor(executor_a)   # also register as default
```
