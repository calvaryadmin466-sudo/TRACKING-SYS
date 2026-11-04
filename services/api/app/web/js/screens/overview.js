import { get } from "../api.js";
import { live } from "../store.js";
import { icon, refreshIcons, qs, fmtAge, fmtDateTime, deviceStatus, isMoving, sevBadge, esc, emptyHtml } from "../ui.js";

export async function render(root, ctx) {
  root.innerHTML = `<div class="page-head"><h2>Fleet Overview</h2><div class="grow"></div>
    <span class="muted" id="ov-updated"></span></div>
    <div class="stats" id="ov-stats"></div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("activity")}<h3>Recent activity</h3>
        <a class="grow right" href="#/alerts" style="font-size:12px">View all</a></div>
        <div id="ov-activity"></div></div>
      <div class="card"><div class="card-head">${icon("satellite-dish")}<h3>Vehicles with stale GPS</h3></div>
        <div id="ov-stale"></div></div>
    </div>
    <div class="toolbar section-gap">
      <a class="btn" href="#/tracking">${icon("map-pin")} Live tracking</a>
      <a class="btn" href="#/trips">${icon("route")} Trips</a>
      <a class="btn" href="#/alerts">${icon("bell")} Alerts</a>
      <a class="btn" href="#/reports">${icon("bar-chart-3")} Reports</a>
    </div>`;
  refreshIcons(root);

  let alive = true;
  async function load() {
    let devices = live.list();
    if (!devices.length) { try { devices = (await get("/api/devices")).devices; } catch { devices = []; } }
    const evResp = await get("/api/events?limit=8").catch(() => ({ events: [], open_alarms: 0 }));
    const openResp = await get("/api/events?acknowledged=false&limit=1").catch(() => ({ open_alarms: 0 }));
    if (!alive || !qs("#ov-stats")) return;  // navigated away during async load

    const total = devices.length;
    const online = devices.filter((d) => deviceStatus(d) === "online").length;
    const offline = devices.filter((d) => deviceStatus(d) === "offline").length;
    const moving = devices.filter(isMoving).length;
    const idle = devices.filter((d) => deviceStatus(d) === "online" && !isMoving(d)).length;
    const stale = devices.filter((d) => d.has_position && d.position && !d.position.fresh);
    const sim = devices.filter((d) => d.simulated).length;

    const stat = (cls, ic, val, label, sub = "") => `<div class="stat ${cls}">
      <div class="ico">${icon(ic)}</div><div class="label">${label}</div>
      <div class="value">${val}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    qs("#ov-stats").innerHTML =
      stat("pri", "truck", total, "Registered Vehicles", sim ? `${sim} simulated` : "") +
      stat("ok", "wifi", online, "Online") +
      stat("", "navigation", moving, "Moving", `${idle} idle`) +
      stat("bad", "wifi-off", offline, "Offline") +
      stat("warn", "satellite-dish", stale.length, "Stale GPS") +
      stat("bad", "bell-ring", openResp.open_alarms || 0, "Open Alerts", "unacknowledged");
    refreshIcons(qs("#ov-stats"));

    const acts = evResp.events || [];
    qs("#ov-activity").innerHTML = acts.length ? acts.map((e) => `
      <div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">
        ${sevBadge(e.severity)}
        <div class="grow" style="min-width:0"><div style="font-weight:600">${esc(e.type.replace(/_/g, " "))}</div>
          <div class="muted" style="font-size:12px">${esc(e.reporting_id)} · ${esc(e.detail || "")}</div></div>
        <div class="dim" style="font-size:12px">${fmtAge(ageOf(e.at))}</div></div>`).join("")
      : emptyHtml("inbox", "No recent events");

    qs("#ov-stale").innerHTML = stale.length ? stale.slice(0, 8).map((d) => `
      <div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">
        ${icon("satellite-dish", "i-sm")}<div class="grow"><a href="#/vehicle/${d.id}" style="font-weight:600">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</a></div>
        <span class="badge stale"><span class="dot"></span>${fmtAge(d.position ? d.position.age_s : null)}</span></div>`).join("")
      : emptyHtml("check-circle", "All GPS fresh", "No vehicles with stale positioning");
    refreshIcons(root);
    qs("#ov-updated").textContent = "Updated " + fmtDateTime(new Date().toISOString());
  }

  function ageOf(iso) { if (!iso) return null; return (Date.now() - new Date(iso).getTime()) / 1000; }

  await load();
  const unsub = live.subscribe(() => { /* throttle */ if (!render._t) render._t = setTimeout(() => { render._t = null; load(); }, 1500); });
  const timer = setInterval(load, 15000);
  return () => { alive = false; unsub(); clearInterval(timer); if (render._t) { clearTimeout(render._t); render._t = null; } };
}
