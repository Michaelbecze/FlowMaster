"""Consumes flow-records.v1 with idempotent dedupe on replay (at-least-once delivery
per contracts/event-flow-record.md), then hands validated events to the BatchWriter."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from aiokafka import AIOKafkaConsumer

from shared.events.flow_record import FlowRecordEvent

from .batch_writer import BatchWriter
from .config import get_settings

logger = logging.getLogger(__name__)

TOPIC = "flow-records.v1"
_DEDUPE_TTL_SECONDS = 300


class DedupeCache:
    """Bounded, TTL-based cache of recently-seen dedupe keys."""

    def __init__(self, ttl_seconds: float = _DEDUPE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[tuple, float] = {}

    def seen_before(self, key: tuple) -> bool:
        self._evict_expired()
        now = time.monotonic()
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, seen_at in self._seen.items() if now - seen_at > self._ttl]
        for k in expired:
            del self._seen[k]


async def run_consumer(writer: BatchWriter, dedupe: DedupeCache | None = None) -> AIOKafkaConsumer:
    settings = get_settings()
    dedupe = dedupe or DedupeCache()
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=settings.kafka_brokers,
        group_id="flow-writer",
        enable_auto_commit=True,
    )
    await consumer.start()

    async def _consume_loop() -> None:
        async for msg in consumer:
            await _handle_message(msg.value, writer, dedupe)

    asyncio.create_task(_consume_loop())
    return consumer


async def _handle_message(raw: bytes, writer: BatchWriter, dedupe: DedupeCache) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("dropped non-JSON message on %s", TOPIC)
        return

    if not FlowRecordEvent.is_supported_schema_version(payload.get("schema_version", "")):
        logger.warning("quarantined event with unsupported schema_version: %s", payload.get("schema_version"))
        return

    event = FlowRecordEvent.model_validate(payload)
    if dedupe.seen_before(event.dedupe_key()):
        return

    await writer.add(event)
