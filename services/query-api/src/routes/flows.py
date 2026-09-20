"""GET /flows — drill-down into individual flow records for a filtered window
(User Story 1 & 2, FR-003, FR-006), including the "outside_retention" reason
(FR-005 edge case) added in User Story 2."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope
from shared.authz import Principal, require_site_scope

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
    principal: Principal = Depends(require_site_scope),
) -> Envelope[list[dict]]:
    # A requested site outside the caller's scope yields an empty result, not a 403 —
    # consistent with the realtime channel's silent-drop rule (never confirm a site's
    # existence to a caller who isn't scoped to it).
    if site_id is not None and not principal.is_allowed(site_id):
        return Envelope.of([], empty=True, reason=EmptyReason.NO_TRAFFIC)

    flt = FlowFilter(
        start=start, end=end, site_id=site_id, protocol=protocol, application=application, host=host
    )
    allowed = None if principal.all_sites else principal.site_ids
    data = await query_flows(flt, page=page, allowed_site_ids=allowed)

    if not data:
        reason = (
            EmptyReason.OUTSIDE_RETENTION
            if await is_outside_retention(flt)
            else EmptyReason.NO_TRAFFIC
        )
        return Envelope.of(data, empty=True, reason=reason)

    return Envelope.of(data, empty=False)
