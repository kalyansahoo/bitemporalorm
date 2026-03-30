from __future__ import annotations

from typing import Any

from bitemporalorm.connection.config import ConnectionConfig
from bitemporalorm.migration.loader import LoadedMigration, MigrationLoader

_TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "_bitemporalorm_migrations" (
    "id"         BIGSERIAL PRIMARY KEY,
    "name"       TEXT NOT NULL UNIQUE,
    "applied_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class MigrationRunner:
    """Applies pending migrations to a live PostgreSQL database."""

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config

    def _get_conn(self) -> Any:
        import psycopg2

        conn = psycopg2.connect(self._config.psycopg2_dsn)
        conn.autocommit = True
        return conn

    def ensure_migration_table(self) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_TRACKING_TABLE_SQL)
        finally:
            conn.close()

    def applied_migrations(self) -> list[str]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT name FROM "_bitemporalorm_migrations" ORDER BY id')
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def pending_migrations(self, migrations_dir: str) -> list[LoadedMigration]:
        loader = MigrationLoader(migrations_dir)
        all_mig = loader.load()
        applied = set(self.applied_migrations())
        return [m for m in all_mig if m.name not in applied]

    def apply(self, migration: LoadedMigration, fake: bool = False) -> None:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if not fake:
                    for op in migration.operations:
                        sql = op.to_sql()
                        cur.execute(sql)
                cur.execute(
                    'INSERT INTO "_bitemporalorm_migrations" (name) VALUES (%s)',
                    (migration.name,),
                )
        finally:
            conn.close()

    def plan_sql(self, migrations: list[LoadedMigration]) -> str:
        lines: list[str] = [f"Pending migrations: {len(migrations)}\n"]
        for mig in migrations:
            lines.append(f"── {mig.name} " + "─" * max(1, 60 - len(mig.name)))
            for op in mig.operations:
                lines.append(op.to_sql())
                lines.append("")
        return "\n".join(lines)
