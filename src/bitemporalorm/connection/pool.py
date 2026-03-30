from __future__ import annotations

from typing import Any

import asyncpg

from bitemporalorm.connection.config import ConnectionConfig


class AsyncPool:
    """Thin wrapper around asyncpg connection pool."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=self._config.asyncpg_dsn,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(
                "Database pool is not connected. "
                "Call connect() or use bitemporalorm_lifespan() in your FastAPI app."
            )
        return self._pool

    async def execute(self, sql: str, *args: Any) -> str:
        return await self._require_pool().execute(sql, *args)  # type: ignore[no-any-return]

    async def executemany(self, sql: str, args: list[tuple]) -> None:
        await self._require_pool().executemany(sql, args)

    async def fetch(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        return await self._require_pool().fetch(sql, *args)  # type: ignore[no-any-return]

    async def fetchrow(self, sql: str, *args: Any) -> asyncpg.Record | None:
        return await self._require_pool().fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return await self._require_pool().fetchval(sql, *args)

    async def execute_ddl(self, sql: str) -> None:
        """Execute DDL statement(s) inside a transaction."""
        async with self._require_pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
