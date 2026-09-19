"""Consumes flow-records.v1 to feed the rolling volume window, and periodically
evaluates active AlertRules against it (User Story 4, FR-012/FR-013)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer
from shared.events.flow_record import FlowRecordEvent

from . import db, notifier, volume_window
from .config import get_settings
from .scope_client import get_owner_scope

logger = logging.getLogger(__name__)

TOPIC = "flow-records.v1"


async def run_flow_consumer() -> AIOKafkaConsumer:
    settings = get_settings()
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=settings.kafka_brokers,
        group_id="alerting",
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
    await volume_window.record_bytes(event.site_id, event.bytes)


async def _fetch_enabled_rules() -> list[dict]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, owner_user_id, site_scope, condition_definition, "
            "notification_target FROM alert_rule WHERE enabled"
        )
    return [
        {
            "id": str(r["id"]),
            "owner_user_id": str(r["owner_user_id"]),
            "site_scope": str(r["site_scope"]) if r["site_scope"] else None,
            "condition": json.loads(r["condition_definition"]),
            "notification_target": json.loads(r["notification_target"]),
        }
        for r in rows
    ]


async def _evaluate_rule(rule: dict) -> None:
    condition = rule["condition"]
    if condition.get("type") != "volume_threshold":
        return  # v1 evaluator only understands volume_threshold (see routes/rules.py)

    # Re-verified at evaluation time, not just at rule creation (contracts/alerting-api.md):
    # a later access-scope reduction stops this rule from evaluating a site no longer
    # in the owner's scope.
    all_sites, owned_site_ids = await get_owner_scope(rule["owner_user_id"])

    if rule["site_scope"]:
        if not all_sites and rule["site_scope"] not in owned_site_ids:
            await notifier.resolve(rule["id"])  # owner lost access; stop treating it as active
            return
        site_ids = [rule["site_scope"]]
    elif all_sites:
        # Org-wide with unrestricted access: evaluate every site currently carrying
        # traffic rather than an unbounded "all sites that ever existed" scan.
        site_ids = await _all_tracked_site_ids()
    else:
        site_ids = owned_site_ids

    if not site_ids:
        return

    total_bytes = await volume_window.sum_window(site_ids, condition["window_seconds"])
    condition_met = total_bytes >= condition["bytes_threshold"]
    currently_active = await notifier.is_active(rule["id"])

    if condition_met and not currently_active:
        await notifier.trigger(
            rule["id"],
            rule["notification_target"],
            triggering_flow_reference={
                "site_ids": site_ids,
                "window_seconds": condition["window_seconds"],
                "observed_bytes": total_bytes,
            },
            condition_met_at=datetime.now(timezone.utc),
        )
    elif not condition_met and currently_active:
        await notifier.resolve(rule["id"])


async def _all_tracked_site_ids() -> list[str]:
    """Fallback when an org-wide rule's owner has unrestricted (all_sites) scope: this
    evaluator only knows which sites it has itself seen traffic for, via its own
    volume_window state — it does not query identity's full site list, since an
    org-wide rule only needs to consider sites that are actually producing traffic."""
    return await volume_window.known_site_ids()


async def run_evaluation_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.evaluation_interval_seconds)
        try:
            rules = await _fetch_enabled_rules()
            for rule in rules:
                await _evaluate_rule(rule)
        except Exception:  # noqa: BLE001 — one bad evaluation pass must not crash the service
            logger.exception("alert evaluation pass failed; will retry next interval")
