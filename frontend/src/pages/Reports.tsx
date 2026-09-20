import { FormEvent, useState } from "react";
import { apiFetch, apiGetJson } from "../services/api";

interface FlowRow {
  timestamp: string;
  site_id: string;
  src_addr: string;
  dst_addr: string;
  src_port: number;
  dst_port: number;
  protocol: number;
  application: string;
  bytes: number;
  packets: number;
  direction: string;
}

interface ReportEnvelope {
  data: FlowRow[];
  empty: boolean;
  reason: "no_traffic" | "outside_retention" | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function defaultDateTimeLocal(offsetHours: number): string {
  const d = new Date(Date.now() + offsetHours * 3600 * 1000);
  return d.toISOString().slice(0, 16);
}

/** Historical data exploration & reporting (User Story 2, FR-006/FR-007). Filters
 * (date range, site, protocol, application, host) apply uniformly to the results
 * table and the export, per constitution Principle III. */
export function Reports() {
  const [start, setStart] = useState(defaultDateTimeLocal(-24));
  const [end, setEnd] = useState(defaultDateTimeLocal(0));
  const [siteId, setSiteId] = useState("");
  const [protocol, setProtocol] = useState("");
  const [application, setApplication] = useState("");
  const [host, setHost] = useState("");

  const [reportId, setReportId] = useState<string | null>(null);
  const [result, setResult] = useState<ReportEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onExport() {
    if (!reportId) return;
    // A plain <a href> wouldn't carry the Authorization header apiFetch adds, so the
    // export is fetched client-side and handed to the browser as a Blob download.
    const res = await apiFetch(`/api/v1/query/reports/${reportId}/export?format=csv`);
    if (!res.ok) {
      setError("Failed to export report.");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `report-${reportId}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const createRes = await apiFetch("/api/v1/query/reports", {
        method: "POST",
        body: JSON.stringify({
          start: new Date(start).toISOString(),
          end: new Date(end).toISOString(),
          site_id: siteId || undefined,
          protocol: protocol ? Number(protocol) : undefined,
          application: application || undefined,
          host: host || undefined,
        }),
      });
      if (!createRes.ok) throw new Error("Failed to create report");
      const created = await createRes.json();
      setReportId(created.id);

      const viewRes = await apiGetJson<ReportEnvelope>(`/api/v1/query/reports/${created.id}`);
      setResult(viewRes);
    } catch {
      setError("Failed to run report. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 18, marginBottom: 16 }}>Reports</h1>

      <form
        onSubmit={onSubmit}
        className="card"
        aria-label="Report filters"
        style={{ marginBottom: 20 }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
            marginBottom: 12,
          }}
        >
          <div>
            <label htmlFor="start">Start</label>
            <input
              id="start"
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              required
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="end">End</label>
            <input
              id="end"
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              required
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="site_id">Site ID</label>
            <input
              id="site_id"
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              placeholder="all sites"
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="protocol">Protocol</label>
            <input
              id="protocol"
              type="number"
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
              placeholder="any"
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="application">Application</label>
            <input
              id="application"
              value={application}
              onChange={(e) => setApplication(e.target.value)}
              placeholder="any"
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label htmlFor="host">Host</label>
            <input
              id="host"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="any"
              style={{ width: "100%" }}
            />
          </div>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? "Running…" : "Run report"}
        </button>
        {error && (
          <p role="alert" style={{ color: "var(--status-critical)" }}>
            {error}
          </p>
        )}
      </form>

      {result && (
        <div className="card">
          <div
            className="card-title"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            Results
            {reportId && !result.empty && (
              <button onClick={onExport} style={{ fontSize: 12 }}>
                Export CSV
              </button>
            )}
          </div>

          {result.empty ? (
            <div className="empty-state">
              {result.reason === "outside_retention"
                ? "This time range is outside the configured retention period — the data is no longer retained, not merely absent."
                : "No flows matched this filter."}
            </div>
          ) : (
            <table>
              <caption className="sr-only">Filtered flow records for this report</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Site</th>
                  <th scope="col">Source</th>
                  <th scope="col">Destination</th>
                  <th scope="col">Application</th>
                  <th scope="col">Bytes</th>
                </tr>
              </thead>
              <tbody>
                {result.data.map((row, i) => (
                  <tr key={i}>
                    <td>{new Date(row.timestamp).toLocaleString()}</td>
                    <td>{row.site_id.slice(0, 8)}</td>
                    <td>
                      {row.src_addr}:{row.src_port}
                    </td>
                    <td>
                      {row.dst_addr}:{row.dst_port}
                    </td>
                    <td>{row.application}</td>
                    <td>{formatBytes(row.bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
