-- Site (Exporter): a monitored location/device sending flow data (FR-010, data-model.md).
-- last_seen_at stays NULL until the first flow is received, distinguishing "never
-- connected" from "went silent" (spec Edge Cases).
CREATE TYPE site_status AS ENUM ('active', 'stale', 'never_connected');

CREATE TABLE site (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id   UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    network_identity  TEXT NOT NULL,
    status            site_status NOT NULL DEFAULT 'never_connected',
    last_seen_at      TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by        UUID NULL,
    UNIQUE (organization_id, network_identity)
);

CREATE INDEX site_network_identity_idx ON site (network_identity);
