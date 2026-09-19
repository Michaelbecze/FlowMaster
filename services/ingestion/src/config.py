"""Per-service environment configuration — no hardcoded ports/connection strings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    netflow_host: str
    netflow_port: int
    kafka_brokers: str
    identity_base_url: str
    port: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        netflow_host=os.environ.get("NETFLOW_HOST", "0.0.0.0"),
        netflow_port=int(os.environ.get("NETFLOW_PORT", "2055")),
        kafka_brokers=os.environ["KAFKA_BROKERS"],
        identity_base_url=os.environ["IDENTITY_BASE_URL"],
        port=int(os.environ.get("PORT", "8002")),
    )
