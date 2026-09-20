import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";
import { FlowDrilldown } from "../components/FlowDrilldown";
import { FlowMapSankey, FlowMapData } from "../components/FlowMapSankey";
import { SiteSelector } from "../components/SiteSelector";
import { TrafficBucket, TrafficChart } from "../components/TrafficChart";
import { apiGetJson } from "../services/api";
import { useRealtimeStats } from "../services/realtime";
import {
  CHART_BASELINE,
  CHART_GRIDLINE,
  CHART_OTHER_COLOR,
  CHART_SERIES_COLORS,
  CHART_SURFACE,
  CHART_TEXT_MUTED,
  CHART_TEXT_SECONDARY,
} from "../styles/chartColors";

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

/** A part-to-whole ring only reads at a glance up to ~6 segments, and there are only
 * 8 categorical hues — a real capture sees 14+ applications, which previously meant
 * both a thicket of collided leader lines and hues recycling (HTTPS and RDP both
 * cyan, IMAP and SMB both red) so the legend no longer identified anything. The tail
 * folds into one neutral "Other" instead, merged with whatever the backend already
 * classified as OTHER rather than sitting next to a second bucket of the same name. */
const MAX_NAMED_SLICES = 6;
/** Below this share a direct label is more collision than information; the legend
 * and the hover tooltip carry those slices instead. */
const MIN_LABELED_SHARE = 0.03;

interface PieSlice {
  name: string;
  bytes: number;
  folded: { application: string; bytes: number }[];
}

function toPieSlices(breakdown: { application: string; bytes: number }[]): PieSlice[] {
  const isOther = (application: string) => application.toUpperCase() === "OTHER";
  const named = breakdown
    .filter((b) => !isOther(b.application) && b.bytes > 0)
    .sort((a, b) => b.bytes - a.bytes);
  const top = named.slice(0, MAX_NAMED_SLICES);
  const tail = [
    ...named.slice(MAX_NAMED_SLICES),
    ...breakdown.filter((b) => isOther(b.application) && b.bytes > 0),
  ].sort((a, b) => b.bytes - a.bytes);

  const slices: PieSlice[] = top.map((b) => ({ name: b.application, bytes: b.bytes, folded: [] }));
  if (tail.length > 0) {
    slices.push({
      name: "Other",
      bytes: tail.reduce((sum, b) => sum + b.bytes, 0),
      folded: tail,
    });
  }
  return slices;
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
    const slices = toPieSlices(summary?.data.application_breakdown ?? []);
    const total = slices.reduce((sum, s) => sum + s.bytes, 0);
    const foldedByName = new Map(slices.map((s) => [s.name, s.folded]));

    return {
      tooltip: {
        trigger: "item",
        // Folding the tail must not make it unreachable: hovering "Other" itemizes
        // what went into it, so no application disappears from the dashboard.
        formatter: (params: { name: string; value: number; percent: number }) => {
          const folded = foldedByName.get(params.name) ?? [];
          const head = `${params.name}<br/>${formatBytes(params.value)} (${params.percent}%)`;
          if (folded.length === 0) return head;
          const rows = folded
            .map((b) => `${b.application} — ${formatBytes(b.bytes)}`)
            .join("<br/>");
          return `${head}<hr style="opacity:0.2;margin:4px 0"/>${rows}`;
        },
      },
      legend: {
        show: true,
        bottom: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: CHART_TEXT_SECONDARY, fontSize: 11 },
      },
      series: [
        {
          type: "pie",
          radius: ["48%", "72%"],
          // Raised off-center so the ring never reaches down into the legend band —
          // a bottom-pointing leader line used to land on top of the legend chips.
          center: ["50%", "44%"],
          avoidLabelOverlap: true,
          minAngle: 2,
          // A 2px surface gap, not a stroke around each mark, so touching slivers
          // still read as separate.
          itemStyle: { borderColor: CHART_SURFACE, borderWidth: 2 },
          labelLine: { length: 10, length2: 10 },
          data: slices.map((s, i) => {
            const labeled = total > 0 && s.bytes / total >= MIN_LABELED_SHARE;
            return {
              name: s.name,
              value: s.bytes,
              itemStyle: {
                color: s.name === "Other" ? CHART_OTHER_COLOR : CHART_SERIES_COLORS[i],
              },
              // Selective direct labels: the slices big enough to name are named,
              // the rest are identified by the legend and on hover.
              label: { show: labeled, color: CHART_TEXT_SECONDARY, fontSize: 11 },
              labelLine: { show: labeled },
            };
          }),
        },
      ],
    };
  }, [summary]);

  const talkersOption = useMemo(() => {
    const rows = topTalkers?.data ?? [];
    return {
      tooltip: { valueFormatter: (v: number) => formatBytes(v) },
      // right: the last x-axis tick is centered on the plot edge, so it needs room
      // to overhang — at 20 it was being clipped mid-word ("762.9 MI").
      grid: { left: 90, right: 48, top: 10, bottom: 24 },
      xAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => formatBytes(v), color: CHART_TEXT_MUTED },
        splitLine: { lineStyle: { color: CHART_GRIDLINE } },
        axisLine: { lineStyle: { color: CHART_BASELINE } },
      },
      yAxis: {
        type: "category",
        data: rows.map((r) => r.src_addr).reverse(),
        axisLabel: { color: CHART_TEXT_MUTED },
        axisLine: { lineStyle: { color: CHART_BASELINE } },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          data: rows.map((r) => r.total_bytes).reverse(),
          itemStyle: { color: CHART_SERIES_COLORS[0], borderRadius: [0, 4, 4, 0] },
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
                className="pill-btn"
                aria-selected={range === r}
                onClick={() => setRange(r)}
              >
                {r.toUpperCase()}
              </button>
            ))}
          </div>
          <span
            role="status"
            aria-live="polite"
            className={`live-badge${realtime.connectionState === "reconnecting" ? " reconnecting" : ""}`}
          >
            <span className="pulse-dot" aria-hidden="true" />
            {realtime.connectionState === "connected" && "LIVE"}
            {realtime.connectionState === "connecting" && "CONNECTING…"}
            {realtime.connectionState === "reconnecting" && "RECONNECTING…"}
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
        <div className="card stat-card cyan">
          <div className="card-title">Total Volume ({range})</div>
          <div className="stat-value cyan">
            {liveTotalBytes != null ? formatBytes(liveTotalBytes) : "—"}
          </div>
        </div>
        <div className="card stat-card purple">
          <div className="card-title">Total Packets ({range})</div>
          <div className="stat-value purple">
            {summary?.data.total_packets != null ? summary.data.total_packets.toLocaleString() : "—"}
          </div>
        </div>
        <div className="card stat-card green" style={{ display: "flex", alignItems: "center" }}>
          <button
            onClick={() => setDrilldownWindow({ start: new Date(Date.now() - 5 * 60 * 1000), end: new Date() })}
            style={{ width: "100%" }}
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
            selectedBucket={drilldownWindow?.start ?? null}
            onPointClick={(bucket) => {
              const start = new Date(bucket.bucket);
              setDrilldownWindow({ start, end: new Date(start.getTime() + bucketSeconds * 1000) });
            }}
          />
        ) : (
          <p>Loading…</p>
        )}
        {/* Expands in place under the chart that opened it — clicking a point used to
            jump to the foot of the page, away from the point you clicked. */}
        {drilldownWindow && (
          <FlowDrilldown
            start={drilldownWindow.start}
            end={drilldownWindow.end}
            siteId={selectedSiteId}
            onClose={() => setDrilldownWindow(null)}
          />
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
            <ReactECharts option={protocolOption} style={{ height: 330 }} />
          )}
        </div>
        <div className="card">
          <div className="card-title">Top Talkers</div>
          {topTalkers?.empty ? (
            <div className="empty-state">No traffic in this window.</div>
          ) : (
            <ReactECharts option={talkersOption} style={{ height: 330 }} />
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
    </div>
  );
}
