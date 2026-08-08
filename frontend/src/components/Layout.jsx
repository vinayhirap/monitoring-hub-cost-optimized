// src/components/Layout.jsx
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useState, useEffect } from "react";
import AlertToast from "./AlertToast";
import "./Layout.css";

// Role-based nav visibility:
// admin   → all items
// editor  → overview, alerts, compliance, settings (NO onboarding, NO user mgmt)
// viewer  → overview, alerts, compliance (NO onboarding, NO user mgmt, NO settings)
const NAV_ITEMS = [
  { to: "/overview",   label: "Overview",           icon: OverviewIcon,   roles: ["admin","editor","viewer"] },
  { to: "/alerts",     label: "Alerts",             icon: AlertIcon,      roles: ["admin","editor","viewer"], badge: true },
  { to: "/onboarding", label: "Account Onboarding", icon: OnboardIcon,    roles: ["admin","editor"] },
  { to: "/users",      label: "User Management",    icon: UsersIcon,      roles: ["admin"] },
  { to: "/compliance", label: "Compliance",         icon: ComplianceIcon, roles: ["admin","editor","viewer"] },
  { to: "/settings",   label: "Settings",           icon: SettingsIcon,   roles: ["admin","editor"] },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate          = useNavigate();
  const role              = (user?.role || "viewer").toLowerCase();
  const [now, setNow]     = useState(new Date());
  const [alertCount, setAlertCount] = useState(0);
  const [dark, setDark]   = useState(() => localStorage.getItem("theme") !== "light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    async function fetchCount() {
      try {
        const res = await fetch("/api/alerts/open");
        if (!res.ok) return;
        const data = await res.json();
        const arr = Array.isArray(data) ? data : (data.alerts ?? []);
        setAlertCount(arr.filter(a => (a.status || "").toLowerCase() === "active").length);
      } catch {}
    }
    fetchCount();
    const t = setInterval(fetchCount, 30000);
    return () => clearInterval(t);
  }, []);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  const timeStr = now.toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    timeZone: "Asia/Kolkata",
  });

  const visibleNav = NAV_ITEMS.filter(item => item.roles.includes(role));

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <svg width="28" height="28" viewBox="0 0 36 36" fill="none">
              <rect x="2" y="2" width="32" height="32" rx="8" fill="rgba(0,199,255,0.1)" stroke="rgba(0,199,255,0.35)" strokeWidth="1.5"/>
              <path d="M10 24 L18 12 L26 24" stroke="#00c7ff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M13 20 L23 20" stroke="#00e5a0" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <div className="sidebar-brand-name">ASLOps</div>
            <div className="sidebar-brand-sub">Monitoring Dashboard</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {visibleNav.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`}
            >
              <span className="nav-icon"><Icon /></span>
              <span className="nav-label">{label}</span>
              {badge && alertCount > 0 && (
                <span className="nav-badge">{alertCount}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-last-updated">
            <span className="lup-label">Last updated</span>
            <span className="lup-time">
              {now.toLocaleDateString("en-IN", { month: "short", day: "numeric", year: "numeric" })},{" "}
              {timeStr.split(":").slice(0, 3).join(":")}
            </span>
          </div>
        </div>
      </aside>

      <div className="main-wrap">
        <header className="topbar">
          <div className="topbar-page-label" id="page-label" />
          <div className="topbar-right">
            <div className="live-pill">
              <span className="live-dot" />
              LIVE
            </div>
            <button
              className="btn-theme-toggle"
              onClick={() => setDark(d => !d)}
              title={dark ? "Switch to light theme" : "Switch to dark theme"}
            >
              {dark ? "☀" : "🌙"}
            </button>
            <div className="topbar-clock">
              {timeStr} <span className="topbar-tz">IST</span>
            </div>
            <div className="topbar-user">
              <span className="topbar-user-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                  <circle cx="12" cy="7" r="4"/>
                </svg>
              </span>
              <span className="topbar-username">{user?.username ?? "admin"}</span>
              <span className={`topbar-role-badge role-${role}`}>
                {role.toUpperCase()}
              </span>
            </div>
            <button className="btn-logout" onClick={handleLogout} title="Logout">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              Logout
            </button>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
          <AlertToast />
        </main>
      </div>
    </div>
  );
}

function OverviewIcon()    { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>; }
function AlertIcon()       { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>; }
function OnboardIcon()     { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>; }
function UsersIcon()       { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>; }
function ComplianceIcon()  { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>; }
function SettingsIcon()    { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>; }
