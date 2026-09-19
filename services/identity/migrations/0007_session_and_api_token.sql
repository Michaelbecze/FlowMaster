-- Session and ApiToken: implementation detail backing POST/DELETE /auth/login|logout|tokens
-- (contracts/identity-api.md). Short-lived, revocable rows are what make "access changes
-- take effect on the very next request without a restart" (User Story 3, Acceptance Scenario 3)
-- possible, per identity-api.md's Access-control contract.
CREATE TABLE session (
    token_hash  TEXT PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ NULL
);

CREATE TABLE api_token (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash   TEXT NOT NULL UNIQUE,
    user_id      UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ NULL
);

CREATE INDEX session_user_idx ON session (user_id);
CREATE INDEX api_token_user_idx ON api_token (user_id);
