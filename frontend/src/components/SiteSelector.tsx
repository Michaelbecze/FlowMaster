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
        className="pill-btn"
        aria-selected={selectedSiteId === null}
        onClick={() => onSelect(null)}
      >
        All sites
      </button>
      {sites.map((s) => (
        <button
          key={s.site_id}
          role="tab"
          className="pill-btn"
          aria-selected={selectedSiteId === s.site_id}
          onClick={() => onSelect(s.site_id)}
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          {s.site_id.slice(0, 8)}
          <SiteStatusBadge status={s.status} />
        </button>
      ))}
    </div>
  );
}
