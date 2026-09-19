# Contract: Realtime Push Channel

**Transport**: WebSocket, proxied through the Gateway (`wss://.../api/v1/realtime`)
**Producer**: `realtime` service (reads its own Redis-cached aggregate state, itself kept
current by consuming `flow-records.v1`)
**Consumer**: Frontend dashboard

## Connection contract

- Client connects with its session token (same auth as REST calls); the Gateway rejects
  the upgrade if the token is invalid/expired — the realtime channel MUST NOT be a
  side-channel that bypasses normal access control (FR-009).
- On connect, the client sends the set of sites/dashboards it wants updates for (within
  its authorized scope); the server MUST silently drop any requested site outside that
  scope rather than error in a way that reveals the site's existence.

## Message schema (server → client)

```json
{
  "type": "stats_update",
  "sites": ["uuid", "..."],
  "window": "1h",
  "summary": { "total_bytes": 0, "protocol_mix": {}, "top_talkers": [] },
  "site_status": { "uuid": "active" },
  "as_of": "2026-09-19T18:00:05.000Z"
}
```

```json
{
  "type": "site_status_changed",
  "site_id": "uuid",
  "status": "stale",
  "last_seen_at": "2026-09-19T17:55:00.000Z"
}
```

## Cadence and resilience contract

- `stats_update` messages are pushed at least once per 5 seconds per active dashboard
  session, satisfying SC-001 — the frontend does not poll for this data.
- On disconnect, the frontend MUST show a visible reconnect indicator (constitution
  Principle III) rather than silently freezing the last-known values; on reconnect, the
  server sends a fresh `stats_update` immediately rather than waiting for the next tick.
