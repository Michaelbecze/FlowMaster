# Contract: Query API Service

**Base path** (via Gateway): `/api/v1/query`
**Backing store**: ClickHouse (flow data), PostgreSQL (reports metadata)
**Auth**: Bearer session token or API token (see `identity-api.md`); every endpoint
enforces the caller's site scope (FR-009) server-side — never trusts a client-supplied
site filter as authorization.

| Method | Path | Purpose | Maps to |
|---|---|---|---|
| GET | `/summary?range=1h\|3h\|6h\|12h\|24h&sites=...` | Aggregated traffic volume, protocol distribution, application breakdown for the caller's authorized sites | User Story 1, FR-002 |
| GET | `/top-talkers?range=...&sites=...&limit=...` | Highest-bandwidth source IPs in range | User Story 1, FR-002 |
| GET | `/flows?start=...&end=...&site_id=...&protocol=...&application=...&host=...&page=...` | Drill-down: individual flow records matching filters | User Story 1 & 2, FR-003, FR-006 |
| GET | `/sites/status` | Per-site connectivity status (`active`/`stale`/`never_connected`) and `last_seen_at` | User Story 1, FR-004 |
| POST | `/reports` | Create a saved or ad hoc report from a filter definition | User Story 2, FR-006, FR-007 |
| GET | `/reports/{id}` | Retrieve a saved report's current results | User Story 2, FR-006 |
| GET | `/reports/{id}/export?format=csv` | Export report results in a shareable, verifiable format | User Story 2, FR-007 |

## Response conventions

- Every list/aggregate endpoint returns an explicit `"empty": true/false` plus a
  `"reason"` when empty (`"no_traffic"` vs `"outside_retention"`), implementing FR-018
  and the retention edge case — callers must never have to infer "no data" vs
  "not retained anymore" from an empty array alone.
- Every response includes `"site_status"` metadata for any site whose data may be
  incomplete (stale/offline) within the requested window, so the frontend can visibly
  flag it rather than silently under-report (FR-004).

## Performance contract

- `/summary` and `/top-talkers` (backing the live dashboard) MUST respond fast enough to
  sustain the 5-second update cadence from SC-001 under the target scale (SC-002).
- `/flows` and `/reports/*` MUST meet the <3s p95 target from SC-003 for queries within
  the configured retention window.
