-- RetentionPolicy: configurable retention window per organization (FR-005).
CREATE TABLE retention_policy (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    duration_days    INTEGER NOT NULL CHECK (duration_days > 0),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by       UUID NULL
);

ALTER TABLE organization
    ADD CONSTRAINT organization_retention_policy_fk
    FOREIGN KEY (retention_policy_id) REFERENCES retention_policy(id);
