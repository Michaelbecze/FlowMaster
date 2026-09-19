import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

export interface FlowMapData {
  nodes: { name: string }[];
  links: { source: string; target: string; value: number }[];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

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

/** Flow Map (top source -> destination traffic pairs) — restores the single-process
 * dashboard's Sankey view. ECharts' sankey series requires an acyclic graph; the
 * backend (services/query-api/src/routes/flow_map.py) already merges any
 * bidirectional pair into a single link before this ever sees the data. */
export function FlowMapSankey({ data }: { data: FlowMapData }) {
  const option = useMemo(
    () => ({
      tooltip: {
        trigger: "item",
        formatter: (params: { dataType: string; data: { source?: string; target?: string; value?: number; name?: string } }) =>
          params.dataType === "edge"
            ? `${params.data.source} → ${params.data.target}<br/>${formatBytes(params.data.value ?? 0)}`
            : params.data.name ?? "",
      },
      series: [
        {
          type: "sankey",
          data: data.nodes.map((n, i) => ({
            name: n.name,
            itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
          })),
          links: data.links,
          emphasis: { focus: "adjacency" },
          lineStyle: { color: "gradient", curveness: 0.5, opacity: 0.4 },
          label: { color: "var(--text-secondary)", fontSize: 11 },
          nodeWidth: 14,
          nodeGap: 10,
        },
      ],
    }),
    [data],
  );

  return <ReactECharts option={option} style={{ height: 320 }} />;
}
