import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/reports", label: "Reports" },
  { to: "/admin", label: "Admin" },
  { to: "/alerts", label: "Alerts" },
];

export function Layout() {
  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label="Primary">
        <div style={{ fontWeight: 700, padding: "8px 12px 20px", letterSpacing: "0.04em" }}>
          FlowMaster
        </div>
        {/* NavLink sets aria-current="page" on the active route automatically. */}
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
