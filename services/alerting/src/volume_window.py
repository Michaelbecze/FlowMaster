"""Per-site rolling byte-volume window in Redis, populated by evaluator.py's own
flow-records.v1 consumer — alerting maintains this independently rather than reading
realtime's aggregate cache, so each service's Redis usage stays its own concern
(constitution Principle I), even though they share a Redis instance for v1."""

from __future__ import annotations

import time

import redis.asyncio as redis

from .config import get_settings

_MAX_RETENTION_SECONDS = 3600  # covers any rule's window_seconds up to one hour

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


_KNOWN_SITES_KEY = "alerting:known_sites"


def _key(site_id: str) -> str:
    return f"alerting:volume:{site_id}"


async def record_bytes(site_id: str, num_bytes: int, at: float | None = None) -> None:
    at = at if at is not None else time.time()
    client = get_redis()
    key = _key(site_id)
    # A unique member per call (score alone isn't unique across same-timestamp events).
    member = f"{at}:{num_bytes}:{id(object())}"
    async with client.pipeline(transaction=True) as pipe:
        pipe.zadd(key, {member: at})
        pipe.zremrangebyscore(key, 0, at - _MAX_RETENTION_SECONDS)
        pipe.expire(key, _MAX_RETENTION_SECONDS)
        pipe.sadd(_KNOWN_SITES_KEY, site_id)
        await pipe.execute()


async def known_site_ids() -> list[str]:
    client = get_redis()
    return list(await client.smembers(_KNOWN_SITES_KEY))


async def sum_window(site_ids: list[str], window_seconds: int) -> int:
    client = get_redis()
    now = time.time()
    total = 0
    for site_id in site_ids:
        members = await client.zrangebyscore(_key(site_id), now - window_seconds, now)
        for member in members:
            # member format: "<timestamp>:<bytes>:<uniqueifier>"
            total += int(member.split(":")[1])
    return total
