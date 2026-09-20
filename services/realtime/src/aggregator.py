"""Consumes flow-records.v1 and maintains a Redis-backed rolling aggregate per site,
serving SC-001's 5-second dashboard-latency target without re-querying ClickHouse on
every tick (research.md #3)."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer

from shared.events.flow_record import FlowRecordEvent

from .config import get_settings
from .staleness import note_site_seen

logger = logging.getLogger(__name__)

TOPIC = "flow-records.v1"

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def _events_key(site_id: str) -> str:
    return f"realtime:events:{site_id}"


def _sites_key() -> str:
    return "realtime:sites"


async def record_event(event: FlowRecordEvent, seen_at: float | None = None) -> None:
    """Appends one flow into the site's rolling window (a Redis sorted set scored by
    time) and trims anything older than the window — the cache is rebuildable from
    ClickHouse/the event stream, never a system of record (data-model.md)."""
    settings = get_settings()
    client = get_redis()
    seen_at = seen_at if seen_at is not None else time.time()

    member = json.dumps(
        {
            "bytes": event.bytes,
            "packets": event.packets,
            "protocol": event.protocol,
            "application": event.application,
            "src_addr": event.src_addr,
            "t": seen_at,
        }
    )
    key = _events_key(event.site_id)
    async with client.pipeline(transaction=True) as pipe:
        pipe.zadd(key, {member: seen_at})
        pipe.zremrangebyscore(key, 0, seen_at - settings.window_seconds)
        pipe.expire(key, settings.window_seconds * 2)
        pipe.sadd(_sites_key(), event.site_id)
        await pipe.execute()


async def get_site_summary(site_id: str, window_seconds: int | None = None) -> dict:
    settings = get_settings()
    window_seconds = window_seconds or settings.window_seconds
    client = get_redis()
    now = time.time()
    raw = await client.zrangebyscore(_events_key(site_id), now - window_seconds, now)

    total_bytes = 0
    total_packets = 0
    protocol_mix: dict[str, int] = {}
    talkers: dict[str, int] = {}
    for item in raw:
        record = json.loads(item)
        total_bytes += record["bytes"]
        total_packets += record["packets"]
        protocol_mix[record["application"]] = protocol_mix.get(record["application"], 0) + record["bytes"]
        talkers[record["src_addr"]] = talkers.get(record["src_addr"], 0) + record["bytes"]

    top_talkers = sorted(talkers.items(), key=lambda kv: kv[1], reverse=True)[
        : settings.top_talkers_limit
    ]
    return {
        "site_id": site_id,
        "total_bytes": total_bytes,
        "total_packets": total_packets,
        "protocol_mix": protocol_mix,
        "top_talkers": [{"src_addr": ip, "bytes": b} for ip, b in top_talkers],
    }


async def known_site_ids() -> set[str]:
    client = get_redis()
    return await client.smembers(_sites_key())


async def run_aggregator() -> AIOKafkaConsumer:
    settings = get_settings()
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=settings.kafka_brokers,
        group_id="realtime-aggregator",
        enable_auto_commit=True,
    )
    await consumer.start()

    async def _consume_loop() -> None:
        async for msg in consumer:
            await _handle_message(msg.value)

    asyncio.create_task(_consume_loop())
    return consumer


async def _handle_message(raw: bytes) -> None:
    try:
        payload = json.loads(raw)
        if not FlowRecordEvent.is_supported_schema_version(payload.get("schema_version", "")):
            return
        event = FlowRecordEvent.model_validate(payload)
    except (json.JSONDecodeError, ValueError):
        logger.warning("dropped unparseable event on %s", TOPIC)
        return
    await record_event(event)
    await note_site_seen(event.site_id)
