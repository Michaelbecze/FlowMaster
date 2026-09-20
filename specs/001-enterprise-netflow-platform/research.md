# Phase 0 Research: Enterprise NetFlow Collection & Analytics Platform

All Technical Context items were resolvable from the feature spec, the user's explicit
direction (microservices, fast/scalable databases, dynamic frontend), and the existing
FlowMaster project as a behavioral reference. No `NEEDS CLARIFICATION` markers remain.
Each decision below records the alternatives considered so the rationale survives
independent of this document's author.

## 1. Flow-record storage engine

**Decision**: ClickHouse.

**Rationale**: Flow records are an append-mostly, extremely high-volume, wide-and-narrow
dataset queried mainly through time-windowed aggregation (top talkers, protocol mix,
traffic-volume-over-time) — ClickHouse's columnar storage and vectorized aggregation are
built for exactly this pattern, and it is the storage engine used by comparable
open-source NetFlow/IPFIX analytics collectors (e.g., Akvorado) at multi-site,
high-throughput scale. It directly targets SC-002 (100+ concurrent sites) and SC-003
(sub-3s p95 historical queries over 30 days).

**Alternatives considered**:
- **TimescaleDB (PostgreSQL extension)** — attractive for operational simplicity (one
  database technology for both metadata and flows), but row-store-based time-series
  performance falls behind a columnar engine at this cardinality/aggregation profile, and
  mixing high-volume flow writes with transactional metadata writes on the same engine
  risks the two workloads contending for resources.
- **InfluxDB** — strong at single-metric time series, weaker at the multi-dimensional
  group-by (by site, protocol, application, host) that the dashboard and reports need.
- **Continuing with SQLite/aiosqlite at larger scale** — rejected; see plan.md
  Complexity Tracking (single-writer, not built for concurrent multi-service access or
  this aggregation volume).

## 2. Metadata storage engine

**Decision**: PostgreSQL.

**Rationale**: Organizations, users, roles, sites, alert rules, saved reports, and the
audit log are comparatively low-volume, relational, and require transactional integrity
(e.g., role changes must not partially apply). PostgreSQL is the mature default for this
access pattern and integrates cleanly with standard RBAC and audit-log patterns.

**Alternatives considered**:
- **Storing metadata in ClickHouse alongside flow data** — rejected; ClickHouse is
  optimized for append-heavy analytics, not transactional updates (e.g., revoking a
  user's access must take effect immediately and atomically, per FR-008/FR-009).
- **A document store (e.g., MongoDB)** — rejected; the metadata (users/roles/sites) is
  inherently relational (many-to-many role/site scoping), which a relational schema
  expresses and enforces more directly than a document model.

## 3. Real-time state and fan-out

**Decision**: Redis.

**Rationale**: The 5-second dashboard-latency target (SC-001) and per-connection
WebSocket fan-out to potentially many concurrent viewers need sub-millisecond read/write
of small, frequently-updated aggregate state — a job neither ClickHouse (analytical,
higher query latency) nor PostgreSQL (transactional, not built for pub/sub fan-out) are
suited for. Redis also provides a natural home for alert de-duplication state (FR-013)
and API rate-limit counters (FR-019).

**Alternatives considered**:
- **Re-querying ClickHouse on every refresh tick per connected client** — rejected;
  does not scale with concurrent viewers and cannot reliably hit the 5-second target at
  100+ site scale.
- **In-process memory per service instance** — rejected; breaks the moment more than one
  instance of the Realtime service runs, which independent scalability requires.

## 4. Event backbone for decoupling ingestion from consumers

**Decision**: A Kafka-API-compatible event stream (Apache Kafka, or a lighter-weight
Kafka-API-compatible alternative such as Redpanda — the specific distribution is an
implementation/ops decision deferred to `tasks.md`, not a plan-level architectural
choice).

**Rationale**: Ingestion must never block on the speed of its slowest consumer
(Flow-Writer, Realtime, Alerting each read the same flow data for different purposes).
A durable, partitioned log lets each consumer read at its own pace, exposes consumer lag
as an observable signal (satisfying FR-014's requirement that overload be visible rather
than silent), and is a common integration point enterprises already use for SIEM/data
pipeline connectivity (supporting FR-019).

**Alternatives considered**:
- **Redis Streams** — simpler operationally, but weaker durability/replay guarantees and
  ecosystem support for the kind of long-retention, multi-consumer replay enterprise
  customers may expect from an integration point.
- **Direct HTTP/gRPC calls from Ingestion to each consumer** — rejected; re-couples
  ingestion throughput to every consumer's availability and speed, defeating the purpose
  of decoupling.
- **A shared database table as a queue** — rejected; does not scale to the ingest volume
  and reintroduces a single write bottleneck.

## 5. Frontend architecture

**Decision**: React 18 + TypeScript, built with Vite, using a charting library consistent
with the `dataviz` skill's palette/interaction guidance already referenced in the
project's constitution (e.g., ECharts or Recharts — final selection is an implementation
detail for `tasks.md`).

**Rationale**: The platform now has several distinct, componentized screens (live
dashboard, historical reports, admin/access control, alerts) rather than one page, so a
component framework is needed to keep FR-016 (consistent, accessible UI across all views)
achievable without duplicating markup. React + TypeScript is chosen over a full
metaframework (e.g., Next.js) because this is an authenticated, non-SEO-sensitive
internal/enterprise application — server-side rendering is not required, and a plain SPA
keeps the build/deploy surface simpler.

**Alternatives considered**:
- **Continuing with a single-file vanilla-JS dashboard** — rejected; see plan.md
  Complexity Tracking (does not scale to multiple screens without duplication).
- **A full SSR framework (Next.js, Remix)** — rejected as unnecessary complexity; no SEO
  or first-byte-content requirement exists for an authenticated internal dashboard.
- **A different component framework (Vue, Svelte)** — viable alternatives with similar
  properties; React is chosen for ecosystem maturity around enterprise dashboard/chart
  component libraries, not a hard technical requirement.

## 6. API style between frontend and backend

**Decision**: REST/JSON over HTTP for request/response operations (queries, admin CRUD,
alert-rule CRUD), plus WebSocket for server-push real-time updates. All backend services
expose FastAPI-generated OpenAPI schemas; the Gateway aggregates them for a single
documented v1 API surface (FR-019).

**Rationale**: REST+OpenAPI is directly and automatically documentable (FR-019's
"documented, versioned" requirement), widely understood by enterprise integrators, and
consistent with the existing project's FastAPI usage — no new paradigm for the team to
adopt. WebSocket is kept specifically for the real-time push path (SC-001), where
request/response polling would either miss the latency target or waste resources.

**Alternatives considered**:
- **GraphQL** — offers flexible querying but adds a second query paradigm for
  integrators to learn alongside the documented REST API, without a clear win for this
  domain's relatively fixed set of dashboard/report queries.
- **gRPC for all inter-service and external communication** — good fit for internal
  service-to-service calls, but a poor fit for external enterprise integrators (FR-019),
  who overwhelmingly expect REST/HTTP; introducing both gRPC and REST was rejected as
  unnecessary duplication for v1.
