import { get } from "../api.js";
import { live } from "../store.js";
import { COLORS } from "../map.js?v=20261105";
import { icon, refreshIcons, qs, fmtAge, fmtDateTime, num, deviceStatus, isMoving, sevBadge, esc, emptyHtml, loadingHtml } from "../ui.js";

const PERIODS = [
  { k: "1", label: "24h", days: 1 },
  { k: "7", label: "7 days", days: 7 },
  { k: "30", label: "30 days", days: 30 },
];

// SVG donut from mutually-exclusive segments (slices sum to the total).
function donut(segs) {
  const total = segs.reduce((s, x) => s + x.value, 0);
  const r = 46, C = 2 * Math.PI * r;
  let off = 0;
  const arcs = total === 0
    ? `<circle cx="60" cy="60" r="${r}" fill="none" stroke="var(--panel-3)" stroke-width="15"/>`
    : segs.filter((s) => s.value > 0).map((s) => {
        const len = (s.value / total) * C;
        const el = `<circle cx="60" cy="60" r="${r}" fill="none" stroke="${s.color}" stroke-width="15"
          stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)" stroke-linecap="butt"/>`;
        off += len; return el;
      }).join("");
  return `<svg viewBox="0 0 120 120" width="120" height="120" class="donut-svg">${arcs}
    <text x="60" y="57" text-anchor="middle" class="donut-num">${total}</text>
    <text x="60" y="74" text-anchor="middle" class="donut-lbl">vehicles</text></svg>`;
}

// Horizontal ranking bars for the top vehicles by a numeric key.
function rankBars(rows, key, unit, color, dp = 0) {
  const top = rows.filter((r) => (r[key] || 0) > 0).sort((a, b) => b[key] - a[key]).slice(0, 6);
  if (!top.length) return emptyHtml("inbox", "No data in range");
  const max = top[0][key] || 1;
  return `<div class="rank">${top.map((r) => `
    <div class="rank-row">
      <div class="rank-head"><span class="rank-name">${esc(r.vehicle || r.reporting_id)}</span>
        <span class="rank-val">${num(r[key], dp)}${unit ? `<span class="rank-u">${unit}</span>` : ""}</span></div>
      <div class="rank-track"><div class="rank-fill" style="width:${Math.max(4, Math.round(100 * r[key] / max))}%;background:${color}"></div></div>
    </div>`).join("")}</div>`;
}

export async function render(root, ctx) {
  let period = PERIODS[1]; // default 7 days

  root.innerHTML = `
    <div class="page-head"><h2>Board</h2>
      <div class="grow"></div>
      <div class="filters" id="ov-period">${PERIODS.map((p) => `<button class="chip-toggle ${p === period ? "on" : ""}" data-k="${p.k}">${p.label}</button>`).join("")}</div>
      <span class="muted" id="ov-updated" style="margin-left:6px"></span></div>
    <div class="stats" id="ov-stats"></div>
    <div class="grid-3 section-gap">
      <div class="card"><div class="card-head">${icon("layout-dashboard")}<h3>Fleet status</h3></div>
        <div class="card-pad donut-wrap" id="ov-donut"></div></div>
      <div class="card"><div class="card-head">${icon("bell-ring")}<h3>Safety events</h3>
        <span class="grow right muted" style="font-size:11px" id="ov-rank-period1"></span></div>
        <div class="card-pad" id="ov-safety"></div></div>
      <div class="card"><div class="card-head">${icon("route")}<h3>Distance ranking</h3>
        <span class="grow right muted" style="font-size:11px" id="ov-rank-period2"></span></div>
        <div class="card-pad" id="ov-mileage"></div></div>
    </div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("activity")}<h3>Recent activity</h3>
        <a class="grow right" href="#/alerts" style="font-size:12px">View all</a></div>
        <div id="ov-activity"></div></div>
      <div class="card"><div class="card-head">${icon("satellite-dish")}<h3>Vehicles with stale GPS</h3></div>
        <div id="ov-stale"></div></div>
    </div>`;
  refreshIcons(root);

  let alive = true;

  async function loadLive() {
    let devices = live.list();
    if (!devices.length) { try { devices = (await get("/api/devices")).devices; } catch { devices = []; } }
    const openResp = await get("/api/events?acknowledged=false&limit=1").catch(() => ({ open_alarms: 0 }));
    const evResp = await get("/api/events?limit=8").catch(() => ({ events: [] }));
    if (!alive || !qs("#ov-stats")) return;

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

    // Fleet-status donut (mutually exclusive: moving / idle / offline).
    const segs = [
      { value: moving, color: COLORS.moving, label: "Moving" },
      { value: idle, color: COLORS.online, label: "Idle" },
      { value: offline, color: COLORS.offline, label: "Offline" },
    ];
    qs("#ov-donut").innerHTML = donut(segs) +
      `<div class="donut-legend">${segs.map((s) => `
        <div class="dl-row"><span class="dl-dot" style="background:${s.color}"></span>
          <span class="dl-label">${s.label}</span><span class="dl-val">${s.value}</span></div>`).join("")}
        ${stale.length ? `<div class="dl-row"><span class="dl-dot" style="background:${COLORS.stale}"></span>
          <span class="dl-label">Stale GPS</span><span class="dl-val">${stale.length}</span></div>` : ""}</div>`;

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

  async function loadRankings() {
    const safety = qs("#ov-safety"), mileage = qs("#ov-mileage");
    if (!safety) return;
    safety.innerHTML = loadingHtml(""); mileage.innerHTML = loadingHtml("");
    qs("#ov-rank-period1").textContent = period.label;
    qs("#ov-rank-period2").textContent = period.label;
    const from = new Date(Date.now() - period.days * 86400000).toISOString();
    let rows = [];
    try { rows = (await get(`/api/reports/fleet?from=${encodeURIComponent(from)}`)).rows || []; }
    catch { if (safety) { safety.innerHTML = emptyHtml("triangle-alert", "Could not load"); mileage.innerHTML = emptyHtml("triangle-alert", "Could not load"); } return; }
    if (!alive || !qs("#ov-safety")) return;
    rows.forEach((r) => { r.safety_events = (r.overspeed_events || 0) + (r.harsh_events || 0); });
    qs("#ov-safety").innerHTML = rankBars(rows, "safety_events", "", COLORS.offline);
    qs("#ov-mileage").innerHTML = rankBars(rows, "distance_km", "km", COLORS.moving, 1);
    refreshIcons(qs("#ov-safety")); refreshIcons(qs("#ov-mileage"));
  }

  function ageOf(iso) { if (!iso) return null; return (Date.now() - new Date(iso).getTime()) / 1000; }

  qs("#ov-period").addEventListener("click", (e) => {
    const b = e.target.closest("[data-k]"); if (!b) return;
    period = PERIODS.find((p) => p.k === b.dataset.k) || period;
    qs("#ov-period").querySelectorAll(".chip-toggle").forEach((c) => c.classList.toggle("on", c.dataset.k === period.k));
    loadRankings();
  });

  await Promise.all([loadLive(), loadRankings()]);
  const unsub = live.subscribe(() => { if (!render._t) render._t = setTimeout(() => { render._t = null; loadLive(); }, 1500); });
  const timer = setInterval(loadLive, 15000);
  return () => { alive = false; unsub(); clearInterval(timer); if (render._t) { clearTimeout(render._t); render._t = null; } };
}
