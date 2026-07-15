"""Database connection settings (env-driven)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class DatabaseConfig:
    host: str = "127.0.0.1"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    database: str = "ed2k"
    min_conn: int = 1
    max_conn: int = 8

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        return cls(
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB", "ed2k"),
            min_conn=int(os.getenv("POSTGRES_MIN_CONN", "1")),
            max_conn=int(os.getenv("POSTGRES_MAX_CONN", "8")),
        )

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )
