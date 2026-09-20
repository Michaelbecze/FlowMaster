-- AlertRule: a condition defined over flow data (FR-012, data-model.md).
-- site_scope NULL = all sites the owner can access (contracts/alerting-api.md).
-- condition_definition v1 supports one shape: a sustained volume threshold —
-- {"type": "volume_threshold", "bytes_threshold": N, "window_seconds": W} — matching
-- the spec's own first example ("a sustained spike from a site"); other condition
-- types are a documented future extension, not parsed by the v1 evaluator.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE alert_rule (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id        UUID NOT NULL,
    site_scope           UUID NULL,
    condition_definition JSONB NOT NULL,
    notification_target  JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled              BOOLEAN NOT NULL DEFAULT true,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX alert_rule_owner_idx ON alert_rule (owner_user_id);
CREATE INDEX alert_rule_enabled_idx ON alert_rule (enabled) WHERE enabled;
