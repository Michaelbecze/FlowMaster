import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import {
  CHART_BASELINE,
  CHART_GRIDLINE,
  CHART_SERIES_COLORS,
  CHART_SURFACE,
  CHART_TEXT_MUTED,
} from "../styles/chartColors";

export interface TrafficBucket {
  bucket: string;
  total_bytes: number;
  total_packets: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** Traffic-volume time series (User Story 1) — click a point to drill down into the
 * flow records for that bucket (FR-003). */
export function TrafficChart({
  data,
  bucketSeconds,
  selectedBucket,
  onPointClick,
}: {
  data: TrafficBucket[];
  bucketSeconds: number;
  /** Start of the bucket whose flow list is currently open, if any. */
  selectedBucket?: Date | null;
  onPointClick: (bucket: TrafficBucket) => void;
}) {
  // Compared as parsed instants, not as strings: the drill-down window is built by
  // round-tripping the bucket through a Date, which need not re-serialize to the
  // byte-identical string the API sent (offset spelling, millisecond precision), and
  // a string compare would just silently never match.
  const selectedAt = selectedBucket ? selectedBucket.getTime() : null;
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis", valueFormatter: (v: number) => formatBytes(v) },
      grid: { left: 60, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: "category",
        data: data.map((d) => d.bucket),
        axisLabel: {
          formatter: (value: string) =>
            new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          color: CHART_TEXT_MUTED,
        },
        axisLine: { lineStyle: { color: CHART_BASELINE } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => formatBytes(v), color: CHART_TEXT_MUTED },
        splitLine: { lineStyle: { color: CHART_GRIDLINE } },
        axisLine: { lineStyle: { color: CHART_BASELINE } },
      },
      series: [
        {
          type: "line",
          // The open bucket is marked on the chart itself, so it stays obvious which
          // point the flow list below belongs to — and which one is still open after
          // the 15s refresh repaints the series.
          data: data.map((d) => ({
            value: d.total_bytes,
            ...(selectedAt !== null && new Date(d.bucket).getTime() === selectedAt
              ? {
                  symbolSize: 13,
                  itemStyle: {
                    color: CHART_SERIES_COLORS[0],
                    borderColor: CHART_SURFACE,
                    borderWidth: 2,
                  },
                }
              : {}),
          })),
          smooth: true,
          symbolSize: 7,
          lineStyle: { color: CHART_SERIES_COLORS[0], width: 2 },
          itemStyle: { color: CHART_SERIES_COLORS[0] },
          areaStyle: { color: CHART_SERIES_COLORS[0], opacity: 0.12 },
        },
      ],
    }),
    [data, selectedAt],
  );

  function onChartClick(params: { dataIndex: number }) {
    const bucket = data[params.dataIndex];
    if (bucket) onPointClick(bucket);
  }

  return (
    <div>
      <ReactECharts
        option={option}
        style={{ height: 260 }}
        onEvents={{ click: onChartClick }}
      />
      <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "4px 0 0" }}>
        Click a point to see the individual flows for that {bucketSeconds >= 3600 ? "hour" : "minute"}.
      </p>
    </div>
  );
}
