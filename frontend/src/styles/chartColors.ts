/**
 * Resolved color values for use inside ECharts `option` objects.
 *
 * ECharts paints directly to a <canvas> via the Canvas 2D API (fillStyle,
 * strokeStyle, CanvasGradient.addColorStop, ...). Those setters parse a raw
 * CSS <color> value with no access to an element's computed style, so a
 * `var(--token)` string — valid in JSX `style={{ }}` props, which the DOM
 * resolves against computed style — is not a valid color there and throws
 * (e.g. "CanvasGradient.addColorStop: Invalid color") or is silently
 * dropped. Anything handed to an ECharts option must therefore use a
 * concrete value, not a CSS custom property reference.
 *
 * Keep these in sync with the token values in ./theme.css.
 */

export const CHART_SERIES_COLORS = [
  "#00d4ff", // --series-1 / --cyan
  "#8b5cf6", // --series-2 / --purple
  "#10b981", // --series-3 / --green
  "#f59e0b", // --series-4 / --orange
  "#ec4899", // --series-5 / --pink
  "#ef4444", // --series-6 / --red
  "#3b82f6", // --series-7 / --blue
  "#eab308", // --series-8 / --yellow
];

export const CHART_TEXT_SECONDARY = "#94a3b8"; // --text-secondary
export const CHART_TEXT_MUTED = "#64748b"; // --text-muted
