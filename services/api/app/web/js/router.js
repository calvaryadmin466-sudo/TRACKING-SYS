// Hash router + application shell (sidebar nav, topbar, auth gate).
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

const ADMIN = ["super_admin", "company_admin"];

const ROUTES = [
  { path: "/",          title: "Fleet Overview", icon: "layout-dashboard", group: "Operations", nav: true,  mod: overview },
  { path: "/tracking",  title: "Live Tracking",  icon: "map-pin",          group: "Operations", nav: true,  mod: tracking, flush: true },
  { path: "/trips",     title: "Trips & Playback", icon: "route",          group: "Operations", nav: true,  mod: trips },
  { path: "/alerts",    title: "Alerts & Events", icon: "bell",            group: "Operations", nav: true,  mod: alerts },
  { path: "/devices",   title: "Device Management", icon: "cpu",           group: "Fleet",      nav: true,  mod: devices },
  { path: "/drivers",   title: "Drivers",           icon: "id-card",       group: "Fleet",      nav: true,  mod: drivers },
  { path: "/geofences", title: "Geofences",      icon: "hexagon",          group: "Fleet",      nav: true,  mod: geofences, flush: true },
  { path: "/video",     title: "Video Monitoring", icon: "video",          group: "Fleet",      nav: true,  mod: video },
  { path: "/maintenance", title: "Maintenance", icon: "wrench", group: "Fleet", nav: true, mod: maintenance },
  { path: "/reports",   title: "Reports & Analytics", icon: "bar-chart-3", group: "Analytics",  nav: true,  mod: reports },
  { path: "/admin/users", title: "Users & Roles", icon: "users",          group: "Administration", nav: true, roles: ADMIN, mod: admin },
  { path: "/audit",     title: "Audit Log",      icon: "scroll-text",      group: "Administration", nav: true, roles: ADMIN, mod: audit },
  { path: "/notifications", title: "Notifications", icon: "bell", group: "Administration", nav: true, roles: ["super_admin", "company_admin", "fleet_manager"], mod: notifications },
  { path: "/settings",  title: "Settings",       icon: "settings",         group: "Administration", nav: true, mod: settings },
  { path: "/vehicle/:id", title: "Vehicle Details", icon: "truck",         nav: false, mod: vehicle },
];

let currentCleanup = null;
let navPollTimer = null;

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

function shellHtml(user) {
  const canSee = (r) => r.nav && (!r.roles || r.roles.includes(user.role));
  const groups = {};
  for (const r of ROUTES.filter(canSee)) (groups[r.group] ||= []).push(r);
  const navHtml = Object.entries(groups).map(([g, items]) => `
    <div class="group">${g}</div>
    ${items.map((r) => `<a href="#${r.path}" data-path="${r.path}">${icon(r.icon)} <span>${r.title}</span>
      ${r.path === "/alerts" ? `<span class="count hidden" id="nav-alert-count">0</span>` : ""}</a>`).join("")}
  `).join("");
  return `
  <div class="app">
    <aside class="sidebar" id="sidebar">
      <div class="brand">
        <div class="logo">${icon("navigation")}</div>
        <div><b>FleetTrack</b><small>GPS &amp; Video</small></div>
      </div>
      <nav class="nav">${navHtml}</nav>
    </aside>
    <div class="scrim hidden" id="scrim"></div>
    <div class="main">
      <header class="topbar">
        <button class="btn ghost icon hamburger" id="hamburger">${icon("menu")}</button>
        <div><div class="page-title" id="page-title">—</div></div>
        <div class="grow"></div>
        <div class="conn" id="conn"><span class="dot"></span><span id="conn-text">connecting…</span></div>
        <div class="usermenu">
          <div class="avatar">${initials(user.email)}</div>
          <div class="hide-sm"><div style="font-size:13px;font-weight:600">${user.email}</div>
            <div class="dim" style="font-size:11px">${user.role}</div></div>
          <button class="btn ghost icon" id="logout" title="Sign out">${icon("log-out")}</button>
        </div>
      </header>
      <main class="content" id="content"></main>
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
    const badge = qs("#nav-alert-count");
    if (badge) { badge.textContent = n; badge.classList.toggle("hidden", n === 0); }
  } catch {}
}

export function mountShell() {
  const root = qs("#app-root");
  root.innerHTML = shellHtml(session.user);
  refreshIcons(root);
  qs("#logout").addEventListener("click", () => { live.close(); clearToken(); session.user = null; location.hash = "#/login"; location.reload(); });
  qs("#hamburger").addEventListener("click", () => { qs("#sidebar").classList.toggle("open"); qs("#scrim").classList.toggle("hidden"); });
  qs("#scrim").addEventListener("click", () => { qs("#sidebar").classList.remove("open"); qs("#scrim").classList.add("hidden"); });
  live.subscribe(({ connState }) => setConn(connState));
  setConn(live.connState);
  live.connect();
  clearInterval(navPollTimer); pollAlertCount(); navPollTimer = setInterval(pollAlertCount, 20000);
  window.addEventListener("hashchange", route);
  route();
}

async function route() {
  if (!session.user) return;
  const { route: r, params } = match(location.hash);
  qsa(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.path === r.path ||
    (r.path.startsWith("/vehicle") && a.dataset.path === "/devices")));
  qs("#page-title").textContent = r.title;
  qs("#sidebar").classList.remove("open"); qs("#scrim").classList.add("hidden");
  const content = qs("#content");
  content.className = "content" + (r.flush ? " flush" : "");
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
