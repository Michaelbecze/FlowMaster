# Contract: Identity Service

**Base path** (via Gateway): `/api/v1/identity`
**Backing store**: PostgreSQL
**Auth**: This service issues the credentials every other service validates.

| Method | Path | Purpose | Maps to |
|---|---|---|---|
| POST | `/auth/login` | Platform-managed username/password login → session token | FR-020 |
| POST | `/auth/logout` | Invalidate session token | FR-020 |
| POST | `/auth/tokens` | Issue a machine/API token, scoped to the caller's own permissions, for programmatic access | FR-019 |
| DELETE | `/auth/tokens/{id}` | Revoke an API token | FR-019 |
| GET/POST | `/users` | List / invite users | User Story 3, FR-008 |
| PATCH | `/users/{id}/roles` | Assign/change a user's role(s) and site scope | User Story 3, FR-008, FR-009 |
| PATCH | `/users/{id}/status` | Disable/re-enable a user (access revocation) | User Story 3 |
| GET/POST | `/sites` | List sites / onboard a new site (generates the exporter identity Ingestion uses to attribute flows) | User Story 3, FR-010 |
| DELETE | `/sites/{id}` | Remove a site | Edge Cases (referenced-entity cleanup) |
| GET | `/audit-log?...` | Query the audit trail | FR-011 |
| GET/PATCH | `/retention-policy` | View/update the organization's configured retention window | FR-005 |

## Access-control contract

- Every other service (Query API, Alerting, Realtime, Gateway) validates tokens issued
  here and MUST treat the site-scope claim as authoritative — this is the single point
  of truth for FR-009's "no user can access another site's data through any view,
  export, or API."
- Role/access changes MUST take effect on the *next* request from the affected user,
  without requiring a system restart (User Story 3, Acceptance Scenario 3) — enforced by
  short-lived session tokens plus a revocation check, not by long-lived unrevocable
  tokens.
- Every mutating call on this service MUST write an `AuditLogEntry` (FR-011) — this is
  the one service where audit logging is a contractual requirement of the endpoint
  itself, not an optional side effect.
