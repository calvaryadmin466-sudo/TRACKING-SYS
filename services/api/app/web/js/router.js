// Hash router + application shell.
// App-like navigation: a left sidebar on desktop (primary tabs + tool groups)
// and a bottom tab bar on phones (Monitor / Board / Service / Alarm / Mine),
// mirroring the fleet-app structure the operators already know.
import { clearToken, get } from "./api.js";
import { session, live } from "./store.js";
import { icon, refreshIcons, qs, qsa, initials, toast } from "./ui.js";

import * as overview from "./screens/overview.js";
import * as tracking from "./screens/tracking.js";
import * as trips from "./screens/trips.js";
import * as alerts from "./screens/alerts.js";
import * as devices from "./screens/devices.js";
import * as geofences from "./screens/geofences.js";
import * as video from "./screens/video.js";
import * as reports from "./screens/reports.js";
import * as vehicle from "./screens/vehicle.js";
import * as admin from "./screens/admin.js";
import * as audit from "./screens/audit.js";
import * as settings from "./screens/settings.js";
import * as maintenance from "./screens/maintenance.js";
import * as notifications from "./screens/notifications.js";
import * as drivers from "./screens/drivers.js";
import * as service from "./screens/service.js";
import * as mine from "./screens/mine.js";

const ADMIN = ["super_admin", "company_admin"];
const MGR = ["super_admin", "company_admin", "fleet_manager"];

// Five primary tabs — the top-level navigation shared by the desktop sidebar
// and the mobile bottom bar.
const TABS = [
  { tab: "monitor", path: "/tracking", title: "Monitor", icon: "map-pin" },
  { tab: "board",   path: "/",         title: "Board",   icon: "layout-dashboard" },
  { tab: "service", path: "/service",  title: "Service", icon: "grid" },
  { tab: "alarm",   path: "/alerts",   title: "Alarm",   icon: "bell" },
  { tab: "mine",    path: "/mine",     title: "Mine",    icon: "user" },
];

// Every route carries the primary `tab` it belongs to (drives active state in
// both navs). `tool` marks a route that also appears in the Service hub and the
// desktop sidebar's tool section, grouped by the tool label.
const ROUTES = [
  { path: "/",             title: "Board",               icon: "layout-dashboard", tab: "board",   mod: overview },
  { path: "/tracking",     title: "Live Monitor",        icon: "map-pin",          tab: "monitor", flush: true, mod: tracking },
  { path: "/service",      title: "Service",             icon: "grid",             tab: "service", mod: service },
  { path: "/alerts",       title: "Alarms & Events",     icon: "bell",             tab: "alarm",   mod: alerts },
  { path: "/mine",         title: "My Account",          icon: "user",             tab: "mine",    mod: mine },

  { path: "/trips",        title: "Trips & Playback",    icon: "route",            tab: "service", tool: "Operations", mod: trips },
  { path: "/video",        title: "Video Monitoring",    icon: "video",            tab: "service", tool: "Operations", mod: video },
  { path: "/devices",      title: "Device Management",   icon: "cpu",              tab: "service", tool: "Fleet",      mod: devices },
  { path: "/drivers",      title: "Drivers",             icon: "id-card",          tab: "service", tool: "Fleet",      mod: drivers },
  { path: "/geofences",    title: "Geofences",           icon: "hexagon",          tab: "service", tool: "Fleet",      flush: true, mod: geofences },
  { path: "/maintenance",  title: "Maintenance",         icon: "wrench",           tab: "service", tool: "Fleet",      mod: maintenance },
  { path: "/reports",      title: "Reports & Analytics", icon: "bar-chart-3",      tab: "service", tool: "Analytics",  mod: reports },
  { path: "/admin/users",  title: "Users & Roles",       icon: "users",            tab: "service", tool: "Management", roles: ADMIN, mod: admin },
  { path: "/notifications",title: "Notification Rules",  icon: "bell-ring",        tab: "service", tool: "Management", roles: MGR,   mod: notifications },
  { path: "/audit",        title: "Audit Log",           icon: "scroll-text",      tab: "service", tool: "Management", roles: ADMIN, mod: audit },
  { path: "/settings",     title: "Settings",            icon: "settings",         tab: "mine",    mod: settings },

  { path: "/vehicle/:id",  title: "Vehicle Details",     icon: "truck",            tab: "monitor", mod: vehicle },
];

let currentCleanup = null;
let navPollTimer = null;

// Exposed to the Service hub (and reused for the desktop tool list). Returns the
// role-visible tool routes grouped by their `tool` label, preserving order.
export function serviceToolGroups(user) {
  const canSee = (r) => !r.roles || r.roles.includes(user.role);
  const groups = {};
  for (const r of ROUTES) {
    if (r.tab === "service" && r.tool && canSee(r)) (groups[r.tool] ||= []).push(r);
  }
  return groups;
}

function match(hash) {
  const path = (hash || "#/").replace(/^#/, "") || "/";
  for (const r of ROUTES) {
    if (!r.path.includes(":")) { if (r.path === path) return { route: r, params: {} }; continue; }
    const rp = r.path.split("/"), pp = path.split("/");
    if (rp.length !== pp.length) continue;
    const params = {}; let ok = true;
    for (let i = 0; i < rp.length; i++) {
      if (rp[i].startsWith(":")) params[rp[i].slice(1)] = decodeURIComponent(pp[i]);
      else if (rp[i] !== pp[i]) { ok = false; break; }
    }
    if (ok) return { route: r, params };
  }
  return { route: ROUTES[0], params: {} };
}

function primaryNavHtml() {
  return TABS.map((t) => `
    <a href="#${t.path}" class="nav-item" data-tab="${t.tab}">
      <span class="ni-ic">${icon(t.icon)}</span><span class="ni-lbl">${t.title}</span>
      ${t.tab === "alarm" ? `<span class="count nav-alert-count hidden">0</span>` : ""}
    </a>`).join("");
}

function toolNavHtml(user) {
  const groups = serviceToolGroups(user);
  return Object.entries(groups).map(([g, items]) => `
    <div class="group">${g}</div>
    ${items.map((r) => `<a href="#${r.path}" class="nav-link" data-path="${r.path}">${icon(r.icon)}<span>${r.title}</span></a>`).join("")}
  `).join("");
}

function shellHtml(user) {
  const primary = primaryNavHtml();
  return `
  <div class="app">
    <aside class="sidebar" id="sidebar">
      <div class="brand">
        <div class="logo">${icon("navigation")}</div>
        <div><b>FleetTrack</b><small>GPS &amp; Video</small></div>
      </div>
      <nav class="nav">
        <div class="nav-primary">${primary}</div>
        <div class="nav-tools">${toolNavHtml(user)}</div>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="tb-brand"><div class="logo">${icon("navigation")}</div><b>FleetTrack</b></div>
        <div class="page-title" id="page-title">—</div>
        <div class="grow"></div>
        <div class="conn" id="conn"><span class="dot"></span><span id="conn-text" class="hide-xs">connecting…</span></div>
        <div class="usermenu">
          <div class="avatar">${initials(user.email)}</div>
          <div class="hide-sm"><div style="font-size:13px;font-weight:600">${user.email}</div>
            <div class="dim" style="font-size:11px">${user.role}</div></div>
          <button class="btn ghost icon hide-sm" id="logout" title="Sign out">${icon("log-out")}</button>
        </div>
      </header>
      <main class="content" id="content"></main>
      <nav class="bottom-nav">${primary}</nav>
    </div>
  </div>`;
}

function setConn(state) {
  const el = qs("#conn"), txt = qs("#conn-text");
  if (!el) return;
  el.className = "conn " + (state === "live" ? "live" : state === "stale" ? "stale" : state === "connecting" ? "" : "down");
  txt.textContent = state === "live" ? "Live" : state === "stale" ? "Feed stale" : state === "connecting" ? "Connecting…" : "Disconnected";
}

async function pollAlertCount() {
  try {
    const data = await get("/api/events?acknowledged=false&limit=1");
    const n = data.open_alarms || 0;
    qsa(".nav-alert-count").forEach((b) => { b.textContent = n; b.classList.toggle("hidden", n === 0); });
  } catch {}
}

function signOut() {
  live.close(); clearToken(); session.user = null; location.hash = "#/login"; location.reload();
}

export function mountShell() {
  const root = qs("#app-root");
  root.innerHTML = shellHtml(session.user);
  refreshIcons(root);
  qs("#logout").addEventListener("click", signOut);
  live.subscribe(({ connState }) => setConn(connState));
  setConn(live.connState);
  live.connect();
  clearInterval(navPollTimer); pollAlertCount(); navPollTimer = setInterval(pollAlertCount, 20000);
  window.addEventListener("hashchange", route);
  route();
}

// Exposed so screens (e.g. Mine) can trigger sign-out.
export { signOut };

async function route() {
  if (!session.user) return;
  const { route: r, params } = match(location.hash);
  qsa(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.tab === r.tab));
  qsa(".nav-link").forEach((a) => a.classList.toggle("active", a.dataset.path === r.path));
  qs("#page-title").textContent = r.title;
  const content = qs("#content");
  content.className = "content" + (r.flush ? " flush" : "");
  content.scrollTop = 0;
  if (currentCleanup) { try { currentCleanup(); } catch {} currentCleanup = null; }
  content.innerHTML = `<div class="state"><div class="spinner"></div></div>`;
  try {
    const cleanup = await r.mod.render(content, { params, user: session.user, navigate: (p) => location.hash = "#" + p });
    currentCleanup = typeof cleanup === "function" ? cleanup : null;
    refreshIcons(content);
    pollAlertCount();
  } catch (e) {
    content.innerHTML = `<div class="state">${icon("triangle-alert", "i-lg")}<h4>Failed to load</h4><div class="muted">${(e && e.detail) || e.message || "error"}</div></div>`;
    refreshIcons(content);
    if (e && e.status !== 401) toast((e.detail || e.message || "Load failed"), "error");
  }
}
