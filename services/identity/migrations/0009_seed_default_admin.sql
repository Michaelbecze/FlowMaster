-- Seeds a default organization + administrator account for local/dev use.
--
-- Every user-management endpoint (POST /users, PATCH /users/{id}/roles, ...) requires
-- an authenticated administrator caller (contracts/identity-api.md), which is a
-- chicken-and-egg problem on a fresh database: there is no signup endpoint by design
-- (FR-020 — platform-managed credentials only), so without this seed nobody could ever
-- log in to create the first user. This is the account documented as the default login
-- in README.md.
--
-- CHANGE OR REMOVE THIS BEFORE ANY non-local/production deployment — see README.md's
-- "Default login" section.
INSERT INTO organization (name)
SELECT 'Default Organization'
WHERE NOT EXISTS (SELECT 1 FROM organization);

INSERT INTO app_user (organization_id, email, password_hash)
SELECT o.id, 'admin@flowmaster.test', crypt('changeme', gen_salt('bf'))
FROM organization o
WHERE NOT EXISTS (SELECT 1 FROM app_user WHERE email = 'admin@flowmaster.test')
LIMIT 1;

INSERT INTO user_role_assignment (user_id, role_id, site_id)
SELECT u.id, r.id, NULL
FROM app_user u
JOIN role r ON r.name = 'administrator'
WHERE u.email = 'admin@flowmaster.test'
  AND NOT EXISTS (
      SELECT 1 FROM user_role_assignment existing
      WHERE existing.user_id = u.id AND existing.role_id = r.id AND existing.site_id IS NULL
  );
