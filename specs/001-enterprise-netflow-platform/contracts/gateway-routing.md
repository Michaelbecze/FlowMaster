# Contract: API Gateway Routing

**Role**: Single entry point for the frontend. Terminates TLS, validates auth tokens
against the Identity service (or a shared verification key, as an implementation detail),
enforces API rate limits (Redis-backed), and routes to the owning service. The frontend
and external integrators (FR-019) only ever address the Gateway — they never call a
backend service directly.

| Path prefix | Routed to | Auth required |
|---|---|---|
| `/api/v1/identity/*` | `identity` service | Public for `/auth/login`; bearer token for everything else |
| `/api/v1/query/*` | `query-api` service | Bearer token (session or API token) |
| `/api/v1/alerting/*` | `alerting` service | Bearer token |
| `/api/v1/realtime` (WebSocket) | `realtime` service | Bearer token at upgrade time |

## Contract guarantees

- The Gateway is the only network-facing entry point for backend services; services do
  not need their own public ingress or duplicate auth logic beyond validating the token
  the Gateway (or Identity service) issued.
- The Gateway aggregates each service's OpenAPI schema into a single documented v1 API
  surface, satisfying FR-019's "documented, versioned" requirement without each service
  needing to separately publish developer-facing docs.
- Rate limiting is applied per API token at the Gateway, not duplicated per service
  (FR-019).
