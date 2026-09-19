import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiGetJson } from "../services/api";

interface RoleAssignment {
  role: string;
  site_id: string | null;
}

interface UserRow {
  id: string;
  email: string;
  status: "active" | "disabled";
  roles: RoleAssignment[];
}

interface SiteRow {
  id: string;
  name: string;
  network_identity: string;
  status: "active" | "stale" | "never_connected";
  last_seen_at: string | null;
}

interface AuditLogEntryRow {
  id: string;
  actor_user_id: string;
  action: string;
  target: string;
  occurred_at: string;
}

interface RetentionPolicyRow {
  duration_days: number;
  updated_at: string;
}

const ROLE_OPTIONS = ["viewer", "analyst", "administrator"];

function UsersSection() {
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setUsers(await apiGetJson<UserRow[]>("/api/v1/identity/users"));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await apiFetch("/api/v1/identity/users", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    });
    if (!res.ok) {
      setError(res.status === 409 ? "A user with that email already exists." : "Failed to invite user.");
      return;
    }
    setEmail("");
    setPassword("");
    await refresh();
  }

  async function onToggleStatus(user: UserRow) {
    const next = user.status === "active" ? "disabled" : "active";
    await apiFetch(`/api/v1/identity/users/${user.id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: next }),
    });
    await refresh();
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">Users</div>

      <form onSubmit={onInvite} aria-label="Invite user" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label htmlFor="invite-email">Email</label>
            <input
              id="invite-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ padding: 6 }}
            />
          </div>
          <div>
            <label htmlFor="invite-password">Initial password</label>
            <input
              id="invite-password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ padding: 6 }}
            />
          </div>
          <div>
            <label htmlFor="invite-role">Role</label>
            <select id="invite-role" value={role} onChange={(e) => setRole(e.target.value)} style={{ padding: 6 }}>
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <button type="submit">Invite</button>
        </div>
        {error && (
          <p role="alert" style={{ color: "var(--status-critical)" }}>
            {error}
          </p>
        )}
      </form>

      {users === null && <p>Loading…</p>}
      {users !== null && users.length === 0 && <div className="empty-state">No users yet.</div>}
      {users !== null && users.length > 0 && (
        <table>
          <caption className="sr-only">Platform users and their roles</caption>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Roles</th>
              <th scope="col">Status</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>
                  {u.roles.map((r) => `${r.role}${r.site_id ? ` (${r.site_id.slice(0, 8)})` : " (all sites)"}`).join(", ")}
                </td>
                <td>{u.status}</td>
                <td>
                  <button onClick={() => onToggleStatus(u)}>
                    {u.status === "active" ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SitesSection() {
  const [sites, setSites] = useState<SiteRow[] | null>(null);
  const [name, setName] = useState("");
  const [networkIdentity, setNetworkIdentity] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setSites(await apiGetJson<SiteRow[]>("/api/v1/identity/sites"));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onOnboard(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await apiFetch("/api/v1/identity/sites", {
      method: "POST",
      body: JSON.stringify({ name, network_identity: networkIdentity }),
    });
    if (!res.ok) {
      setError(res.status === 409 ? "A site with that network identity already exists." : "Failed to onboard site.");
      return;
    }
    setName("");
    setNetworkIdentity("");
    await refresh();
  }

  async function onDelete(siteId: string) {
    await apiFetch(`/api/v1/identity/sites/${siteId}`, { method: "DELETE" });
    await refresh();
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">Sites</div>

      <form onSubmit={onOnboard} aria-label="Onboard site" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label htmlFor="site-name">Name</label>
            <input
              id="site-name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ padding: 6 }}
            />
          </div>
          <div>
            <label htmlFor="site-network-identity">Exporter IP</label>
            <input
              id="site-network-identity"
              required
              value={networkIdentity}
              onChange={(e) => setNetworkIdentity(e.target.value)}
              style={{ padding: 6 }}
            />
          </div>
          <button type="submit">Onboard site</button>
        </div>
        {error && (
          <p role="alert" style={{ color: "var(--status-critical)" }}>
            {error}
          </p>
        )}
      </form>

      {sites === null && <p>Loading…</p>}
      {sites !== null && sites.length === 0 && (
        <div className="empty-state">No sites onboarded yet.</div>
      )}
      {sites !== null && sites.length > 0 && (
        <table>
          <caption className="sr-only">Onboarded sites</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Exporter IP</th>
              <th scope="col">Status</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {sites.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.network_identity}</td>
                <td>{s.status}</td>
                <td>
                  <button onClick={() => onDelete(s.id)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AuditLogSection() {
  const [entries, setEntries] = useState<AuditLogEntryRow[] | null>(null);

  useEffect(() => {
    apiGetJson<AuditLogEntryRow[]>("/api/v1/identity/audit-log").then(setEntries);
  }, []);

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-title">Audit Log</div>
      {entries === null && <p>Loading…</p>}
      {entries !== null && entries.length === 0 && (
        <div className="empty-state">No administrative actions recorded yet.</div>
      )}
      {entries !== null && entries.length > 0 && (
        <table>
          <caption className="sr-only">Administrative action history</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Action</th>
              <th scope="col">Target</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{new Date(e.occurred_at).toLocaleString()}</td>
                <td>{e.action}</td>
                <td>{e.target.slice(0, 8)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RetentionPolicySection() {
  const [policy, setPolicy] = useState<RetentionPolicyRow | null>(null);
  const [days, setDays] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGetJson<RetentionPolicyRow>("/api/v1/identity/retention-policy").then((p) => {
      setPolicy(p);
      setDays(String(p.duration_days));
    });
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    const res = await apiFetch("/api/v1/identity/retention-policy", {
      method: "PATCH",
      body: JSON.stringify({ duration_days: Number(days) }),
    });
    if (res.ok) {
      setPolicy(await res.json());
      setSaved(true);
    }
  }

  return (
    <div className="card">
      <div className="card-title">Retention Policy</div>
      {policy === null ? (
        <p>Loading…</p>
      ) : (
        <form onSubmit={onSave} aria-label="Retention policy" style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div>
            <label htmlFor="retention-days">Retention (days)</label>
            <input
              id="retention-days"
              type="number"
              min={1}
              required
              value={days}
              onChange={(e) => setDays(e.target.value)}
              style={{ padding: 6, width: 100 }}
            />
          </div>
          <button type="submit">Save</button>
          {saved && <span style={{ color: "var(--status-good)" }}>Saved</span>}
        </form>
      )}
    </div>
  );
}

/** Multi-User Access Control & Site Onboarding (User Story 3, FR-008/FR-009/FR-010/FR-011). */
export function Admin() {
  return (
    <div>
      <h1 style={{ fontSize: 18, marginBottom: 16 }}>Admin</h1>
      <UsersSection />
      <SitesSection />
      <AuditLogSection />
      <RetentionPolicySection />
    </div>
  );
}
