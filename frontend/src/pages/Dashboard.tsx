import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";
import { FlowDrilldown } from "../components/FlowDrilldown";
import { SiteStatusBadge } from "../components/SiteStatusBadge";
import { apiGetJson } from "../services/api";
import { useRealtimeStats } from "../services/realtime";

const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];

interface SiteStatusRow {
  site_id: string;
  status: "active" | "stale" | "never_connected";
  last_seen_at: string | null;
}

interface SummaryEnvelope {
  data: {
    total_bytes: number;
    total_packets: number;
    application_breakdown: { application: string; bytes: number }[];
  };
  empty: boolean;
  reason: string | null;
}

interface TopTalkersEnvelope {
  data: { src_addr: string; total_bytes: number }[];
  empty: boolean;
}

const FULL_REFRESH_INTERVAL_MS = 15_000;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function Dashboard() {
  const [sites, setSites] = useState<SiteStatusRow[]>([]);
  const [summary, setSummary] = useState<SummaryEnvelope | null>(null);
  const [topTalkers, setTopTalkers] = useState<TopTalkersEnvelope | null>(null);
  const [drilldownOpen, setDrilldownOpen] = useState(false);

  const siteIds = useMemo(() => sites.map((s) => s.site_id), [sites]);
  const realtime = useRealtimeStats(siteIds);

  useEffect(() => {
    apiGetJson<{ data: SiteStatusRow[] }>("/api/v1/query/sites/status").then((res) =>
      setSites(res.data),
    );
  }, []);

  useEffect(() => {
    if (siteIds.length === 0) return;
    const sitesParam = siteIds.join(",");

    async function refresh(): Promise<void> {
      const [summaryRes, talkersRes] = await Promise.all([
        apiGetJson<SummaryEnvelope>(`/api/v1/query/summary?range=1h&sites=${sitesParam}`),
        apiGetJson<TopTalkersEnvelope>(`/api/v1/query/top-talkers?range=1h&sites=${sitesParam}`),
      ]);
      setSummary(summaryRes);
      setTopTalkers(talkersRes);
    }

    refresh();
    const interval = setInterval(refresh, FULL_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [siteIds]);

  const liveTotalBytes = realtime.latestStats?.summary.total_bytes ?? summary?.data.total_bytes;

  const protocolOption = useMemo(() => {
    const breakdown = summary?.data.application_breakdown ?? [];
    return {
      tooltip: { trigger: "item", valueFormatter: (v: number) => formatBytes(v) },
      legend: { show: true, bottom: 0, textStyle: { color: "var(--text-secondary)" } },
      series: [
        {
          type: "pie",
          radius: ["55%", "80%"],
          data: breakdown.map((b, i) => ({
            name: b.application,
            value: b.bytes,
            itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
          })),
        },
      ],
    };
  }, [summary]);

  const talkersOption = useMemo(() => {
    const rows = topTalkers?.data ?? [];
    return {
      tooltip: { valueFormatter: (v: number) => formatBytes(v) },
      grid: { left: 90, right: 20, top: 10, bottom: 20 },
      xAxis: { type: "value", axisLabel: { formatter: (v: number) => formatBytes(v) } },
      yAxis: { type: "category", data: rows.map((r) => r.src_addr).reverse() },
      series: [
        {
          type: "bar",
          data: rows.map((r) => r.total_bytes).reverse(),
          itemStyle: { color: "var(--series-1)", borderRadius: [0, 4, 4, 0] },
        },
      ],
    };
  }, [topTalkers]);

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <h1 style={{ fontSize: 18, margin: 0 }}>Dashboard</h1>
        <span role="status" aria-live="polite" style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {realtime.connectionState === "connected" && "● Live"}
          {realtime.connectionState === "connecting" && "Connecting…"}
          {realtime.connectionState === "reconnecting" && "⚠ Reconnecting…"}
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div className="card">
          <div className="card-title">Total Volume (1h)</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>
            {liveTotalBytes != null ? formatBytes(liveTotalBytes) : "—"}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Sites</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {sites.length === 0 && <span className="empty-state">No sites onboarded yet</span>}
            {sites.map((s) => (
              <div key={s.site_id} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{s.site_id.slice(0, 8)}</span>
                <SiteStatusBadge status={realtime.siteStatus[s.site_id] ?? s.status} />
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <button onClick={() => setDrilldownOpen(true)} style={{ width: "100%", padding: 10 }}>
            View flows (last 5m)
          </button>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div className="card">
          <div className="card-title">Application Breakdown</div>
          {summary?.empty ? (
            <div className="empty-state">No traffic in this window.</div>
          ) : (
            <ReactECharts option={protocolOption} style={{ height: 260 }} />
          )}
        </div>
        <div className="card">
          <div className="card-title">Top Talkers</div>
          {topTalkers?.empty ? (
            <div className="empty-state">No traffic in this window.</div>
          ) : (
            <ReactECharts option={talkersOption} style={{ height: 260 }} />
          )}
        </div>
      </div>

      {drilldownOpen && (
        <FlowDrilldown
          start={new Date(Date.now() - 5 * 60 * 1000)}
          end={new Date()}
          onClose={() => setDrilldownOpen(false)}
        />
      )}
    </div>
  );
}
