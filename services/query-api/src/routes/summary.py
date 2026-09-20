"""GET /summary — aggregated traffic volume, protocol distribution, and application
breakdown for the caller's authorized sites (User Story 1, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from shared.api.envelope import EmptyReason, Envelope, SiteStatus
from shared.authz import Principal, require_site_scope

from .. import clickhouse
from ..sites_client import list_site_statuses

router = APIRouter(tags=["query"])

_RANGE_TO_HOURS = {"1h": 1, "3h": 3, "6h": 6, "12h": 12, "24h": 24}


def _parse_range(range_: str) -> int:
    if range_ not in _RANGE_TO_HOURS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unsupported range '{range_}'; expected one of {sorted(_RANGE_TO_HOURS)}",
        )
    return _RANGE_TO_HOURS[range_]


@router.get("/summary")
async def get_summary(
    range: str = Query("1h"),
    sites: str = Query(..., description="Comma-separated site ids"),
    principal: Principal = Depends(require_site_scope),
) -> Envelope[dict]:
    hours = _parse_range(range)
    # Never trusts the client-supplied site filter as authorization (contracts/query-api.md):
    # intersected with the caller's actual scope before it ever reaches a ClickHouse query.
    site_ids = principal.filter_sites([s for s in sites.split(",") if s])

    client = await clickhouse.get_client()
    totals = await client.query(
        "SELECT sum(bytes) AS total_bytes, sum(packets) AS total_packets "
        "FROM flow_record WHERE site_id IN {site_ids:Array(String)} "
        "AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR",
        parameters={"site_ids": site_ids, "hours": hours},
    )
    protocol_rows = await client.query(
        "SELECT application, sum(bytes) AS total_bytes FROM flow_record "
        "WHERE site_id IN {site_ids:Array(String)} AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR "
        "GROUP BY application ORDER BY total_bytes DESC",
        parameters={"site_ids": site_ids, "hours": hours},
    )

    total_row = totals.result_rows[0] if totals.result_rows else (0, 0)
    total_bytes, total_packets = total_row[0] or 0, total_row[1] or 0

    data = {
        "total_bytes": total_bytes,
        "total_packets": total_packets,
        "application_breakdown": [
            {"application": r[0], "bytes": r[1]} for r in protocol_rows.result_rows
        ],
    }

    site_status = await list_site_statuses()
    relevant_status = {
        sid: SiteStatus(site_status[sid]) for sid in site_ids if sid in site_status
    }

    empty = total_bytes == 0
    return Envelope.of(
        data,
        empty=empty,
        reason=EmptyReason.NO_TRAFFIC if empty else None,
        site_status=relevant_status,
    )
