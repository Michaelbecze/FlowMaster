"""GET /top-talkers — highest-bandwidth source IPs in range (User Story 1, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope

from .. import clickhouse
from ..auth import require_authenticated
from .summary import _parse_range

router = APIRouter(tags=["query"])


@router.get("/top-talkers")
async def get_top_talkers(
    range: str = Query("1h"),
    sites: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    _auth: str = Depends(require_authenticated),
) -> Envelope[list[dict]]:
    hours = _parse_range(range)
    site_ids = [s for s in sites.split(",") if s]

    client = await clickhouse.get_client()
    rows = await client.query(
        "SELECT src_addr, sum(bytes) AS total_bytes FROM flow_record "
        "WHERE site_id IN {site_ids:Array(String)} AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR "
        "GROUP BY src_addr ORDER BY total_bytes DESC LIMIT {limit:UInt32}",
        parameters={"site_ids": site_ids, "hours": hours, "limit": limit},
    )
    data = [{"src_addr": r[0], "total_bytes": r[1]} for r in rows.result_rows]

    empty = len(data) == 0
    return Envelope.of(data, empty=empty, reason=EmptyReason.NO_TRAFFIC if empty else None)
