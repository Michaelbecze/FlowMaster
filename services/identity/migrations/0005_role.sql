-- Role: named set of permitted actions (Viewer, Analyst, Administrator — spec Key Entities).
CREATE TABLE role (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    permissions  JSONB NOT NULL DEFAULT '[]'::jsonb
);

INSERT INTO role (name, permissions) VALUES
    ('viewer',       '["dashboard:read", "reports:read"]'),
    ('analyst',      '["dashboard:read", "reports:read", "reports:write", "alerts:read", "alerts:write"]'),
    ('administrator', '["*"]');
