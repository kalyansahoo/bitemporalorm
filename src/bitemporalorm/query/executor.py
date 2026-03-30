from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import polars as pl

from bitemporalorm.connection.config import ConnectionConfig
from bitemporalorm.connection.pool import AsyncPool

if TYPE_CHECKING:
    from bitemporalorm.entity import Entity


_INFINITY_TS = "infinity"


class DBExecutor:
    """
    Handles all database I/O for bitemporalorm.

    - Writes via asyncpg (async)
    - Bulk reads via connectorx + polars
    - DDL via asyncpg
    """

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._pool = AsyncPool(config)

    async def connect(self) -> None:
        await self._pool.connect()

    async def disconnect(self) -> None:
        await self._pool.disconnect()

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    async def read_as_dataframe(self, sql: str, _params: list[Any]) -> pl.DataFrame:
        """Execute a read query and return a Polars DataFrame."""
        import connectorx as cx

        df = cx.read_sql(self._config.connectorx_uri, sql, return_type="polars")
        if hasattr(df, "collect"):
            df = df.collect()
        return df

    # -----------------------------------------------------------------------
    # Save entity
    # -----------------------------------------------------------------------

    async def save_entity(
        self,
        entity_cls: type[Entity],
        df: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        Persist entity events from a DataFrame.

        Inserts into audit tables and updates materialized tables.
        Returns the DataFrame with entity_id populated.
        """
        meta = entity_cls._meta
        all_fields = meta.all_fields()

        # Validate required column
        if "as_of_start" not in df.columns:
            raise ValueError("DataFrame must contain an 'as_of_start' column.")

        # Fill defaults
        if "as_of_end" not in df.columns:
            df = df.with_columns(pl.lit(_INFINITY_TS).alias("as_of_end"))

        has_entity_id = "entity_id" in df.columns

        # Convert to list of row dicts for processing
        rows = df.to_dicts()
        result_rows: list[dict] = []

        for row in rows:
            as_of_start = row["as_of_start"]
            as_of_end   = row.get("as_of_end", _INFINITY_TS)
            entity_id   = row.get("entity_id")

            # ---- Insert new entity if needed --------------------------------
            if entity_id is None:
                rec = await self._pool.fetchrow(
                    f'INSERT INTO "{meta.table_name}" DEFAULT VALUES RETURNING id'
                )
                entity_id = rec["id"]

            row["entity_id"] = entity_id

            # ---- Build as_of range literal ----------------------------------
            as_of_start_str = _to_ts_str(as_of_start)
            as_of_end_str   = _to_ts_str(as_of_end) if as_of_end not in (None, _INFINITY_TS, "infinity") else "infinity"
            range_literal   = f"[{as_of_start_str},{as_of_end_str})"

            # ---- Persist each field present in the row ----------------------
            for fname, fspec in all_fields.items():
                if fname not in row:
                    continue

                value = row[fname]
                if value is None:
                    continue

                # Determine the owning entity's table
                owner_table = _find_owner_table(entity_cls, fname)
                audit_table = f"{owner_table}_to_{fname}_audit"
                mat_table   = f"{owner_table}_to_{fname}"

                # ---- Audit insert ------------------------------------------
                await self._pool.execute(
                    f"""
                    INSERT INTO "{audit_table}" (entity_id, value, as_of)
                    VALUES ($1, $2, $3::tstzrange)
                    """,
                    entity_id,
                    str(value),
                    range_literal,
                )

                # ---- Materialized table update -----------------------------
                await self._update_materialized(
                    mat_table=mat_table,
                    entity_id=entity_id,
                    value=value,
                    range_literal=range_literal,
                    as_of_start_str=as_of_start_str,
                    as_of_end_str=as_of_end_str,
                    is_one_to_many=(fspec.relationship.value == "one_to_many"),
                )

            result_rows.append(row)

        return pl.DataFrame(result_rows)

    async def _update_materialized(
        self,
        mat_table: str,
        entity_id: int,
        value: Any,
        range_literal: str,
        as_of_start_str: str,
        as_of_end_str: str,
        is_one_to_many: bool,
    ) -> None:
        """
        Maintain the materialized field table:
        1. Find overlapping rows for this entity_id.
        2. Delete them.
        3. Re-insert split remnants at the boundaries.
        4. Insert the new row.

        For one-to-many we skip step 1–3 (multiple values at same time are OK)
        and just insert.
        """
        if is_one_to_many:
            # No exclusion constraint — just insert
            await self._pool.execute(
                f"""
                INSERT INTO "{mat_table}" (entity_id, value, as_of)
                VALUES ($1, $2, $3::tstzrange)
                """,
                entity_id,
                str(value),
                range_literal,
            )
            return

        # Fetch overlapping rows
        overlap_rows = await self._pool.fetch(
            f"""
            SELECT lower(as_of) AS lo, upper(as_of) AS hi, value
            FROM "{mat_table}"
            WHERE entity_id = $1
              AND as_of && $2::tstzrange
            """,
            entity_id,
            range_literal,
        )

        # Delete overlapping rows
        await self._pool.execute(
            f"""
            DELETE FROM "{mat_table}"
            WHERE entity_id = $1 AND as_of && $2::tstzrange
            """,
            entity_id,
            range_literal,
        )

        # Re-insert left remnants [old_lower, new_start)
        for orow in overlap_rows:
            old_lo = orow["lo"]
            old_hi = orow["hi"]  # may be None for infinity
            old_val = orow["value"]

            if old_lo is not None:
                old_lo_str = _to_ts_str(old_lo)
                if old_lo_str < as_of_start_str:
                    remnant = f"[{old_lo_str},{as_of_start_str})"
                    await self._pool.execute(
                        f"""
                        INSERT INTO "{mat_table}" (entity_id, value, as_of)
                        VALUES ($1, $2, $3::tstzrange)
                        ON CONFLICT DO NOTHING
                        """,
                        entity_id,
                        str(old_val),
                        remnant,
                    )

            # Re-insert right remnant [new_end, old_upper)
            if as_of_end_str != "infinity" and old_hi is not None:
                old_hi_str = _to_ts_str(old_hi)
                if old_hi_str > as_of_end_str:
                    remnant = f"[{as_of_end_str},{old_hi_str})"
                    await self._pool.execute(
                        f"""
                        INSERT INTO "{mat_table}" (entity_id, value, as_of)
                        VALUES ($1, $2, $3::tstzrange)
                        ON CONFLICT DO NOTHING
                        """,
                        entity_id,
                        str(old_val),
                        remnant,
                    )

        # Insert new row
        await self._pool.execute(
            f"""
            INSERT INTO "{mat_table}" (entity_id, value, as_of)
            VALUES ($1, $2, $3::tstzrange)
            """,
            entity_id,
            str(value),
            range_literal,
        )

    # -----------------------------------------------------------------------
    # DDL
    # -----------------------------------------------------------------------

    async def execute_ddl(self, sql: str) -> None:
        await self._pool.execute_ddl(sql)

    def execute_ddl_sync(self, sql: str) -> None:
        """Synchronous DDL execution via psycopg2 (for CLI migrations)."""
        import psycopg2

        conn = psycopg2.connect(self._config.psycopg2_dsn)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Global executor registry
# ---------------------------------------------------------------------------

_executors: dict[str, DBExecutor] = {}


def register_executor(executor: DBExecutor, alias: str = "default") -> None:
    _executors[alias] = executor


def get_executor(alias: str = "default") -> DBExecutor:
    if alias not in _executors:
        raise RuntimeError(
            f"No executor registered under alias '{alias}'. "
            "Call register_executor() or use bitemporalorm_lifespan()."
        )
    return _executors[alias]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_ts_str(value: Any) -> str:
    """Convert various timestamp types to an ISO string PostgreSQL can parse."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _find_owner_table(entity_cls: type[Entity], field_name: str) -> str:
    """Walk the MRO to find which entity table owns the field."""
    from bitemporalorm.entity import EntityMeta

    for cls in entity_cls.__mro__:
        if isinstance(cls, EntityMeta) and cls.__name__ != "Entity":
            if field_name in cls._meta.fields:
                return cls._meta.table_name
    return entity_cls._meta.table_name
