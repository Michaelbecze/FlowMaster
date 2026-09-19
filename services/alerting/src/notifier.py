"""Redis-backed de-dup state and notification delivery (FR-013).

While a condition remains continuously true, no new AlertEvent/notification is
created — the existing event's state is what's updated. Delivery latency is measured
from the flow-records.v1 event's observed_at, not from when this evaluator happened to
poll, per contracts/alerting-api.md's behavioral contract for SC-007's 60s target.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import httpx
import redis.asyncio as redis

from . import db
from .config import get_settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def _dedup_key(rule_id: str) -> str:
    return f"alerting:dedup:{rule_id}"


async def is_active(rule_id: str) -> bool:
    client = _get_redis()
    return await client.get(_dedup_key(rule_id)) is not None


async def trigger(
    rule_id: str,
    notification_target: dict,
    triggering_flow_reference: dict,
    condition_met_at: datetime,
) -> str:
    """Creates the AlertEvent, marks the rule's de-dup state active, and delivers the
    notification. Returns the new AlertEvent id."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alert_event (alert_rule_id, triggering_flow_reference)
            VALUES ($1::uuid, $2::jsonb)
            RETURNING id
            """,
            rule_id,
            json.dumps(triggering_flow_reference),
        )
    event_id = str(row["id"])

    client = _get_redis()
    settings = get_settings()
    await client.set(_dedup_key(rule_id), event_id, ex=settings.notification_latency_budget_seconds * 10)

    await _deliver(rule_id, event_id, notification_target, condition_met_at)
    return event_id


async def resolve(rule_id: str) -> None:
    client = _get_redis()
    event_id = await client.get(_dedup_key(rule_id))
    if event_id is None:
        return

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE alert_event SET resolved_at = now() WHERE id = $1::uuid AND resolved_at IS NULL",
            event_id,
        )
    await client.delete(_dedup_key(rule_id))


async def _deliver(
    rule_id: str, event_id: str, notification_target: dict, condition_met_at: datetime
) -> None:
    latency = (datetime.now(timezone.utc) - condition_met_at).total_seconds()
    settings = get_settings()
    if latency > settings.notification_latency_budget_seconds:
        logger.warning(
            "alert %s for rule %s delivered after %.1fs, exceeding the %ds SC-007 budget",
            event_id, rule_id, latency, settings.notification_latency_budget_seconds,
        )

    url = notification_target.get("webhook_url")
    if not url:
        logger.info("alert %s fired for rule %s (%.1fs latency, no webhook configured)", event_id, rule_id, latency)
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(url, json={"alert_rule_id": rule_id, "alert_event_id": event_id})
        except httpx.HTTPError:
            logger.warning("failed to deliver webhook notification for alert %s", event_id)
