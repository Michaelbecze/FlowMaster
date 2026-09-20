# Contract: Alerting Service

**Base path** (via Gateway): `/api/v1/alerting`
**Backing store**: PostgreSQL (rules, events), Redis (de-dup state)
**Consumes**: `flow-records.v1` event stream (see `event-flow-record.md`)

| Method | Path | Purpose | Maps to |
|---|---|---|---|
| GET/POST | `/rules` | List / define alert rules, scoped to the caller's accessible sites | User Story 4, FR-012 |
| PATCH/DELETE | `/rules/{id}` | Update or remove a rule | User Story 4, FR-012 |
| GET | `/events?rule_id=...&since=...` | List alert firings, each linked to the triggering flow data | User Story 4, FR-012 |
| GET | `/events/{id}/flows` | Retrieve the underlying flow records that triggered a specific alert event | User Story 4, Acceptance Scenario 2 |

## Behavioral contract

- An alert rule MUST only be evaluatable against sites within the owner's access scope
  at creation time and at evaluation time (a later access-scope reduction must stop the
  rule from evaluating sites no longer in scope) — consistent with FR-009.
- While a condition remains continuously true, the service MUST NOT create a new
  `AlertEvent` / send a new notification; it updates the existing event's state instead
  (FR-013, Acceptance Scenario 3). De-dup state lives in Redis keyed by
  `alert_rule_id` (see `data-model.md`).
- Notification delivery latency (condition met → notification sent) MUST meet SC-007's
  60-second target; this is measured from the `flow-records.v1` event's `observed_at`
  timestamp, not from when the Alerting service happens to poll.
