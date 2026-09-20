# FlowMaster

An enterprise-oriented NetFlow v5 collection and analytics platform: a set of
independently deployable services communicating over an event stream and REST APIs,
backed by storage engines chosen per access pattern, fronted by a componentized React
dashboard. This is a from-scratch evolution of an earlier single-process/SQLite
prototype (see `git log`) into the microservices architecture described in
[`specs/001-enterprise-netflow-platform/`](specs/001-enterprise-netflow-platform)
(spec, plan, contracts, data model).

![Dashboard](https://img.shields.io/badge/dashboard-React%20%2B%20ECharts-00d4ff?style=flat-square)
![NetFlow](https://img.shields.io/badge/NetFlow-v5-8b5cf6?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11%2B-10b981?style=flat-square)

---

## Architecture

| Service | Role | Port |
|---|---|---|
| `gateway` | Single public entry point — auth, rate limiting, routes to the services below (frontend and API clients never call a backend service directly) | 8080 |
| `identity` | Users, roles, sites/exporters, auth (sessions + API tokens), audit log — PostgreSQL | 8001 |
| `ingestion` | NetFlow v5 UDP listener; parses + validates packets; publishes to the event stream | 8002 (HTTP), 2055/udp (NetFlow) |
| `flow-writer` | Consumes the event stream; batches flow records into ClickHouse; runs retention purge | 8003 |
| `realtime` | Consumes the event stream; maintains rolling aggregates in Redis; pushes updates over WebSocket | 8004 |
| `query-api` | REST API for dashboard summaries, drill-down, historical queries, report export | 8005 |
| `alerting` | Alert rule evaluation against the event stream; notification delivery + de-dup | 8006 |
| `frontend` | React + TypeScript + Vite SPA (charts via ECharts) | 5173 |

Backing stores: **PostgreSQL** (relational metadata), **ClickHouse** (flow records,
time-window aggregation), **Redis** (real-time state, WebSocket fan-out, rate limits),
and a Kafka-API-compatible broker (**Redpanda**, dev topology) decoupling ingestion from
its consumers.

Full rationale for each choice is in
[`specs/001-enterprise-netflow-platform/research.md`](specs/001-enterprise-netflow-platform/research.md);
per-service contracts are in
[`specs/001-enterprise-netflow-platform/contracts/`](specs/001-enterprise-netflow-platform/contracts).

---

## Requirements

- Docker + Docker Compose (runs the entire stack — Postgres, ClickHouse, Redis, the
  broker, all six services, the Gateway, and the frontend dev server)
- `psql` (or another Postgres client) to apply Identity's SQL migrations — there is no
  automated migration runner yet, so this is a manual one-time step (see below)

Running a single service outside Docker additionally needs Python 3.11+ (each service
has its own `pyproject.toml`) or Node.js 20+ for the frontend.

---

## Running it

```bash
git clone https://github.com/Michaelbecze/FlowMaster.git
cd FlowMaster
docker compose -f infra/docker-compose.yml up -d
```

Apply the Identity service's database schema (one-time, or after pulling new
migrations — each file is idempotent-safe to re-run):

```bash
for f in services/identity/migrations/*.sql; do
  docker compose -f infra/docker-compose.yml exec -T postgres \
    psql -U flowmaster -d flowmaster -f - < "$f"
done
```

Then open **http://localhost:5173** in your browser.

### Default login

The last migration (`0009_seed_default_admin.sql`) seeds one administrator account so
there's a way to log in on a fresh database — every user-management endpoint requires an
existing admin caller, and there is no public signup (FR-020: platform-managed
credentials only).

| Email | Password |
|---|---|
| `admin@flowmaster.test` | `changeme` |

**Change this password (or create a new admin and disable this one) before using
FlowMaster outside your own machine.** There is currently no self-service "change my
password" flow in the UI — do it via the Identity API (`PATCH /users/{id}` /
re-seed with a different hash) or directly against the `app_user` table.

---

## Project structure

```
FlowMaster/
├── gateway/                 # API gateway — single public entry point
├── services/
│   ├── identity/             # Users, roles, sites, auth, audit log (PostgreSQL)
│   ├── ingestion/            # NetFlow v5 UDP listener → event stream
│   ├── flow-writer/          # Event stream → ClickHouse; retention purge
│   ├── realtime/              # Event stream → Redis aggregates → WebSocket
│   ├── query-api/             # Historical queries, reports, export
│   └── alerting/               # Alert rule evaluation + notification delivery
├── packages/shared/          # Shared Python library used by every service
├── frontend/                 # React + TypeScript + Vite dashboard
│   └── src/
│       ├── pages/            # Dashboard, Reports, Admin, Alerts, Login
│       └── components/       # Charts, layout, auth guard, etc.
├── infra/
│   ├── docker-compose.yml    # Full local stack
│   └── kafka-topics-init.sh
└── specs/001-enterprise-netflow-platform/   # Spec, plan, contracts, data model, tasks
```

Each service directory has its own `src/` and `tests/`.

---

## Testing

Backend (per service, from that service's directory):

```bash
pytest
```

Integration tests that exercise the full running stack are skipped automatically if
`infra/docker-compose.yml` isn't up (they probe `GATEWAY_URL`, default
`http://localhost:8080`).

Frontend:

```bash
cd frontend
npm run build   # tsc -b && vite build
npx vitest run
```

---

## Testing ingestion without a real NetFlow source

Send synthetic NetFlow v5 packets directly to the Ingestion service's UDP port
(`2055` by default) once a site has been onboarded via the Identity API or the Admin
page — see
[`specs/001-enterprise-netflow-platform/quickstart.md`](specs/001-enterprise-netflow-platform/quickstart.md)
Scenario 1 for the full walkthrough.

---

## License

MIT
