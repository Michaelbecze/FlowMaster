-- User: named individual with platform-managed credentials for v1 (FR-020).
-- password_hash is nullable so SSO/IdP integration can be added later without a schema break.
CREATE TYPE user_status AS ENUM ('active', 'disabled');

CREATE TABLE app_user (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    email             TEXT NOT NULL UNIQUE,
    password_hash     TEXT NULL,
    status            user_status NOT NULL DEFAULT 'active',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE site
    ADD CONSTRAINT site_created_by_fk FOREIGN KEY (created_by) REFERENCES app_user(id);

ALTER TABLE retention_policy
    ADD CONSTRAINT retention_policy_updated_by_fk FOREIGN KEY (updated_by) REFERENCES app_user(id);
