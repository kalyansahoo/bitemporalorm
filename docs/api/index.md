# API Reference

Complete reference for all public symbols in bitemporalorm.

---

## Modules

| Page | Contents |
|---|---|
| [Entity](entity.md) | `Entity`, `EntityOptions`, `EntityRegistry` |
| [Fields](fields.md) | `ManyToOneField`, `OneToOneField`, `OneToManyField`, `FieldType`, `FieldSpec` |
| [Filter & Query](filter.md) | `Entity.filter()`, `ExprTranslator`, `FilterError` |
| [Migrations](migrations.md) | All 6 operation classes, `MigrationState`, `SchemaDiffer`, `MigrationRunner` |
| [Connection](connection.md) | `ConnectionConfig`, `DBExecutor`, `AsyncPool` |

---

## Quick symbol index

| Symbol | Module | Description |
|---|---|---|
| `Entity` | `bitemporalorm` | Base class for all entities |
| `ManyToOneField` | `bitemporalorm` | Field descriptor: one value per entity at any time, many entities share value |
| `OneToOneField` | `bitemporalorm` | Field descriptor: strictly one value per entity at any time |
| `OneToManyField` | `bitemporalorm` | Field descriptor: multiple values per entity at same time |
| `FieldType` | `bitemporalorm` | Enum of SQL types |
| `ConnectionConfig` | `bitemporalorm` | Database connection settings |
| `DBExecutor` | `bitemporalorm` | Manages reads, writes, and DDL |
| `register_executor` | `bitemporalorm` | Register a `DBExecutor` under an alias |
| `get_executor` | `bitemporalorm` | Retrieve a registered executor |
| `registry` | `bitemporalorm` | Global `EntityRegistry` singleton |
| `MigrationError` | `bitemporalorm` | Raised on forbidden schema changes |
