"""Per-service environment configuration — no hardcoded ports/connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    clickhouse_url: str
    database_url: str
    identity_base_url: str
    port: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        clickhouse_url=os.environ["CLICKHOUSE_URL"],
        database_url=os.environ["DATABASE_URL"],
        identity_base_url=os.environ.get("IDENTITY_BASE_URL", "http://identity:8001"),
        port=int(os.environ.get("PORT", "8005")),
    )
