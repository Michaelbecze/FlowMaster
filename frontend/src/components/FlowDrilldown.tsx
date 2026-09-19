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
 * window (User Story 1, FR-003). */
export function FlowDrilldown({
  start,
  end,
  onClose,
}: {
  start: Date;
  end: Date;
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
    apiGetJson<FlowsEnvelope>(`/api/v1/query/flows?${params}`).then((res) => {
      if (cancelled) return;
      setRows(res.data);
      setEmptyReason(res.empty ? res.reason : null);
    });
    return () => {
      cancelled = true;
    };
  }, [start, end]);

  return (
    <div className="card" role="region" aria-label="Flow drill-down">
      <div className="card-title">
        Flows: {start.toLocaleTimeString()} – {end.toLocaleTimeString()}
        <button onClick={onClose} aria-label="Close drill-down" style={{ marginLeft: 12 }}>
          ×
        </button>
      </div>
      {rows === null && <p>Loading…</p>}
      {rows !== null && rows.length === 0 && (
        <div className="empty-state">
          {emptyReason === "outside_retention"
            ? "This window is outside the configured retention period."
            : "No flows in this window."}
        </div>
      )}
      {rows !== null && rows.length > 0 && (
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
      )}
    </div>
  );
}
