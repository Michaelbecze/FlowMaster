"""Per-service environment configuration — no hardcoded ports/connection strings
(constitution Principle I / Technology & Security Constraints)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    port: int
    session_ttl_seconds: int = 3600
    site_stale_after_seconds: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        session_secret=os.environ["SESSION_SECRET"],
        port=int(os.environ.get("PORT", "8001")),
    )
