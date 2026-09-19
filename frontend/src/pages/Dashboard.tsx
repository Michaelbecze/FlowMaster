import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";
import { FlowDrilldown } from "../components/FlowDrilldown";
import { FlowMapSankey, FlowMapData } from "../components/FlowMapSankey";
import { SiteSelector } from "../components/SiteSelector";
import { TrafficBucket, TrafficChart } from "../components/TrafficChart";
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

const RANGE_OPTIONS = ["1h", "3h", "6h", "12h", "24h"] as const;
type Range = (typeof RANGE_OPTIONS)[number];
const RANGE_TO_HOURS: Record<Range, number> = { "1h": 1, "3h": 3, "6h": 6, "12h": 12, "24h": 24 };
const FINE_BUCKET_RANGE_HOURS = 2;

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

interface TrafficOverTimeEnvelope {
  data: TrafficBucket[];
  empty: boolean;
}

interface FlowMapEnvelope {
  data: FlowMapData;
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
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [range, setRange] = useState<Range>("1h");

  const [summary, setSummary] = useState<SummaryEnvelope | null>(null);
  const [topTalkers, setTopTalkers] = useState<TopTalkersEnvelope | null>(null);
  const [trafficOverTime, setTrafficOverTime] = useState<TrafficOverTimeEnvelope | null>(null);
  const [flowMap, setFlowMap] = useState<FlowMapEnvelope | null>(null);

  const [drilldownWindow, setDrilldownWindow] = useState<{ start: Date; end: Date } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const allSiteIds = useMemo(() => sites.map((s) => s.site_id), [sites]);
  // Selecting a site scopes every chart to it; "All sites" (null) keeps the
  // org-wide aggregate view every endpoint already supports via a multi-id filter.
  const scopedSiteIds = selectedSiteId ? [selectedSiteId] : allSiteIds;
  const realtime = useRealtimeStats(scopedSiteIds);

  useEffect(() => {
    apiGetJson<{ data: SiteStatusRow[] }>("/api/v1/query/sites/status")
      .then((res) => setSites(res.data))
      .catch(() => setLoadError("Failed to load sites. Retrying…"));
  }, []);

  useEffect(() => {
    if (scopedSiteIds.length === 0) return;
    const sitesParam = scopedSiteIds.join(",");

    async function refresh(): Promise<void> {
      try {
        const [summaryRes, talkersRes, trafficRes, flowMapRes] = await Promise.all([
          apiGetJson<SummaryEnvelope>(`/api/v1/query/summary?range=${range}&sites=${sitesParam}`),
          apiGetJson<TopTalkersEnvelope>(`/api/v1/query/top-talkers?range=${range}&sites=${sitesParam}`),
          apiGetJson<TrafficOverTimeEnvelope>(
            `/api/v1/query/traffic-over-time?range=${range}&sites=${sitesParam}`,
          ),
          apiGetJson<FlowMapEnvelope>(`/api/v1/query/flow-map?range=${range}&sites=${sitesParam}`),
        ]);
        setSummary(summaryRes);
        setTopTalkers(talkersRes);
        setTrafficOverTime(trafficRes);
        setFlowMap(flowMapRes);
        setLoadError(null);
      } catch {
        // A failed refresh must not leave every widget stuck on "Loading…" forever
        // with no indication anything went wrong; the previous successful data (if
        // any) stays on screen and this banner explains why it's stale.
        setLoadError("Failed to refresh dashboard data. Retrying every 15s…");
      }
    }

    refresh();
    const interval = setInterval(refresh, FULL_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
    // Depends on scopedSiteIds.join(",") (a stable string), not the array reference,
    // so this only re-fires when the actual site selection changes.
  }, [scopedSiteIds.join(","), range]);

  const liveTotalBytes = realtime.latestStats?.summary.total_bytes ?? summary?.data.total_bytes;
  const bucketSeconds = RANGE_TO_HOURS[range] <= FINE_BUCKET_RANGE_HOURS ? 60 : 3600;

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
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <h1 style={{ fontSize: 18, margin: 0 }}>Dashboard</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div role="tablist" aria-label="Time range" style={{ display: "flex", gap: 4 }}>
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r}
                role="tab"
                aria-selected={range === r}
                onClick={() => setRange(r)}
                style={{
                  padding: "4px 10px",
                  fontSize: 12,
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  background: range === r ? "var(--series-1)" : "transparent",
                  color: range === r ? "#fff" : "var(--text-primary)",
                }}
              >
                {r.toUpperCase()}
              </button>
            ))}
          </div>
          <span role="status" aria-live="polite" style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {realtime.connectionState === "connected" && "● Live"}
            {realtime.connectionState === "connecting" && "Connecting…"}
            {realtime.connectionState === "reconnecting" && "⚠ Reconnecting…"}
          </span>
        </div>
      </div>

      {loadError && (
        <div
          role="alert"
          className="card"
          style={{ marginBottom: 20, color: "var(--status-critical)" }}
        >
          {loadError}
        </div>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">Site</div>
        <SiteSelector sites={sites} selectedSiteId={selectedSiteId} onSelect={setSelectedSiteId} />
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
          <div className="card-title">Total Volume ({range})</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>
            {liveTotalBytes != null ? formatBytes(liveTotalBytes) : "—"}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Total Packets ({range})</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>
            {summary?.data.total_packets != null ? summary.data.total_packets.toLocaleString() : "—"}
          </div>
        </div>
        <div className="card">
          <button
            onClick={() => setDrilldownWindow({ start: new Date(Date.now() - 5 * 60 * 1000), end: new Date() })}
            style={{ width: "100%", padding: 10 }}
          >
            View flows (last 5m)
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">Traffic Volume</div>
        {trafficOverTime?.empty ? (
          <div className="empty-state">No traffic in this window.</div>
        ) : trafficOverTime ? (
          <TrafficChart
            data={trafficOverTime.data}
            bucketSeconds={bucketSeconds}
            onPointClick={(bucket) => {
              const start = new Date(bucket.bucket);
              setDrilldownWindow({ start, end: new Date(start.getTime() + bucketSeconds * 1000) });
            }}
          />
        ) : (
          <p>Loading…</p>
        )}
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

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">Flow Map</div>
        {flowMap?.empty ? (
          <div className="empty-state">No traffic in this window.</div>
        ) : flowMap ? (
          <FlowMapSankey data={flowMap.data} />
        ) : (
          <p>Loading…</p>
        )}
      </div>

      {drilldownWindow && (
        <FlowDrilldown
          start={drilldownWindow.start}
          end={drilldownWindow.end}
          siteId={selectedSiteId}
          onClose={() => setDrilldownWindow(null)}
        />
      )}
    </div>
  );
}
