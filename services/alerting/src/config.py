"""Per-service environment configuration — no hardcoded ports/connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    kafka_brokers: str
    database_url: str
    redis_url: str
    query_api_base_url: str
    identity_base_url: str
    port: int
    evaluation_interval_seconds: float = 5.0
    notification_latency_budget_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings(
        kafka_brokers=os.environ["KAFKA_BROKERS"],
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        query_api_base_url=os.environ.get("QUERY_API_BASE_URL", "http://query-api:8005"),
        identity_base_url=os.environ.get("IDENTITY_BASE_URL", "http://identity:8001"),
        port=int(os.environ.get("PORT", "8006")),
    )
