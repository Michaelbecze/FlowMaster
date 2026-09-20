"""GET /internal/flows — service-to-service flow lookup, used by Alerting's
GET /events/{id}/flows (contracts/alerting-api.md's "see the underlying flow data
that triggered it") so alerting can fulfill that contract without reaching into
ClickHouse directly (constitution Principle I: flow data stays owned by query-api).
Not exposed through the Gateway's public routing table."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from ..flow_query import FlowFilter, query_flows

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/flows")
async def get_flows_internal(
    start: datetime = Query(...),
    end: datetime = Query(...),
    site_ids: str = Query("", description="Comma-separated site ids; empty = all sites"),
) -> list[dict]:
    ids = [s for s in site_ids.split(",") if s]
    flt = FlowFilter(start=start, end=end)
    return await query_flows(flt, allowed_site_ids=ids or None)
