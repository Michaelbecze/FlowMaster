"""GET /traffic-over-time — bucketed traffic volume for the live traffic chart.

Not part of the original contracts/query-api.md table; added alongside it (same
envelope conventions, same site-scope enforcement) to restore the time-series
"Traffic Volume" chart from the single-process dashboard that inspired this
platform's User Story 1, now driving the enterprise dashboard's clickable
drill-down chart.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope
from shared.authz import Principal, require_site_scope

from .. import clickhouse
from ..isotime import to_utc_iso
from .summary import _parse_range

router = APIRouter(tags=["query"])

# <=2h: 1-minute buckets (fine enough to see individual spikes); otherwise hourly,
# so a 24h view doesn't return 1440 points.
_FINE_BUCKET_SECONDS = 60
_COARSE_BUCKET_SECONDS = 3600
_FINE_BUCKET_RANGE_HOURS = 2


@router.get("/traffic-over-time")
async def get_traffic_over_time(
    range: str = Query("1h"),
    sites: str = Query(..., description="Comma-separated site ids"),
    principal: Principal = Depends(require_site_scope),
) -> Envelope[list[dict]]:
    hours = _parse_range(range)
    site_ids = principal.filter_sites([s for s in sites.split(",") if s])
    bucket_seconds = (
        _FINE_BUCKET_SECONDS if hours <= _FINE_BUCKET_RANGE_HOURS else _COARSE_BUCKET_SECONDS
    )

    client = await clickhouse.get_client()
    rows = await client.query(
        "SELECT toStartOfInterval(timestamp, INTERVAL {bucket_seconds:UInt32} SECOND) AS bucket, "
        "sum(bytes) AS total_bytes, sum(packets) AS total_packets FROM flow_record "
        "WHERE site_id IN {site_ids:Array(String)} AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR "
        "GROUP BY bucket ORDER BY bucket ASC",
        parameters={"site_ids": site_ids, "hours": hours, "bucket_seconds": bucket_seconds},
    )
    data = [
        # to_utc_iso, not a bare .isoformat(): the chart parses this back into the
        # drill-down window, and an offset-less string is read as local time there.
        {"bucket": to_utc_iso(r[0]), "total_bytes": r[1], "total_packets": r[2]}
        for r in rows.result_rows
    ]

    empty = len(data) == 0
    return Envelope.of(data, empty=empty, reason=EmptyReason.NO_TRAFFIC if empty else None)
