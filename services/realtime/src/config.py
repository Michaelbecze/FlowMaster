"""Per-service environment configuration — no hardcoded ports/connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    kafka_brokers: str
    redis_url: str
    identity_base_url: str
    port: int
    window_seconds: int = 300
    push_interval_seconds: float = 5.0
    stale_after_seconds: int = 90
    staleness_sweep_interval_seconds: float = 15.0
    top_talkers_limit: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings(
        kafka_brokers=os.environ["KAFKA_BROKERS"],
        redis_url=os.environ["REDIS_URL"],
        identity_base_url=os.environ.get("IDENTITY_BASE_URL", "http://identity:8001"),
        port=int(os.environ.get("PORT", "8004")),
    )
