type Status = "active" | "stale" | "never_connected";

const STATUS_META: Record<Status, { label: string; icon: string; color: string }> = {
  active: { label: "Active", icon: "●", color: "var(--status-good)" },
  stale: { label: "Stale — not reporting", icon: "▲", color: "var(--status-warning)" },
  never_connected: { label: "Never connected", icon: "○", color: "var(--text-muted)" },
};

/** Status is never color-alone (dataviz skill status rule): every badge pairs an icon
 * with a text label, distinguishing "no current traffic" from "site not reporting"
 * (FR-004). */
export function SiteStatusBadge({ status }: { status: Status }) {
  const meta = STATUS_META[status];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        color: meta.color,
      }}
    >
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}
