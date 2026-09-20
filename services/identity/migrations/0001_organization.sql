-- Organization: single top-level boundary for v1 (FR-021, data-model.md).
-- Modeled as a real table (not a hardcoded constant) so a later multi-tenant release
-- does not require a schema rewrite; v1 still enforces exactly one row at the app layer.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE organization (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,
    retention_policy_id  UUID NULL
);
