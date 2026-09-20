# Quickstart: Validating the Enterprise NetFlow Platform

This is a runnable validation guide proving the feature works end-to-end, one scenario
per prioritized user story. It assumes the services in `services/`, `gateway/`, and
`frontend/` (see `plan.md` Project Structure) are implemented per `contracts/` and
`data-model.md`. It does not include implementation code — see `tasks.md` for that.

## Prerequisites

- Docker + Docker Compose
- `infra/docker-compose.yml` brings up: PostgreSQL, ClickHouse, Redis, the
  Kafka-compatible broker, all six services, the Gateway, and the frontend dev server.

```bash
docker compose -f infra/docker-compose.yml up -d
```

## Scenario 1 — Real-time visibility (User Story 1, P1)

1. Onboard a site via the Identity API (or admin UI) to obtain a site identity.
2. Send synthetic NetFlow v5 packets to the Ingestion service's UDP port, addressed as
   that site (a generalized version of the existing project's `test_flow.py`).
3. Open the frontend dashboard, authenticated as a user scoped to that site.
4. **Expected**: aggregated traffic appears within 5 seconds (SC-001); clicking a chart
   point drills down to the individual flow records (FR-003).
5. Stop sending packets for longer than the configured staleness threshold.
   **Expected**: the site is shown as offline/stale, not as zero traffic (FR-004).

## Scenario 2 — Historical query & export (User Story 2, P2)

1. Using the seeded/synthetic data from Scenario 1 (or a larger backfilled dataset),
   call `GET /api/v1/query/flows` with a date range, site, and protocol filter.
2. **Expected**: results match the filter; a query over 30 days of data returns in
   under 3 seconds (SC-003).
3. Call `GET /api/v1/query/reports/{id}/export?format=csv` and open the result in a
   spreadsheet tool.
   **Expected**: exported rows match what the dashboard/report view displayed exactly
   (SC-009).
4. Query a time range older than the configured retention window.
   **Expected**: the response indicates data is no longer retained (`reason:
   "outside_retention"`), not an indistinguishable empty result.

## Scenario 3 — Access control & site onboarding (User Story 3, P3)

1. As an administrator, create a second site and a new user with a role scoped only to
   the first site.
2. Log in as that user.
   **Expected**: the second site's data is not visible in any dashboard, report, or API
   response (FR-009) — verify explicitly via a direct API call to the second site's data,
   not just the UI.
3. Revoke the user's access.
   **Expected**: their very next request is denied, without restarting any service
   (Acceptance Scenario 3).

## Scenario 4 — Alerting (User Story 4, P4)

1. Define an alert rule (e.g., volume threshold) scoped to a site.
2. Send synthetic traffic that satisfies the condition.
   **Expected**: a notification is delivered within 60 seconds (SC-007), and
   `GET /api/v1/alerting/events/{id}/flows` returns the triggering flow data.
3. Continue sending traffic that keeps the condition true.
   **Expected**: no duplicate notification is sent for the same ongoing condition
   (FR-013).

## Cross-cutting checks

- Kill the Flow-Writer service while Ingestion keeps receiving traffic.
  **Expected**: no data loss once Flow-Writer resumes (event stream retains unconsumed
  messages); consumer lag is visible in metrics (FR-014).
- Send a truncated/malformed flow packet.
  **Expected**: Ingestion rejects it without crashing or affecting other packets
  (FR-015).
