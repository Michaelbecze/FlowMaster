"""Per-service environment configuration — no hardcoded ports/connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    kafka_brokers: str
    clickhouse_url: str
    database_url: str
    port: int
    batch_max_size: int = 500
    batch_max_seconds: float = 2.0
    retention_check_interval_seconds: float = 3600.0
    default_retention_days: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings(
        kafka_brokers=os.environ["KAFKA_BROKERS"],
        clickhouse_url=os.environ["CLICKHOUSE_URL"],
        database_url=os.environ["DATABASE_URL"],
        port=int(os.environ.get("PORT", "8003")),
    )
