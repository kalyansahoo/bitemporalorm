from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectionConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    min_pool_size: int = 2
    max_pool_size: int = 10

    @property
    def asyncpg_dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def connectorx_uri(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def psycopg2_dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )
