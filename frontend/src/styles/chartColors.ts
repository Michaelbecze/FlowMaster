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

/**
 * Categorical slots, in assignment order. These are theme.css's --cyan/--purple/...
 * hues unchanged (the dark glowing NOC palette is deliberate design direction) —
 * only the *order* differs from the --series-N numbering, and the order is load-
 * bearing, not cosmetic: slots are consumed in sequence, so slot N and slot N+1 are
 * what a reader has to tell apart. The theme's own numbering puts --pink beside
 * --red, which is ΔE 11.4 in normal vision — below the 15 floor, i.e. confusable
 * even with full color vision, and worse under simulated protanopia.
 *
 * This order was picked by running the palette through a CVD/separation validator
 * and maximizing the worst adjacent pair, pinned to cyan-first so the single-series
 * charts keep the app's signature accent. It scores ΔE 26.0 normal / 20.0 CVD on
 * its worst adjacent pair against the card surface.
 *
 * Re-run the validator before reordering or extending this.
 */
export const CHART_SERIES_COLORS = [
  "#00d4ff", // --cyan
  "#f59e0b", // --orange
  "#ec4899", // --pink
  "#eab308", // --yellow
  "#8b5cf6", // --purple
  "#10b981", // --green
  "#3b82f6", // --blue
  "#ef4444", // --red
];

/** The remainder bucket is not an identity, so it gets neutral ink rather than
 * consuming a categorical hue. */
export const CHART_OTHER_COLOR = "#64748b"; // --text-muted

/** Card surface (--surface-1 composited over --page-plane). Used as the 2px gap
 * between adjacent fills, so touching segments read as separate without drawing a
 * border around each mark. */
export const CHART_SURFACE = "#081129";

export const CHART_TEXT_SECONDARY = "#94a3b8"; // --text-secondary
export const CHART_TEXT_MUTED = "#64748b"; // --text-muted

/** Grid and axis rules stay one shade off the surface so they never compete with
 * the data — ECharts' own defaults are considerably brighter than these tokens. */
export const CHART_GRIDLINE = "rgba(255, 255, 255, 0.06)"; // --gridline
export const CHART_BASELINE = "rgba(255, 255, 255, 0.12)"; // --baseline
