"""GET /flows — drill-down into individual flow records for a filtered window
(User Story 1 & 2, FR-003, FR-006), including the "outside_retention" reason
(FR-005 edge case) added in User Story 2."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope

from ..auth import require_authenticated
from ..flow_query import FlowFilter, is_outside_retention, query_flows

router = APIRouter(tags=["query"])


@router.get("/flows")
async def get_flows(
    start: datetime = Query(...),
    end: datetime = Query(...),
    site_id: str | None = Query(None),
    protocol: int | None = Query(None),
    application: str | None = Query(None),
    host: str | None = Query(None),
    page: int = Query(1, ge=1),
    _auth: str = Depends(require_authenticated),
) -> Envelope[list[dict]]:
    flt = FlowFilter(
        start=start, end=end, site_id=site_id, protocol=protocol, application=application, host=host
    )
    data = await query_flows(flt, page=page)

    if not data:
        reason = (
            EmptyReason.OUTSIDE_RETENTION
            if await is_outside_retention(flt)
            else EmptyReason.NO_TRAFFIC
        )
        return Envelope.of(data, empty=True, reason=reason)

    return Envelope.of(data, empty=False)
