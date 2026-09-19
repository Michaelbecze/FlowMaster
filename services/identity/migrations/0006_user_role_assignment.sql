-- UserRoleAssignment: a user can hold a role scoped to a subset of sites (FR-008).
-- site_id NULL means organization-wide scope for that role.
CREATE TABLE user_role_assignment (
    user_id  UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role_id  UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    site_id  UUID NULL REFERENCES site(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id, site_id)
);

CREATE INDEX user_role_assignment_user_idx ON user_role_assignment (user_id);
