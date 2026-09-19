import { SiteStatusBadge } from "./SiteStatusBadge";

export interface SelectableSite {
  site_id: string;
  status: "active" | "stale" | "never_connected";
}

/** Selecting a site scopes every chart on the dashboard to it (per the user's
 * request to make a site selectable). "All sites" (the default) keeps the
 * org-wide aggregate view. */
export function SiteSelector({
  sites,
  selectedSiteId,
  onSelect,
}: {
  sites: SelectableSite[];
  selectedSiteId: string | null;
  onSelect: (siteId: string | null) => void;
}) {
  return (
    <div role="tablist" aria-label="Site" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <button
        role="tab"
        aria-selected={selectedSiteId === null}
        onClick={() => onSelect(null)}
        style={{
          padding: "6px 12px",
          borderRadius: 20,
          border: "1px solid var(--border)",
          background: selectedSiteId === null ? "var(--series-1)" : "transparent",
          color: selectedSiteId === null ? "#fff" : "var(--text-primary)",
        }}
      >
        All sites
      </button>
      {sites.map((s) => (
        <button
          key={s.site_id}
          role="tab"
          aria-selected={selectedSiteId === s.site_id}
          onClick={() => onSelect(s.site_id)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 12px",
            borderRadius: 20,
            border: "1px solid var(--border)",
            background: selectedSiteId === s.site_id ? "var(--series-1)" : "transparent",
            color: selectedSiteId === s.site_id ? "#fff" : "var(--text-primary)",
          }}
        >
          {s.site_id.slice(0, 8)}
          <SiteStatusBadge status={s.status} />
        </button>
      ))}
    </div>
  );
}
