-- AuditLogEntry: record of an administrative/config-changing action (FR-011).
-- Every mutating call on Identity writes one (contracts/identity-api.md).
CREATE TABLE audit_log_entry (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id  UUID NOT NULL REFERENCES app_user(id),
    action         TEXT NOT NULL,
    target         TEXT NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX audit_log_entry_occurred_at_idx ON audit_log_entry (occurred_at DESC);
