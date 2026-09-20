-- FlowRecord: the fundamental unit of collected data (data-model.md, FR-001).
-- TTL implements FR-005 as a declared deletion policy, not a silent ad hoc purge; the
-- literal 24 HOUR default here is overridden per-organization by services/flow-writer's
-- retention_purge job reading RetentionPolicy.duration_days (see T042 / T077).
CREATE TABLE IF NOT EXISTS flow_record
(
    timestamp    DateTime64(3),
    site_id      String,
    src_addr     String,
    dst_addr     String,
    src_port     UInt16,
    dst_port     UInt16,
    protocol     UInt8,
    application  LowCardinality(String),
    bytes        UInt64,
    packets      UInt64,
    direction    Enum8('inbound' = 1, 'outbound' = 2, 'unknown' = 3),
    ingested_at  DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (site_id, timestamp)
TTL toDateTime(timestamp) + INTERVAL 24 HOUR;
