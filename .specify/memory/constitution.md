<!--
Sync Impact Report
- Version change: none (initial ratification) → 1.0.0
- Modified principles: n/a (initial ratification)
- Added sections:
  - Core Principles: I. Code Quality, II. Testing Standards, III. User Experience
    Consistency, IV. Performance Requirements
  - Technology & Security Constraints
  - Development Workflow & Quality Gates
  - Governance
- Removed sections: none
- Templates requiring follow-up:
  - .specify/templates/plan-template.md — ⚠ pending manual check
  - .specify/templates/spec-template.md — ⚠ pending manual check
  - .specify/templates/tasks-template.md — ⚠ pending manual check
  Re-run /speckit-analyze or review these templates for alignment with the four
  principles below before the next planning cycle.
- Follow-up TODOs: none.
-->

# FlowMaster Constitution

## Core Principles

### I. Code Quality
Every service or module MUST stay small, single-purpose, and readable without external
explanation. Each service owns exactly one concern (e.g., ingestion, flow storage, query,
realtime, identity, alerting) and MUST NOT read from or write to another service's data
store directly — cross-service interaction happens only through published APIs or the
event stream. Configuration (ports, connection strings, retention, feature flags) MUST
live in per-service environment configuration and MUST NOT be hardcoded. Async code MUST
NOT perform blocking I/O or CPU-heavy work on the event loop; blocking operations are
offloaded or made properly async. Code MUST NOT carry dead code, commented-out blocks, or
speculative abstractions for features not yet built. Comments are added only where the
*why* is non-obvious (e.g., a wire-format quirk, a cross-service ordering constraint);
they are not used to narrate what the code already says.
**Rationale**: The platform ingests untrusted binary network data at enterprise scale and
spans multiple independently deployable services; strict ownership boundaries and small,
well-bounded units keep the system auditable and prevent one service's internal change
from silently breaking another's correctness or security guarantees.

### II. Testing Standards
Every change to flow parsing, storage/query logic, or any service's published API or
event schema MUST be covered by an automated, assertion-based test that runs without
manual steps or a live dashboard. Manual smoke scripts MAY remain for exploratory
verification but MUST NOT be the only check for a change — they do not assert correctness
and do not run in CI. New or changed flow-parsing logic MUST include tests for at least
one valid packet and one malformed/truncated packet, since the Ingestion service
processes untrusted network input (FR-015: one bad packet MUST NOT affect processing of
others). Every service boundary crossed by another service or the frontend MUST have a
contract test validating its published API/event schema against `contracts/`, so a
breaking change is caught before it reaches a consumer. A bug fix MUST include a
regression test that fails before the fix and passes after.
**Rationale**: Once behavior spans process/network boundaries, an untested contract
change fails silently for its consumers instead of loudly at compile time; contract tests
and boundary-level assertions are what make independent service deployability safe rather
than merely convenient.

### III. User Experience Consistency
Every user-facing view — dashboard, historical reports, admin/access-control screens, and
alerts — MUST meet the same design and interaction standard; "the dashboard" is not
allowed to be the only well-finished view (FR-016). The real-time dashboard's refresh
cadence MUST stay consistent and MUST reflect new flow data within the platform's stated
latency target. Any time-range or scope filter (site, date range, protocol, application,
host) MUST apply uniformly across every chart and table it claims to filter — no view may
silently ignore an active filter. All views MUST use a single, consistent, accessible
color and component system (see the `dataviz` skill for palette and interaction rules)
rather than ad hoc per-view styling. Every view MUST define an explicit empty/no-data
state and MUST NOT render as blank or broken when no data matches the current scope or
filter (FR-018). A site that stops reporting MUST be visibly distinguished from a site
with genuinely no current traffic (FR-004), and a lost realtime connection MUST be shown
to the user rather than silently freezing. All views MUST support keyboard navigation and
screen-reader use (FR-016).
**Rationale**: An enterprise operations or compliance audience judges the product by
whether every screen — not just the flagship dashboard — is trustworthy and usable;
inconsistency or silent gaps in any one view undermine confidence in all of them.

### IV. Performance Requirements
The Ingestion service MUST NOT block on downstream writes or drop packets under normal
enterprise traffic bursts; it publishes to the event stream rather than writing
synchronously, so ingest throughput is decoupled from storage or query load. The
Flow-Writer service MUST batch writes into flow storage so ingest volume does not degrade
query latency. The retention purge process MUST run as a job independent of live ingest
and MUST NOT block the Query API or the realtime path. Dashboard-facing and query
endpoints MUST meet their stated latency targets (new flow data reflected within the
platform's real-time target; filtered historical queries within the platform's
query-performance target) under normal load. If ingest capacity is exceeded, the system
MUST make the resulting data loss visible (e.g., a loss counter or indicator) rather than
silently falling behind (FR-014). Any change that adds a synchronous, per-flow, or
per-request expensive operation (e.g., a cross-service call in a hot path, an unbounded
scan) MUST be justified in the change description and, where possible, gated, cached, or
moved off the hot path.
**Rationale**: The platform's value is real-time, enterprise-scale visibility; a service
that silently falls behind under load, or an API that can't sustain its own refresh
cadence, defeats the product's core promise regardless of how correct its logic is.

## Technology & Security Constraints

The platform's architecture (see `specs/001-enterprise-netflow-platform/plan.md`) is a
set of independently deployable, single-concern services. Backend services MUST be
Python 3.11+ using FastAPI for their HTTP layer. The frontend MUST be TypeScript with
React 18, built as a componentized SPA, so that dashboard, reports, admin, and alerts can
each be developed and reviewed as separate, design-system-consistent units. Services
communicate over a Kafka-compatible event stream (Apache Kafka or a Kafka-API-compatible
alternative such as Redpanda) as the durable flow-record backbone; direct
service-to-service database access is prohibited (see Principle I). Storage is polyglot
and chosen per access pattern: **ClickHouse** for high-volume flow-record storage and
windowed aggregation, **PostgreSQL** for relational metadata (organizations, users,
roles, sites, alert rules, reports, audit log), and **Redis** for ephemeral real-time
state, WebSocket fan-out, alert de-duplication, and API rate-limit counters. A new
runtime dependency or storage technology beyond this set MUST be justified against this
already-polyglot footprint — prefer an existing service's technology before introducing
another one.

Because the Ingestion service accepts unauthenticated flow packets from the network, all
packet parsing MUST be defensive: length-validated unpacking that rejects malformed or
truncated packets without raising an unhandled exception that could crash the listener,
and without one bad packet affecting any other (FR-015). The v1 API MUST support
authenticated machine-client access (API tokens) separate from interactive user login,
MUST be rate-limited, and MUST be documented and versioned (FR-019). User authentication
is platform-managed (username/password) for v1; the identity/role/scope model MUST NOT
preclude adding external SSO/IdP integration in a later release (FR-020). Secrets or
credentials MUST NOT be committed to version control; per-service environment
configuration stays out of the repository per `.gitignore`.

## Development Workflow & Quality Gates

Every service MUST have automated unit tests plus `pytest`/`pytest-asyncio`
service-level integration tests run against real dependencies (PostgreSQL, ClickHouse,
Redis, the event stream) via Testcontainers — not against mocks standing in for another
service's storage. Every published API or event schema MUST have a contract test
validated against `contracts/` before a change to that boundary is considered complete
(Principle II). Frontend changes MUST be manually exercised in a browser against a
running stack, per affected page (dashboard, reports, admin, alerts) — type-checking or
unit tests alone do not verify rendering or interaction behavior — and MUST have Vitest
unit coverage plus Playwright end-to-end coverage for the user journeys they affect.
Changes that alter a service's configuration defaults, a public API/event contract, or
retention/alerting behavior MUST update the corresponding `contracts/` document (and
`README.md` where user-facing) in the same change so documentation does not drift from
behavior.

## Governance

This constitution supersedes ad hoc practice for FlowMaster development. Amendments are
made by editing this file directly, updating the version per the policy below, and
recording the change in a Sync Impact Report comment at the top of the file.

Versioning policy (semantic versioning applied to governance):
- **MAJOR**: Backward-incompatible principle or constraint removal or redefinition.
- **MINOR**: A new principle or section is added, or existing guidance is materially
  expanded.
- **PATCH**: Wording, clarification, or typo fixes with no semantic change.

Every change reviewed under this project SHOULD be checked against the four Core
Principles above; a change that knowingly violates one MUST state why, following the plan
template's own Constitution Check / Complexity Tracking process (as demonstrated in
`specs/001-enterprise-netflow-platform/plan.md`) rather than silently deviating.
Complexity that conflicts with Principle I (Code Quality) MUST be justified, not silently
introduced.

**Version**: 1.0.0 | **Ratified**: 2026-09-19 | **Last Amended**: 2026-09-19
