"""GET /events, GET /events/{id}/flows — User Story 4, FR-012 (Acceptance Scenario 2:
"they can see the underlying flow data that triggered it")."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from shared.authz import Principal, require_site_scope

from .. import db
from ..config import get_settings

router = APIRouter(tags=["events"])


def _to_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "alert_rule_id": str(row["alert_rule_id"]),
        "triggered_at": row["triggered_at"],
        "resolved_at": row["resolved_at"],
        "triggering_flow_reference": json.loads(row["triggering_flow_reference"]),
    }


@router.get("/events")
async def list_events(
    rule_id: str | None = Query(None),
    since: datetime | None = Query(None),
    principal: Principal = Depends(require_site_scope),
) -> list[dict]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # Only events for rules the caller owns — an alert event is scoped through its
        # rule's ownership, same as the rule itself (FR-009).
        conditions = ["ar.owner_user_id = $1::uuid"]
        params: list[object] = [principal.user_id]
        if rule_id:
            conditions.append(f"ae.alert_rule_id = ${len(params) + 1}::uuid")
            params.append(rule_id)
        if since:
            conditions.append(f"ae.triggered_at >= ${len(params) + 1}")
            params.append(since)

        rows = await conn.fetch(
            f"""
            SELECT ae.id, ae.alert_rule_id, ae.triggered_at, ae.resolved_at,
                   ae.triggering_flow_reference
            FROM alert_event ae
            JOIN alert_rule ar ON ar.id = ae.alert_rule_id
            WHERE {" AND ".join(conditions)}
            ORDER BY ae.triggered_at DESC
            """,
            *params,
        )
    return [_to_dict(r) for r in rows]


@router.get("/events/{event_id}/flows")
async def get_event_flows(
    event_id: str, principal: Principal = Depends(require_site_scope)
) -> list[dict]:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ae.triggered_at, ae.triggering_flow_reference
            FROM alert_event ae
            JOIN alert_rule ar ON ar.id = ae.alert_rule_id
            WHERE ae.id = $1::uuid AND ar.owner_user_id = $2::uuid
            """,
            event_id,
            principal.user_id,
        )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert event not found")

    reference = json.loads(row["triggering_flow_reference"])
    window_seconds = reference.get("window_seconds", 300)
    end = row["triggered_at"]
    start = end - timedelta(seconds=window_seconds)

    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.query_api_base_url, timeout=5.0) as client:
        resp = await client.get(
            "/internal/flows",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "site_ids": ",".join(reference.get("site_ids", [])),
            },
        )
        resp.raise_for_status()
        return resp.json()
