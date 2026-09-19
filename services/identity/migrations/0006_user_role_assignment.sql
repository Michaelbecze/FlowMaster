-- UserRoleAssignment: a user can hold a role scoped to a subset of sites (FR-008).
-- site_id NULL means organization-wide scope for that role.
--
-- A surrogate id is the primary key rather than (user_id, role_id, site_id): Postgres
-- forces every column of a composite primary key to be NOT NULL regardless of its own
-- column definition, which would silently break org-wide assignments (site_id NULL)
-- with a not-null-constraint violation at insert time.
CREATE TABLE user_role_assignment (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id  UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role_id  UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    site_id  UUID NULL REFERENCES site(id) ON DELETE CASCADE
);

CREATE INDEX user_role_assignment_user_idx ON user_role_assignment (user_id);
