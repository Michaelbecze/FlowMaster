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

    # ECharts' sankey series requires a DAG and throws on any cycle; real traffic
    # commonly has both A->B and B->A (e.g. a client/server conversation recorded as
    # two directions), which is a 2-node cycle. Collapsing each unordered pair into
    # one link (summing both directions) removes that case by construction. Longer
    # cycles (A->B->C->A) are not handled — accepted as a rare edge case, not worth
    # a general cycle-detection pass for a top-N visualization.
    pair_totals: dict[tuple[str, str], int] = {}
    for src_addr, dst_addr, total_bytes in rows.result_rows:
        key = tuple(sorted((src_addr, dst_addr)))
        pair_totals[key] = pair_totals.get(key, 0) + total_bytes

    node_names: dict[str, None] = {}
    links = []
    for (addr_a, addr_b), total_bytes in sorted(pair_totals.items(), key=lambda kv: -kv[1]):
        node_names.setdefault(addr_a, None)
        node_names.setdefault(addr_b, None)
        links.append({"source": addr_a, "target": addr_b, "value": total_bytes})

    data = {"nodes": [{"name": n} for n in node_names], "links": links}
    empty = len(links) == 0
    return Envelope.of(data, empty=empty, reason=EmptyReason.NO_TRAFFIC if empty else None)
