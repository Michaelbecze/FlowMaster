# Implementation Plan: Enterprise NetFlow Collection & Analytics Platform

**Branch**: `001-enterprise-netflow-platform` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-enterprise-netflow-platform/spec.md`

## Summary

Evolve FlowMaster from a single-process, single-node NetFlow v5 collector into an
enterprise-ready platform: a set of independently deployable and scalable services
communicating over an event stream and REST APIs, backed by storage engines chosen for
flow-analytics scale, and fronted by a dynamic, componentized web dashboard. The
architecture is explicitly organized so that ingestion load from one site, a historical
report query, a UI deploy, and alert evaluation can each scale and fail independently —
directly addressing spec requirements FR-001–FR-021 and success criteria SC-001–SC-009
(100+ concurrent sites, sub-5s dashboard latency, sub-3s p95 historical queries, 99.9%
uptime).

## Technical Context

**Language/Version**: Python 3.11+ for all backend services; TypeScript 5.x for the frontend.

**Primary Dependencies**: FastAPI (per-service HTTP layer, continued from the existing
project), an async Kafka/streaming client (e.g., `aiokafka`) for the event backbone,
`asyncpg` for PostgreSQL access, a ClickHouse async client for flow storage/query,
`redis` (async) for real-time state and pub/sub. Frontend: React 18 + TypeScript, Vite
build tooling, a charting library (e.g., ECharts or Recharts, per the `dataviz` skill's
palette/interaction guidance already referenced in the constitution), and a WebSocket
client for live updates.

**Storage**: Polyglot, chosen per access pattern — see `research.md` for the
decision/rationale/alternatives on each:
- **ClickHouse** — high-volume flow record storage and time-window aggregation (replaces `aiosqlite` for flow data).
- **PostgreSQL** — relational metadata: organizations, users, roles, sites, alert rules, saved reports, audit log.
- **Redis** — ephemeral real-time aggregate state, WebSocket fan-out, alert de-duplication state, API rate-limit counters.
- **Kafka-compatible event stream** (Apache Kafka or a Kafka-API-compatible alternative such as Redpanda) — durable flow-record backbone decoupling ingestion from its consumers.

**Testing**: `pytest` + `pytest-asyncio` per service (unit + service-level integration
tests against real Postgres/ClickHouse/Redis/Kafka via Testcontainers, per constitution
Testing Standards); contract tests validating each service's published API/event schema
against `contracts/`; frontend unit tests with Vitest and end-to-end flows with
Playwright.

**Target Platform**: Linux containers, orchestrator-agnostic — Docker Compose for local
development, Kubernetes-compatible manifests for production (specific hosting/compliance
environment is out of scope per spec Assumptions).

**Project Type**: Web application — multiple backend services + API gateway + dynamic
frontend (see Project Structure below).

**Performance Goals** (from spec Success Criteria):
- Dashboard reflects new flow data within 5s of ingestion (SC-001).
- 100+ concurrently active sites ingested without visible lag or data loss (SC-002).
- Filtered historical queries over 30 days return in <3s for 95% of queries (SC-003).
- Alerts delivered within 60s of the triggering condition (SC-007).

**Constraints**:
- Single-organization tenancy for v1 (FR-021) — no cross-tenant isolation requirement, but access control must still fully scope data by site/role (FR-008, FR-009).
- Platform-managed authentication only for v1 (FR-020) — no external IdP integration required yet, but the identity model must not preclude adding SSO later.
- v1 API must be documented, versioned, and support machine-client auth + rate limiting (FR-019).
- 99.9% monthly uptime target for ingestion + live dashboard (SC-008).

**Scale/Scope**: 100+ flow-exporting sites, single organization, 4 prioritized user
journeys (real-time dashboard, historical reporting, admin/access control, alerting).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Section | Status | Notes |
|---|---|---|
| I. Code Quality (small, single-purpose, non-cross-mixed modules; config not hardcoded; no blocking I/O on event loop; no dead code) | **PASS** | Generalizes cleanly to service boundaries — each service owns one concern (ingestion, storage-write, query, realtime, identity, alerting) and does not reach into another's data store directly. Configuration is per-service, env-based, never hardcoded. |
| II. Testing Standards (automated tests for parsing/storage/API changes; malformed-input tests; regression tests for bug fixes) | **PASS** | Extended to every service boundary; ingestion parsing tests (valid + malformed packet) carry over unchanged from the existing project's requirement. Contract tests added between services since there are now network boundaries that didn't exist in the single-process design. |
| III. User Experience Consistency (refresh cadence, uniform time-range filtering, consistent chart color system, explicit empty states, visible reconnect handling) | **PASS** | Carried forward as hard requirements on the Realtime and Query API services and the frontend; FR-016–FR-018 in the spec extend this to *all* views, not just the dashboard. |
| IV. Performance Requirements (non-blocking listener, batched writes, non-blocking retention purge, fast API under refresh cadence) | **PASS** | Maps onto the new architecture: Ingestion service never blocks on writes (publishes to the event stream instead), Flow-Writer batches into ClickHouse, retention purge is a scheduled job independent of the Query API, Query API is a dedicated service sized for read latency. |
| Technology & Security Constraints — stack locked to `aiosqlite` + single-file vanilla-JS frontend; new dependencies must be justified against a minimal footprint | **FAIL — justified** | This plan replaces `aiosqlite` with ClickHouse/PostgreSQL/Redis and the single-file frontend with a componentized React/TypeScript SPA, and introduces a streaming backbone. This is a direct, deliberate departure from the current constitution's technology constraint, done at the user's explicit request for an enterprise, microservices-oriented architecture that the current constraint cannot satisfy (see spec Assumptions and Success Criteria SC-002/SC-003). See **Complexity Tracking** below for the specific justification of each new dependency. **Recommendation**: ratify a constitution amendment (`/speckit-constitution`) updating this section before `/speckit-tasks`/`/speckit-implement`, so the governing document matches the direction the project has now committed to, rather than carrying a permanently-overridden constraint. |
| Technology & Security Constraints — defensive packet parsing (validate lengths, never crash listener on malformed input) | **PASS** | Unchanged requirement on the Ingestion service specifically; this is independent of storage/frontend technology choices. |
| Development Workflow & Quality Gates (frontend changes manually exercised in browser; collector/storage changes tested; config-default changes update docs) | **PASS** | Carried forward; frontend manual verification now applies per-page (dashboard, reports, admin, alerts) rather than a single file. |

**Net gate result**: One section fails against the *current* constitution text, and is
carried forward as an explicitly justified, documented deviation per the process the
constitution's own template provides (see Complexity Tracking). This plan proceeds on
that basis; it does not silently ignore the gate.

## Project Structure

### Documentation (this feature)

```text
specs/001-enterprise-netflow-platform/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
services/
├── ingestion/            # NetFlow UDP listener(s); parses + validates; publishes to event stream
│   ├── src/
│   └── tests/
├── flow-writer/           # Consumes event stream; batches flow records into ClickHouse; runs retention purge
│   ├── src/
│   └── tests/
├── query-api/             # REST API for dashboard summaries, drill-down, historical queries, reports/export
│   ├── src/
│   └── tests/
├── realtime/              # Consumes event stream; maintains rolling aggregates in Redis; pushes updates over WebSocket
│   ├── src/
│   └── tests/
├── identity/              # Users, roles, sites/exporters, auth (session + API tokens), audit log (PostgreSQL)
│   ├── src/
│   └── tests/
└── alerting/              # Alert rule evaluation against the event stream; notification delivery + de-dup
    ├── src/
    └── tests/

gateway/                   # API gateway / BFF: single entry point for the frontend, auth validation, request routing
├── src/
└── tests/

frontend/                  # Dynamic SPA (React + TypeScript) — dashboard, reports, admin, alerts
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

packages/shared/           # Shared flow-record event schema, OpenAPI contracts, common types used by 2+ services
└── ...

infra/
├── docker-compose.yml      # Local dev: all services + Postgres, ClickHouse, Redis, Kafka-compatible broker
└── k8s/                    # Production-oriented manifests (structure only; filled during implementation)

specs/                      # spec-kit artifacts (this feature's spec/plan/tasks)
```

**Structure Decision**: Web-application-plus-services layout (a superset of the
template's Option 2). Each bounded context from the spec's prioritized user stories maps
to exactly one service — `ingestion`/`flow-writer` → P1 (real-time visibility) and P2
(historical data foundation), `query-api` → P2 (reporting), `identity` → P3
(access/admin), `alerting` → P4 — so each user story remains independently testable and
deployable, per the spec template's own requirement for user stories. `gateway` and
`frontend` are shared across all stories since every story is user-facing. `packages/shared`
holds only cross-service contracts (event schema, OpenAPI types), not shared business
logic, to avoid re-coupling services through a shared library.

## Complexity Tracking

> Required because the Constitution Check above has one justified `FAIL`.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Six independently deployable services instead of one process | SC-002 (100+ concurrent sites) and SC-008 (99.9% uptime) require that ingestion load, historical query load, and a frontend/API deploy cannot take each other down; each service also corresponds 1:1 to an independently-testable prioritized user story (P1–P4) as the spec template requires | A single process (current FlowMaster architecture) was explicitly built and tuned for home/SOHO scale; scaling it further would require re-introducing the same isolation internally via threads/queues without gaining independent deployability, test isolation, or fault containment |
| Replacing `aiosqlite` with ClickHouse (flow data) + PostgreSQL (metadata) | SC-003 (sub-3s p95 queries over 30 days of retained flow data) and FR-005 (configurable, non-silent retention) require a storage engine built for high-volume append + windowed aggregation; SQLite is single-writer and does not support safe concurrent access from multiple services | Tuning SQLite (WAL mode, sharding by time) does not resolve concurrent multi-service writers and would still fall well short of ClickHouse's aggregation performance at 100+ site scale, without saving meaningful operational complexity |
| Kafka-compatible event stream as the ingestion backbone | Decouples Ingestion from Flow-Writer, Realtime, and Alerting so each can scale/fail independently (the constitution's own "concerns are not cross-mixed" principle, applied at service granularity), and gives an observable consumer-lag signal to satisfy FR-014 (visible ingest overload rather than silent loss) | Direct service-to-service calls or a shared database as the hand-off point would re-couple ingestion throughput to the slowest consumer, reintroducing the single point of failure the multi-service design exists to remove |
| React/TypeScript SPA instead of the single-file vanilla-JS dashboard | FR-016 requires enterprise-grade, accessible UI consistency across dashboard, reports, admin, and alerts — four to five distinct application areas, not one page; "Graphic" and "Usability" are stated as top priorities in the spec input | A single HTML file stops being readable or reusable once it must serve several distinct, componentized screens with shared design-system elements — the same Code Quality concern (Principle I) that justifies small modules in the backend |
| Redis alongside PostgreSQL and ClickHouse (three storage technologies) | Redis serves a different job than the other two: sub-second live aggregate state and WebSocket fan-out for SC-001 (5s dashboard latency) and alert de-duplication state for FR-013 — neither PostgreSQL nor ClickHouse are built for this access pattern | Serving live dashboard state from ClickHouse directly would require re-querying/aggregating on every update tick across all connected clients, which cannot meet the 5-second, many-concurrent-viewer latency target at 100+ site scale |

## Post-Design Constitution Re-Check

*Performed after Phase 1 (`data-model.md`, `contracts/`, `quickstart.md`).*

No new violations were introduced beyond the single justified deviation above. Notably,
the design *reinforces* the passing principles rather than eroding them further:
`data-model.md` keeps each service's data in exactly one owning store (no service reads
another's table directly — Principle I); every `contracts/*.md` file specifies the
empty-state and site-status conventions required by FR-018/Principle III; and
`event-flow-record.md` makes ingest-overload visibility (Principle IV / FR-014) an
explicit operational contract rather than an afterthought. The recommendation to ratify
a constitution amendment before `/speckit-tasks` stands unchanged.
