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
        <div className="app-logo">
          <svg viewBox="0 0 28 28" fill="none" width="24" height="24" aria-hidden="true">
            <path
              d="M2 18 Q7 8 14 14 Q21 20 26 10"
              stroke="#00d4ff"
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
            <path
              d="M2 22 Q7 12 14 18 Q21 24 26 14"
              stroke="#8b5cf6"
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
              opacity="0.7"
            />
          </svg>
          FLOWMASTER
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
