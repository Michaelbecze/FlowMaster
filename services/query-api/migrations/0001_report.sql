-- Report: a saved or ad hoc filtered query over historical flow data (FR-006, FR-007).
-- name is nullable: present for saved reports, null for ad hoc/one-off exports.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE report (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id      UUID NOT NULL,
    filter_definition  JSONB NOT NULL,
    name               TEXT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX report_owner_idx ON report (owner_user_id);
