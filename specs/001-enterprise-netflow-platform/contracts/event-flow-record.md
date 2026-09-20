# Contract: Flow Record Event

**Type**: Event (published on the Kafka-compatible stream)
**Topic**: `flow-records.v1`
**Producer**: `ingestion` service
**Consumers**: `flow-writer`, `realtime`, `alerting`

Partition key: `site_id` (preserves per-site ordering; allows independent consumer
scaling by site).

## Payload schema

```json
{
  "schema_version": "1.0",
  "site_id": "uuid",
  "observed_at": "2026-09-19T18:00:00.000Z",
  "ingested_at": "2026-09-19T18:00:00.120Z",
  "src_addr": "10.0.1.5",
  "dst_addr": "203.0.113.9",
  "src_port": 51321,
  "dst_port": 443,
  "protocol": 6,
  "application": "HTTPS",
  "bytes": 15420,
  "packets": 22,
  "direction": "outbound"
}
```

## Guarantees

- At-least-once delivery. Consumers MUST be idempotent (dedupe on
  `site_id` + `observed_at` + `src_addr` + `src_port` + `dst_addr` + `dst_port` +
  `protocol`, or an equivalent producer-assigned event id, if exact-once semantics are
  needed for a given consumer).
- `schema_version` is included on every event; consumers MUST reject/quarantine unknown
  major versions rather than guess-parse them (schema evolution rule, not a v1 build item).
- A malformed/truncated source packet MUST NOT reach this topic — the Ingestion service
  validates before publishing (FR-015); invalid input is counted in an Ingestion-owned
  metric instead.

## Consumer lag as a monitoring signal

Each consumer group's lag on `flow-records.v1` is the platform's visible signal for
FR-014 (ingest volume exceeding downstream capacity). This is an operational
contract, not a schema field: consumer lag MUST be exposed via each consumer's metrics
endpoint.
