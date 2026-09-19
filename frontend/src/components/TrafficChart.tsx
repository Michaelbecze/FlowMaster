import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

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
  onPointClick,
}: {
  data: TrafficBucket[];
  bucketSeconds: number;
  onPointClick: (bucket: TrafficBucket) => void;
}) {
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
        },
      },
      yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatBytes(v) } },
      series: [
        {
          type: "line",
          data: data.map((d) => d.total_bytes),
          smooth: true,
          symbolSize: 7,
          lineStyle: { color: "var(--series-1)", width: 2 },
          itemStyle: { color: "var(--series-1)" },
          areaStyle: { color: "var(--series-1)", opacity: 0.12 },
        },
      ],
    }),
    [data],
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
