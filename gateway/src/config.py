"""Gateway environment configuration — no hardcoded service URLs/ports."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    identity_base_url: str
    query_api_base_url: str
    alerting_base_url: str
    realtime_base_url: str
    redis_url: str
    port: int
    rate_limit_per_minute: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings(
        identity_base_url=os.environ["IDENTITY_BASE_URL"],
        query_api_base_url=os.environ["QUERY_API_BASE_URL"],
        alerting_base_url=os.environ["ALERTING_BASE_URL"],
        realtime_base_url=os.environ["REALTIME_BASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        port=int(os.environ.get("PORT", "8080")),
    )
