import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { CHART_SERIES_COLORS, CHART_SURFACE, CHART_TEXT_SECONDARY } from "../styles/chartColors";

export interface FlowMapData {
  nodes: { name: string }[];
  links: { source: string; target: string; value: number }[];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** A sankey node is identified by its name, so an address that both sends and
 * receives would otherwise be one shared node — and ECharts would push it into a
 * middle column, turning a source -> destination map into a multi-hop chain that
 * implies traffic routed through it. Prefixing the side keeps the two roles as
 * separate nodes, which pins the diagram to exactly two columns. */
const SRC = "src:";
const DST = "dst:";
const addressOf = (nodeName: string) => nodeName.replace(/^(src|dst):/, "");

/** Flow Map — top source -> destination traffic pairs, as a strict two-column
 * diagram: every ribbon runs left to right from a sender to a receiver, and nothing
 * sits in between. Because the two columns are disjoint sets of nodes, the graph is
 * acyclic by construction, which is what ECharts' sankey requires. */
export function FlowMapSankey({ data }: { data: FlowMapData }) {
  const option = useMemo(() => {
    // Derived from the links rather than data.nodes: the API lists each address once,
    // but this chart needs one node per address *per side*.
    const sources: string[] = [];
    const targets: string[] = [];
    for (const link of data.links) {
      if (!sources.includes(link.source)) sources.push(link.source);
      if (!targets.includes(link.target)) targets.push(link.target);
    }

    // depth is set explicitly so the columns hold even when a side has a single node.
    const nodes = [
      ...sources.map((addr, i) => ({ addr, name: SRC + addr, depth: 0, position: "left", i })),
      ...targets.map((addr, i) => ({
        addr,
        name: DST + addr,
        depth: 1,
        position: "right",
        i: sources.length + i,
      })),
    ];

    return {
      tooltip: {
        trigger: "item",
        formatter: (params: {
          dataType: string;
          data: { source?: string; target?: string; value?: number; name?: string };
        }) =>
          params.dataType === "edge"
            ? `${addressOf(params.data.source ?? "")} → ${addressOf(params.data.target ?? "")}` +
              `<br/>${formatBytes(params.data.value ?? 0)}`
            : addressOf(params.data.name ?? ""),
      },
      series: [
        {
          type: "sankey",
          // Room outside each column for the labels, which sit beyond the nodes
          // rather than on top of the ribbons.
          left: 110,
          right: 110,
          top: 10,
          bottom: 10,
          // Node count is data-driven, so hues do cycle past 8 here. That's sound
          // only because every node is directly labeled with its address — color is
          // a secondary cue on this chart, never the sole carrier of identity.
          data: nodes.map((n) => ({
            name: n.name,
            depth: n.depth,
            // Sources label to their left, destinations to their right, so no label
            // is drawn over the flows.
            label: { position: n.position },
            itemStyle: {
              color: CHART_SERIES_COLORS[n.i % CHART_SERIES_COLORS.length],
              borderColor: CHART_SURFACE,
              borderWidth: 2,
            },
          })),
          links: data.links.map((link) => ({
            source: SRC + link.source,
            target: DST + link.target,
            value: link.value,
          })),
          emphasis: { focus: "adjacency" },
          lineStyle: {
            // "gradient" faded each ribbon from its source hue into its target hue,
            // so neighboring ribbons met in the middle at the same muddy blend and
            // the whole map smeared into one mass. Anchoring each ribbon to its
            // source keeps it one traceable band end to end.
            color: "source",
            // Max curveness made long S-bends that swept across their neighbors;
            // easing it off keeps flows readable where they cross.
            curveness: 0.38,
            opacity: 0.45,
          },
          label: {
            color: CHART_TEXT_SECONDARY,
            fontSize: 11,
            formatter: (params: { name: string }) => addressOf(params.name),
          },
          nodeWidth: 12,
          nodeGap: 14,
        },
      ],
    };
  }, [data]);

  // Tall enough that the node column isn't crushed — a busy capture stacks a dozen
  // endpoints per side, and at 320px they collapsed into each other.
  return <ReactECharts option={option} style={{ height: 420 }} />;
}
