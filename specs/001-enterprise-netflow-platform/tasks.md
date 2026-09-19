---

description: "Task list for Enterprise NetFlow Collection & Analytics Platform"
---

# Tasks: Enterprise NetFlow Collection & Analytics Platform

**Input**: Design documents from `/specs/001-enterprise-netflow-platform/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md,
`.specify/memory/constitution.md` (v1.0.0)

**Tests**: Included. `plan.md`'s Technical Context commits to `pytest`/`pytest-asyncio` +
Testcontainers integration tests, contract tests per service boundary, and Vitest/Playwright
for the frontend; the constitution's Testing Standards principle makes these mandatory, not
optional, for this feature.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P4) so each story is
independently implementable, testable, and deployable, per plan.md's one-service-per-story
mapping (`ingestion`/`flow-writer` → P1/P2, `query-api` → P2, `identity` → P3, `alerting` → P4;
`gateway` and `frontend` are shared across all stories).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Every task includes an exact file path

## Path Conventions (per plan.md Project Structure)

```text
services/{ingestion,flow-writer,query-api,realtime,identity,alerting}/{src,tests,migrations}
gateway/{src,tests}
frontend/src/{components,pages,services}, frontend/tests
packages/shared/src/shared/
infra/{docker-compose.yml,k8s}
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository scaffolding for the multi-service architecture approved in plan.md

- [X] T001 Create the repository directory structure per plan.md Project Structure: `services/{ingestion,flow-writer,query-api,realtime,identity,alerting}/{src,tests}`, `gateway/{src,tests}`, `frontend/src/{components,pages,services}`, `frontend/tests`, `packages/shared`, `infra/k8s`
- [X] T002 [P] Initialize each backend service (`ingestion`, `flow-writer`, `query-api`, `realtime`, `identity`, `alerting`, `gateway`) as a Python 3.11+ package with FastAPI, `pytest`, and `pytest-asyncio` declared in its own `pyproject.toml`
- [X] T003 [P] Initialize `frontend/` as a Vite + React 18 + TypeScript project with `package.json`, `tsconfig.json`, and Vitest + Playwright dev dependencies
- [X] T004 [P] Initialize `packages/shared` as a Python package (`packages/shared/pyproject.toml`) for cross-service event/contract types, installable as a dependency by every backend service
- [X] T005 [P] Configure backend linting/formatting (`ruff` + `black` config) at the repository root and frontend linting/formatting (ESLint + Prettier config) in `frontend/`
- [X] T006 [P] Create `infra/docker-compose.yml` with service placeholders for `postgres`, `clickhouse`, `redis`, and the Kafka-compatible broker (filled in during Phase 2)
- [X] T007 Extend the repository `.gitignore` with Python (`__pycache__/`, `*.pyc`, `.venv/`) and Node (`node_modules/`, `dist/`) patterns for the new service and frontend directories
- [X] T008 [P] Create `infra/k8s/README.md` noting production manifests are filled in during Phase 7 hardening (structure-only per plan.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-service plumbing every user story depends on — event schema, base data model,
authentication, and API routing

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T009 Define the `FlowRecordEvent` schema (`schema_version`, `site_id`, `observed_at`, `ingested_at`, `src_addr`, `dst_addr`, `src_port`, `dst_port`, `protocol`, `application`, `bytes`, `packets`, `direction`) as a shared type in `packages/shared/src/shared/events/flow_record.py`, matching `contracts/event-flow-record.md` exactly
- [X] T010 [P] Define shared response-envelope types (`empty`/`reason` with values `"no_traffic"`/`"outside_retention"`, `site_status`) in `packages/shared/src/shared/api/envelope.py` per `contracts/query-api.md` Response Conventions
- [X] T011 Add `postgres`, `clickhouse`, `redis`, and the Kafka-compatible broker (e.g. Redpanda) with persistent volumes to `infra/docker-compose.yml`, plus containers for all six backend services, `gateway`, and the frontend dev server (depends on T006)
- [X] T012 Add `flow-records.v1` topic provisioning (partition key: `site_id`) to `infra/docker-compose.yml` init config per `contracts/event-flow-record.md`
- [X] T013 [P] Write the PostgreSQL migration for `Organization` (`id` UUID PK, `name`, `retention_policy_id` FK) in `services/identity/migrations/0001_organization.sql`
- [X] T014 [P] Write the PostgreSQL migration for `RetentionPolicy` (`id` UUID PK, `organization_id` FK, `duration_days` Integer, `updated_at`, `updated_by` FK→User) in `services/identity/migrations/0002_retention_policy.sql`
- [X] T015 [P] Write the PostgreSQL migration for `Site` (`id` UUID PK, `organization_id` FK, `name`, `network_identity`, `status` enum `active`\|`stale`\|`never_connected`, `last_seen_at` nullable, `created_at`, `created_by` FK→User) in `services/identity/migrations/0003_site.sql`
- [X] T016 [P] Write the PostgreSQL migration for `User` (`id` UUID PK, `organization_id` FK, `email` unique, `password_hash` nullable, `status` enum `active`\|`disabled`, `created_at`) in `services/identity/migrations/0004_user.sql`
- [X] T017 [P] Write the PostgreSQL migration for `Role` (`id` UUID PK, `name`, `permissions` JSONB) in `services/identity/migrations/0005_role.sql`
- [X] T018 Write the PostgreSQL migration for the `UserRoleAssignment` join table (`user_id` FK, `role_id` FK, `site_id` FK nullable = org-wide scope) in `services/identity/migrations/0006_user_role_assignment.sql` (depends on T015, T016, T017)
- [X] T019 Write the ClickHouse migration creating the `FlowRecord` table (`timestamp`, `site_id`, `src_addr`, `dst_addr`, `src_port`, `dst_port`, `protocol`, `application`, `bytes`, `packets`, `direction`, `ingested_at`) with TTL bound to the organization's configured retention window in `services/flow-writer/migrations/0001_flow_record.sql`
- [X] T020 Implement password hashing and session-token issuance/validation (`POST /auth/login`, `POST /auth/logout`) in `services/identity/src/auth/session.py`
- [X] T021 Implement API-token issuance/revocation (`POST /auth/tokens`, `DELETE /auth/tokens/{id}`), scoped to the caller's own permissions, in `services/identity/src/auth/api_tokens.py`
- [X] T022 Implement minimal `Site` create/list (`GET/POST /sites`) in `services/identity/src/sites/router.py`, so Ingestion can attribute flows before the full admin onboarding flow lands in US3 (depends on T015)
- [X] T023 Implement the Gateway routing table in `gateway/src/routing.py` matching `contracts/gateway-routing.md` (public login route, bearer-token routes for query/alerting, WebSocket upgrade auth for realtime)
- [X] T024 Implement Gateway bearer-token validation middleware in `gateway/src/middleware/auth.py`, validating tokens against `services/identity`'s session/API-token verification (depends on T020, T021)
- [X] T025 Implement Gateway Redis-backed per-token rate-limiting middleware in `gateway/src/middleware/rate_limit.py` per FR-019
- [X] T026 [P] Implement shared structured (JSON, request-scoped) logging in `packages/shared/src/shared/logging.py`, imported by every backend service
- [X] T027 [P] Implement per-service environment configuration loading (no hardcoded ports/connection strings) in `services/*/src/config.py` and `gateway/src/config.py`
- [X] T028 Scaffold the frontend app shell in `frontend/src/App.tsx` with routes for `/dashboard`, `/reports`, `/admin`, `/alerts`, an auth context/guard in `frontend/src/services/auth.ts` calling `POST /api/v1/identity/auth/login`, and a shared layout using the `dataviz` skill's palette (depends on T020)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Real-Time Network Traffic Visibility (Priority: P1) 🎯 MVP

**Goal**: A NOC engineer sees live, continuously-updating, correctly-attributed traffic across
every monitored site on one dashboard, with drill-down into underlying flow records.

**Independent Test**: Point multiple simulated flow exporters at the platform and confirm the
dashboard reflects aggregated, correctly-attributed traffic within 5 seconds, with drill-down
from a summary chart into the underlying flow records for a chosen time window.

### Tests for User Story 1

- [X] T029 [P] [US1] Contract test asserting Ingestion-published events match the `FlowRecordEvent` schema in `services/ingestion/tests/contract/test_flow_record_event.py`
- [X] T030 [P] [US1] Parser test for one valid NetFlow v5 packet (generalized from the existing project's `test_flow.py`) in `services/ingestion/tests/test_netflow_v5_parser.py`
- [X] T031 [P] [US1] Parser test for a malformed/truncated NetFlow v5 packet asserting rejection without an unhandled exception and without affecting subsequent packets (FR-015) in `services/ingestion/tests/test_netflow_v5_parser.py`
- [X] T032 [P] [US1] Flow-Writer integration test (Testcontainers: broker + ClickHouse) verifying batched writes and dedupe-on-replay in `services/flow-writer/tests/test_batch_writer.py`
- [X] T033 [P] [US1] Realtime integration test (Testcontainers: Redis) verifying rolling-aggregate updates and the active→stale transition after the configured threshold in `services/realtime/tests/test_aggregate_cache.py`
- [X] T034 [P] [US1] Contract test for `GET /summary`, `/top-talkers`, `/sites/status`, `/flows` in `services/query-api/tests/contract/test_query_endpoints.py`, asserting the `empty`/`reason` and `site_status` response conventions
- [X] T035 [US1] End-to-end integration test automating `quickstart.md` Scenario 1 (onboard site, send synthetic flows, dashboard reflects traffic within 5s, drill-down works, stale-site indication) in `services/query-api/tests/integration/test_scenario_realtime_visibility.py`

### Implementation for User Story 1

- [X] T036 [P] [US1] Implement the asyncio UDP NetFlow v5 listener (generalized from the existing project's `collector/listener.py`) in `services/ingestion/src/listener.py`, non-blocking per constitution Principle IV
- [X] T037 [P] [US1] Implement the NetFlow v5 binary packet parser with length-validated, defensive unpacking (generalized from the existing project's `collector/netflow_v5.py`) in `services/ingestion/src/netflow_v5.py`, rejecting malformed/truncated packets per FR-015
- [X] T038 [US1] Implement site attribution (`network_identity` → `site_id` lookup) and malformed-packet-count + ingest-lag metrics (FR-014) in `services/ingestion/src/attribution.py` (depends on T022, T037)
- [X] T039 [US1] Implement the Kafka-compatible producer publishing validated flows as `FlowRecordEvent` to `flow-records.v1`, partitioned by `site_id`, in `services/ingestion/src/producer.py` (depends on T009, T036, T037, T038)
- [X] T040 [P] [US1] Implement the Flow-Writer consumer with idempotent dedupe (`site_id` + `observed_at` + src/dst addr+port + `protocol`) in `services/flow-writer/src/consumer.py`
- [X] T041 [US1] Implement the batched ClickHouse writer in `services/flow-writer/src/batch_writer.py`, sized so ingest volume does not degrade query latency (depends on T019, T040)
- [X] T042 [US1] Implement the retention purge job in `services/flow-writer/src/retention_purge.py`, scheduled independently of ingest/query and driven by `RetentionPolicy.duration_days` (FR-005)
- [X] T043 [P] [US1] Implement the Realtime Kafka consumer maintaining the Redis rolling-aggregate cache (volume, protocol mix, top talkers) per site/org scope in `services/realtime/src/aggregator.py`
- [X] T044 [US1] Implement site staleness detection and `site_status_changed` event emission in `services/realtime/src/staleness.py` (depends on T043)
- [X] T045 [US1] Implement the `/api/v1/realtime` WebSocket endpoint per `contracts/realtime-channel.md` (scope-filtered subscription, `stats_update` push ≥1/5s, immediate push on reconnect, silent-drop of out-of-scope site requests) in `services/realtime/src/websocket.py` (depends on T043, T044)
- [X] T046 [P] [US1] Implement `GET /summary` in `services/query-api/src/routes/summary.py`, enforcing caller site-scope server-side (FR-009)
- [X] T047 [P] [US1] Implement `GET /top-talkers` in `services/query-api/src/routes/top_talkers.py`
- [X] T048 [P] [US1] Implement `GET /sites/status` in `services/query-api/src/routes/site_status.py`
- [X] T049 [US1] Implement `GET /flows` drill-down (filters: `start`, `end`, `site_id`, `protocol`, `application`, `host`, pagination) in `services/query-api/src/routes/flows.py`
- [X] T050 [US1] Register `/api/v1/query/*` and `/api/v1/realtime` routes in `gateway/src/routing.py` (depends on T023, T045, T046, T047, T048, T049)
- [X] T051 [P] [US1] Implement the Dashboard page (traffic-volume, protocol-distribution, application-breakdown charts, top-talkers table) in `frontend/src/pages/Dashboard.tsx` per the `dataviz` skill's palette/interaction rules
- [X] T052 [US1] Implement the frontend WebSocket client consuming `stats_update`/`site_status_changed`, with a visible reconnect indicator, in `frontend/src/services/realtime.ts` (depends on T045)
- [X] T053 [US1] Implement drill-down interaction (chart click → flow-record table for that window) in `frontend/src/components/FlowDrilldown.tsx` (depends on T049)
- [X] T054 [US1] Implement site-status indicators and explicit empty/no-data states across the Dashboard in `frontend/src/components/SiteStatusBadge.tsx` and `frontend/src/pages/Dashboard.tsx` (FR-004, FR-018)
- [X] T055 [US1] Add keyboard navigation and screen-reader support (ARIA labels, focus order) to the Dashboard page per FR-016 in `frontend/src/pages/Dashboard.tsx`

**Checkpoint**: User Story 1 is fully functional and independently testable via `quickstart.md` Scenario 1

---

## Phase 4: User Story 2 - Historical Data Exploration & Reporting (Priority: P2)

**Goal**: An analyst filters historical traffic by site/application/host over days-to-months and
exports a report that matches what was shown on screen.

**Independent Test**: Load a multi-week dataset, run filtered historical queries, and
generate/export a report — independent of whether real-time ingestion or alerting exists.

### Tests for User Story 2

- [X] T056 [P] [US2] Contract test for `POST /reports`, `GET /reports/{id}`, `GET /reports/{id}/export` in `services/query-api/tests/contract/test_reports_endpoints.py`, asserting exported output matches on-screen results (SC-009)
- [X] T057 [P] [US2] Query-performance test asserting a filtered query over 30 days of seeded ClickHouse data returns in under 3 seconds for 95% of queries (SC-003) in `services/query-api/tests/performance/test_query_latency.py`
- [X] T058 [US2] Integration test automating `quickstart.md` Scenario 2 (filtered query, CSV export round-trip, out-of-retention query response) in `services/query-api/tests/integration/test_scenario_historical_reporting.py`

### Implementation for User Story 2

- [X] T059 [P] [US2] Write the PostgreSQL migration for `Report` (`id` UUID PK, `owner_user_id` FK, `filter_definition` JSONB, `name` nullable, `created_at`) in `services/query-api/migrations/0001_report.sql`
- [X] T060 [US2] Implement `POST /reports` (create saved/ad hoc report from a filter definition) in `services/query-api/src/routes/reports.py` (depends on T059)
- [X] T061 [US2] Implement `GET /reports/{id}` (retrieve current results for a saved report's filter) in `services/query-api/src/routes/reports.py` (depends on T060)
- [X] T062 [US2] Implement `GET /reports/{id}/export?format=csv` producing output that exactly matches the on-screen filtered results (SC-009) in `services/query-api/src/routes/reports.py` (depends on T060)
- [X] T063 [US2] Extend `GET /flows` and `GET /reports/*` to return an explicit `"outside_retention"` reason (distinct from `"no_traffic"`) when the requested range exceeds the configured retention window in `services/query-api/src/routes/flows.py` and `services/query-api/src/routes/reports.py` (depends on T049, T060)
- [X] T064 [P] [US2] Implement the Reports page (date-range/site/protocol/application/host filters, results table, export action) in `frontend/src/pages/Reports.tsx`
- [X] T065 [US2] Add explicit empty/no-data and "outside retention" states to the Reports page in `frontend/src/pages/Reports.tsx` (FR-018) (depends on T063, T064)
- [X] T066 [US2] Add keyboard navigation and screen-reader support to the Reports page per FR-016 in `frontend/src/pages/Reports.tsx`

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Multi-User Access Control & Site Onboarding (Priority: P3)

**Goal**: An administrator onboards sites and manages user roles/scopes entirely through the
application, with access changes and cross-site isolation enforced immediately.

**Independent Test**: Create users with different roles/site scopes, confirm each sees only
permitted data, and onboard a new simulated exporter end-to-end through the admin interface
without code changes.

### Tests for User Story 3

- [ ] T067 [P] [US3] Contract test for `GET/POST /users`, `PATCH /users/{id}/roles`, `PATCH /users/{id}/status` in `services/identity/tests/contract/test_users_endpoints.py`
- [ ] T068 [P] [US3] Contract test for `GET/POST /sites`, `DELETE /sites/{id}`, `GET /audit-log`, `GET/PATCH /retention-policy` in `services/identity/tests/contract/test_admin_endpoints.py`
- [ ] T069 [P] [US3] Access-control test confirming a user scoped to one site cannot read another site's data via `/summary`, `/flows`, `/reports`, or `/realtime` (FR-009) in `services/query-api/tests/test_site_scope_enforcement.py`
- [ ] T070 [US3] Integration test automating `quickstart.md` Scenario 3 (scoped user cannot see a second site's data; revocation takes effect on the very next request without a restart) in `services/identity/tests/integration/test_scenario_access_control.py`

### Implementation for User Story 3

- [ ] T071 [P] [US3] Write the PostgreSQL migration for `AuditLogEntry` (`id` UUID PK, `actor_user_id` FK, `action`, `target`, `occurred_at`, `detail` JSONB) in `services/identity/migrations/0007_audit_log_entry.sql`
- [ ] T072 [US3] Implement `GET/POST /users` (list/invite users) in `services/identity/src/users/router.py`
- [ ] T073 [US3] Implement `PATCH /users/{id}/roles` (assign role(s) + site scope via `UserRoleAssignment`) in `services/identity/src/users/router.py`, enforcing FR-008/FR-009 (depends on T018, T072)
- [ ] T074 [US3] Implement `PATCH /users/{id}/status` (disable/re-enable; revocation takes effect on the user's very next request without a restart) in `services/identity/src/users/router.py` (depends on T020, T072)
- [ ] T075 [US3] Extend `GET/POST /sites` (full admin onboarding flow) and `DELETE /sites/{id}` (with referenced-entity cleanup per Edge Cases) in `services/identity/src/sites/router.py` (depends on T022)
- [ ] T076 [US3] Implement audit-log writing on every mutating Identity endpoint and `GET /audit-log` in `services/identity/src/audit/logger.py` and `services/identity/src/audit/router.py` (depends on T071, T072, T073, T074, T075)
- [ ] T077 [US3] Implement `GET/PATCH /retention-policy` in `services/identity/src/retention/router.py`, feeding the ClickHouse TTL from T019 (depends on T014, T019)
- [ ] T078 [US3] Implement a shared server-side site-scope authorization dependency (never trusting a client-supplied site filter) in `packages/shared/src/shared/authz.py`, applied to `query-api` and `alerting` (depends on T018)
- [ ] T079 [P] [US3] Implement the Admin page (user invitation/role/scope management, site onboarding form, audit-log view, retention-policy settings) in `frontend/src/pages/Admin.tsx`
- [ ] T080 [US3] Add explicit empty states, keyboard navigation, and screen-reader support to the Admin page per FR-016/FR-018 in `frontend/src/pages/Admin.tsx`

**Checkpoint**: User Stories 1, 2, AND 3 all work independently

---

## Phase 6: User Story 4 - Threshold-Based Alerting (Priority: P4)

**Goal**: An analyst defines a flow-derived alert condition and is notified promptly when it
occurs, without duplicate notifications while the condition remains true.

**Independent Test**: Define an alert rule, generate matching synthetic traffic, and confirm a
notification is delivered — independent of the reporting (P2) capability.

### Tests for User Story 4

- [ ] T081 [P] [US4] Contract test for `GET/POST /rules`, `PATCH/DELETE /rules/{id}`, `GET /events`, `GET /events/{id}/flows` in `services/alerting/tests/contract/test_alerting_endpoints.py`
- [ ] T082 [P] [US4] De-dup test confirming a continuously-true condition does not create a duplicate `AlertEvent`/notification (FR-013) in `services/alerting/tests/test_dedup.py`
- [ ] T083 [US4] Integration test automating `quickstart.md` Scenario 4 (rule definition, matching synthetic traffic, notification within 60s, duplicate suppression) in `services/alerting/tests/integration/test_scenario_alerting.py`

### Implementation for User Story 4

- [ ] T084 [P] [US4] Write the PostgreSQL migrations for `AlertRule` and `AlertEvent` in `services/alerting/migrations/0001_alert_rule.sql` and `0002_alert_event.sql` per data-model.md field definitions
- [ ] T085 [US4] Implement `GET/POST /rules` and `PATCH/DELETE /rules/{id}` in `services/alerting/src/routes/rules.py`, scoped to the owner's accessible sites (depends on T078, T084)
- [ ] T086 [US4] Implement the Kafka consumer evaluating `flow-records.v1` against active `AlertRule`s in `services/alerting/src/evaluator.py`, stopping evaluation of sites no longer in the owner's scope (depends on T085)
- [ ] T087 [US4] Implement Redis-backed de-dup state keyed by `alert_rule_id` and notification delivery, measured from the event's `observed_at` to satisfy the 60s target (SC-007) in `services/alerting/src/notifier.py` (depends on T086)
- [ ] T088 [US4] Implement `GET /events` and `GET /events/{id}/flows` in `services/alerting/src/routes/events.py` (depends on T086)
- [ ] T089 [P] [US4] Implement the Alerts page (rule definition form, alert event list, triggering-flow drill-down) in `frontend/src/pages/Alerts.tsx`
- [ ] T090 [US4] Add explicit empty states, keyboard navigation, and screen-reader support to the Alerts page per FR-016/FR-018 in `frontend/src/pages/Alerts.tsx`

**Checkpoint**: All four user stories are independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening and validation that spans multiple user stories

- [ ] T091 [P] Fill in `infra/k8s/` production-oriented manifests for all six services, `gateway`, and `frontend` per plan.md Project Structure
- [ ] T092 [P] Add Playwright end-to-end coverage for all four `quickstart.md` scenarios against the full `docker-compose` stack in `frontend/tests/e2e/`
- [ ] T093 [P] Document consumer-lag metrics/alerting for `flow-records.v1` (FR-014 visibility) in each consuming service's README
- [ ] T094 Run full `quickstart.md` validation against `docker compose -f infra/docker-compose.yml up -d` and record results
- [ ] T095 [P] Security hardening pass: confirm no secrets/credentials are committed and every service's environment configuration is documented in its README
- [ ] T096 [P] Update root `README.md` to describe the platform's multi-service architecture, superseding the single-process description, and link to `specs/001-enterprise-netflow-platform/` for full design docs
- [ ] T097 Performance validation pass confirming SC-001 (5s), SC-002 (100+ sites), SC-003 (<3s p95), SC-007 (60s alert latency), and SC-008 (99.9% uptime instrumentation) are each measured and documented

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phase 3–6)**: All depend on Foundational completion
  - US1 (P1) has no dependency on US2–US4
  - US2 (P2) reuses `GET /flows` from US1 (T049) for the retention-reason extension (T063) but its own Report CRUD is independent
  - US3 (P3) reuses the minimal Site/auth work from Foundational (T020–T022) and extends it; independent of US1/US2 business logic
  - US4 (P4) depends on the `flow-records.v1` stream (Foundational T009, US1 T039) and the shared authz dependency (US3 T078)
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Parallel Opportunities

- All Setup tasks marked [P] can run together
- All Foundational migration tasks (T013–T017) marked [P] can run together
- Once Foundational completes, US1 can start; US2/US3's own schema and endpoint work can be staffed in parallel with US1 by a different developer, though US2's T063 and US4 wait on US1's T049/T039
- All contract/unit test tasks marked [P] within a story can run together
- All frontend page implementations (T051, T064, T079, T089) can run in parallel once Foundational's app shell (T028) is done

---

## Parallel Example: User Story 1

```bash
# Tests for User Story 1 (after Foundational completes):
Task: "Contract test for FlowRecordEvent in services/ingestion/tests/contract/test_flow_record_event.py"
Task: "Parser test for a valid NetFlow v5 packet in services/ingestion/tests/test_netflow_v5_parser.py"
Task: "Parser test for a malformed NetFlow v5 packet in services/ingestion/tests/test_netflow_v5_parser.py"
Task: "Flow-Writer batch/dedupe integration test in services/flow-writer/tests/test_batch_writer.py"
Task: "Realtime aggregate/staleness integration test in services/realtime/tests/test_aggregate_cache.py"

# Implementation, once its own dependencies are satisfied:
Task: "UDP NetFlow v5 listener in services/ingestion/src/listener.py"
Task: "NetFlow v5 packet parser in services/ingestion/src/netflow_v5.py"
Task: "GET /summary in services/query-api/src/routes/summary.py"
Task: "GET /top-talkers in services/query-api/src/routes/top_talkers.py"
Task: "GET /sites/status in services/query-api/src/routes/site_status.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run `quickstart.md` Scenario 1 independently
5. Demo the real-time dashboard before continuing

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add User Story 1 → validate via Scenario 1 → MVP demo
3. Add User Story 2 → validate via Scenario 2 → historical reporting demo
4. Add User Story 3 → validate via Scenario 3 → access-control demo
5. Add User Story 4 → validate via Scenario 4 → alerting demo
6. Phase 7 polish → production-readiness pass

### Parallel Team Strategy

With multiple developers, once Foundational is done: one developer takes US1
(ingestion/flow-writer/realtime/query-api core), a second takes US3 (identity admin,
since it only extends Foundational's minimal auth/site work), and a third begins US2's
Report schema/endpoints once US1's `GET /flows` (T049) lands. US4 is best staffed last
since it depends on both the event stream (US1) and the shared authz dependency (US3).

---

## Notes

- [P] tasks = different files, no dependency on an incomplete task
- Every field constraint referenced above (enums, nullability, FKs) is quoted from `data-model.md` verbatim — do not re-derive it during implementation
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently before continuing
- The constitution (v1.0.0) Technology & Security Constraints section is the source of truth for the approved stack; do not introduce an additional storage or messaging technology without amending it first
