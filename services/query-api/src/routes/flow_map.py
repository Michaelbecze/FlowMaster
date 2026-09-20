"""GET /flow-map — top source -> destination traffic pairs for the Sankey diagram.

Not part of the original contracts/query-api.md table; added alongside it (same
envelope conventions, same site-scope enforcement) to restore the "Flow Map" Sankey
view from the single-process dashboard that inspired this platform's User Story 1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from shared.api.envelope import EmptyReason, Envelope
from shared.authz import Principal, require_site_scope

from .. import clickhouse
from .summary import _parse_range

router = APIRouter(tags=["query"])

_DEFAULT_LIMIT = 15


@router.get("/flow-map")
async def get_flow_map(
    range: str = Query("1h"),
    sites: str = Query(..., description="Comma-separated site ids"),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=50),
    principal: Principal = Depends(require_site_scope),
) -> Envelope[dict]:
    hours = _parse_range(range)
    site_ids = principal.filter_sites([s for s in sites.split(",") if s])

    client = await clickhouse.get_client()
    rows = await client.query(
        "SELECT src_addr, dst_addr, sum(bytes) AS total_bytes FROM flow_record "
        "WHERE site_id IN {site_ids:Array(String)} AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR "
        "AND src_addr != dst_addr "
        "GROUP BY src_addr, dst_addr ORDER BY total_bytes DESC LIMIT {limit:UInt32}",
        parameters={"site_ids": site_ids, "hours": hours, "limit": limit},
    )

    # Directions are reported as measured — each row is one src -> dst pair, already
    # ordered by volume.
    #
    # This used to collapse every unordered pair into a single link, summing both
    # directions, because ECharts' sankey throws on a cycle and a client/server
    # conversation recorded as both A->B and B->A is a 2-node cycle. That workaround
    # cost more than it bought: it summed opposing directions into one number, and
    # keying on `sorted((src, dst))` meant the surviving link pointed whichever way
    # sorted first — so a link could be drawn backwards relative to the traffic it
    # described. It also only ever covered 2-node cycles; A->B->C->A still threw.
    #
    # The chart now renders as a strict two-column source -> destination diagram
    # (FlowMapSankey.tsx gives an address distinct identities per side), so no cycle
    # of any length is representable and none of that is needed.
    node_names: dict[str, None] = {}
    links = []
    for src_addr, dst_addr, total_bytes in rows.result_rows:
        node_names.setdefault(src_addr, None)
        node_names.setdefault(dst_addr, None)
        links.append({"source": src_addr, "target": dst_addr, "value": total_bytes})

    data = {"nodes": [{"name": n} for n in node_names], "links": links}
    empty = len(links) == 0
    return Envelope.of(data, empty=empty, reason=EmptyReason.NO_TRAFFIC if empty else None)
