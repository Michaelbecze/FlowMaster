import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiGetJson } from "../services/api";

interface RuleRow {
  id: string;
  site_id: string | null;
  condition: { type: string; bytes_threshold: number; window_seconds: number };
  enabled: boolean;
}

interface EventRow {
  id: string;
  alert_rule_id: string;
  triggered_at: string;
  resolved_at: string | null;
}

interface FlowRow {
  timestamp: string;
  src_addr: string;
  dst_addr: string;
  application: string;
  bytes: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function RuleForm({ onCreated }: { onCreated: () => void }) {
  const [siteId, setSiteId] = useState("");
  const [threshold, setThreshold] = useState("1000000");
  const [windowSeconds, setWindowSeconds] = useState("300");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await apiFetch("/api/v1/alerting/rules", {
      method: "POST",
      body: JSON.stringify({
        site_id: siteId || undefined,
        condition: {
          type: "volume_threshold",
          bytes_threshold: Number(threshold),
          window_seconds: Number(windowSeconds),
        },
      }),
    });
    if (!res.ok) {
      setError("Failed to create alert rule.");
      return;
    }
    setSiteId("");
    onCreated();
  }

  return (
    <form onSubmit={onSubmit} aria-label="Define alert rule" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <label htmlFor="rule-site">Site ID (blank = all your sites)</label>
          <input
            id="rule-site"
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="rule-threshold">Volume threshold (bytes)</label>
          <input
            id="rule-threshold"
            type="number"
            min={1}
            required
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="rule-window">Window (seconds)</label>
          <input
            id="rule-window"
            type="number"
            min={1}
            required
            value={windowSeconds}
            onChange={(e) => setWindowSeconds(e.target.value)}
            style={{ width: 100 }}
          />
        </div>
        <button type="submit">Create rule</button>
      </div>
      {error && (
        <p role="alert" style={{ color: "var(--status-critical)" }}>
          {error}
        </p>
      )}
    </form>
  );
}

function EventFlowsPanel({ eventId, onClose }: { eventId: string; onClose: () => void }) {
  const [flows, setFlows] = useState<FlowRow[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGetJson<FlowRow[]>(`/api/v1/alerting/events/${eventId}/flows`).then((data) => {
      if (!cancelled) setFlows(data);
    });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  return (
    <div className="card" role="region" aria-label="Triggering flow data" style={{ marginTop: 12 }}>
      <div className="card-title">
        Triggering flows
        <button onClick={onClose} aria-label="Close" style={{ marginLeft: 12 }}>
          ×
        </button>
      </div>
      {flows === null && <p>Loading…</p>}
      {flows !== null && flows.length === 0 && (
        <div className="empty-state">No flow records retained for this event's window.</div>
      )}
      {flows !== null && flows.length > 0 && (
        <table>
          <caption className="sr-only">Flow records that triggered this alert</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Source</th>
              <th scope="col">Destination</th>
              <th scope="col">Application</th>
              <th scope="col">Bytes</th>
            </tr>
          </thead>
          <tbody>
            {flows.map((f, i) => (
              <tr key={i}>
                <td>{new Date(f.timestamp).toLocaleTimeString()}</td>
                <td>{f.src_addr}</td>
                <td>{f.dst_addr}</td>
                <td>{f.application}</td>
                <td>{formatBytes(f.bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** Threshold-Based Alerting (User Story 4, FR-012/FR-013). */
export function Alerts() {
  const [rules, setRules] = useState<RuleRow[] | null>(null);
  const [events, setEvents] = useState<EventRow[] | null>(null);
  const [openEventId, setOpenEventId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function refresh() {
    try {
      setRules(await apiGetJson<RuleRow[]>("/api/v1/alerting/rules"));
      setEvents(await apiGetJson<EventRow[]>("/api/v1/alerting/events"));
      setLoadError(null);
    } catch {
      // Without this, a failed request leaves rules/events null forever and both
      // sections show "Loading…" indefinitely with no indication anything failed.
      setLoadError("Failed to load alerts. Please try refreshing the page.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 18, marginBottom: 16 }}>Alerts</h1>

      {loadError && (
        <div role="alert" className="card" style={{ marginBottom: 20, color: "var(--status-critical)" }}>
          {loadError}
        </div>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">Alert Rules</div>
        <RuleForm onCreated={refresh} />

        {rules === null && <p>Loading…</p>}
        {rules !== null && rules.length === 0 && (
          <div className="empty-state">No alert rules defined yet.</div>
        )}
        {rules !== null && rules.length > 0 && (
          <table>
            <caption className="sr-only">Configured alert rules</caption>
            <thead>
              <tr>
                <th scope="col">Site</th>
                <th scope="col">Threshold</th>
                <th scope="col">Window</th>
                <th scope="col">Enabled</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.site_id ? r.site_id.slice(0, 8) : "all sites"}</td>
                  <td>{formatBytes(r.condition.bytes_threshold)}</td>
                  <td>{r.condition.window_seconds}s</td>
                  <td>{r.enabled ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <div className="card-title">Alert Events</div>
        {events === null && <p>Loading…</p>}
        {events !== null && events.length === 0 && (
          <div className="empty-state">No alerts have fired yet.</div>
        )}
        {events !== null && events.length > 0 && (
          <table>
            <caption className="sr-only">Alert firing history</caption>
            <thead>
              <tr>
                <th scope="col">Triggered</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td>{new Date(e.triggered_at).toLocaleString()}</td>
                  <td>{e.resolved_at ? "Resolved" : "Active"}</td>
                  <td>
                    <button onClick={() => setOpenEventId(e.id)}>View flows</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {openEventId && (
          <EventFlowsPanel eventId={openEventId} onClose={() => setOpenEventId(null)} />
        )}
      </div>
    </div>
  );
}
