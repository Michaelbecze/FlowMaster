import { useEffect, useState } from "react";
import { apiGetJson } from "../services/api";

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

interface FlowsEnvelope {
  data: FlowRow[];
  empty: boolean;
  reason: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Drill-down from a summary chart point into the underlying flow records for that
 * window (User Story 1, FR-003).
 *
 * Renders as a panel that expands in place directly beneath the chart it was opened
 * from, rather than as a standalone card at the end of the page — a drill-down that
 * scrolls you away from the point you clicked loses the context that made you click
 * it, and on a dashboard this long the jump reads as the page navigating somewhere. */
export function FlowDrilldown({
  start,
  end,
  siteId,
  onClose,
}: {
  start: Date;
  end: Date;
  siteId?: string | null;
  onClose: () => void;
}) {
  const [rows, setRows] = useState<FlowRow[] | null>(null);
  const [emptyReason, setEmptyReason] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      start: start.toISOString(),
      end: end.toISOString(),
    });
    if (siteId) params.set("site_id", siteId);
    apiGetJson<FlowsEnvelope>(`/api/v1/query/flows?${params}`).then((res) => {
      if (cancelled) return;
      setRows(res.data);
      setEmptyReason(res.empty ? res.reason : null);
    });
    return () => {
      cancelled = true;
    };
  }, [start, end, siteId]);

  return (
    <div
      role="region"
      aria-label="Flow drill-down"
      style={{
        marginTop: 14,
        paddingTop: 12,
        borderTop: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 10,
        }}
      >
        <div className="card-title" style={{ margin: 0 }}>
          Flows: {start.toLocaleTimeString()} – {end.toLocaleTimeString()}
          {rows !== null && rows.length > 0 && (
            <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>({rows.length})</span>
          )}
        </div>
        <button onClick={onClose} aria-label="Close flow list">
          Close
        </button>
      </div>
      {rows === null && <p style={{ margin: 0 }}>Loading…</p>}
      {rows !== null && rows.length === 0 && (
        <div className="empty-state">
          {emptyReason === "outside_retention"
            ? "This window is outside the configured retention period."
            : "No flows in this window."}
        </div>
      )}
      {rows !== null && rows.length > 0 && (
        // Capped and scrolled rather than free-growing: a busy minute can return
        // hundreds of flows, and letting the panel run the full length of the page
        // would shove the charts below it out of reach — the same "where did the
        // page go" problem as the old scroll-to-bottom, just in the other direction.
        // theme.css already makes <th> sticky, so the header stays put while scrolling.
        <div style={{ maxHeight: 280, overflowY: "auto" }}>
          <table>
            <caption className="sr-only">Individual flow records for the selected window</caption>
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
              {rows.map((row, i) => (
                <tr key={i}>
                  <td>{new Date(row.timestamp).toLocaleTimeString()}</td>
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
        </div>
      )}
    </div>
  );
}
