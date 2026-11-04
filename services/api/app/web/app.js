"use strict";

// ---- API helpers ---------------------------------------------------------
const TOKEN_KEY = "tp_token";
function token() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; } }
function setToken(t) { try { localStorage.setItem(TOKEN_KEY, t); } catch {} }
function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch {} }

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (token()) headers["Authorization"] = "Bearer " + token();
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 401) { clearToken(); showLogin(); throw new Error("unauthorized"); }
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.status === 204 ? null : res.json();
}

// ---- State ---------------------------------------------------------------
const state = { devices: new Map(), markers: new Map(), selected: null, map: null, ws: null, histLayer: null };

const COLORS = { online: "#16a34a", stale: "#d97706", offline: "#dc2626" };
function classify(d) {
  if (!d.online) return "offline";
  if (d.position && d.position.fresh) return "online";
  return "stale";
}
function fmtAge(s) {
  if (s == null) return "never";
  s = Math.round(s);
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}

// ---- Login ---------------------------------------------------------------
function showLogin() {
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
  if (state.ws) { try { state.ws.close(); } catch {} state.ws = null; }
}
function showApp() {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("login-error");
  err.textContent = "";
  try {
    const data = await (await fetch("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    })).json();
    if (!data.access_token) throw new Error(data.detail || "login failed");
    setToken(data.access_token);
    document.getElementById("who").textContent = data.user.email + " (" + data.user.role + ")";
    await start();
  } catch (ex) {
    err.textContent = "Invalid credentials";
  }
});

document.getElementById("logout").addEventListener("click", () => { clearToken(); showLogin(); });

// ---- Map + rendering -----------------------------------------------------
function ensureMap() {
  if (state.map) return;
  state.map = L.map("map").setView([22.5726, 88.3639], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
}

function upsertMarker(d) {
  if (!d.position) return;
  const color = COLORS[classify(d)];
  const ll = [d.position.latitude, d.position.longitude];
  let m = state.markers.get(d.id);
  if (!m) {
    m = L.circleMarker(ll, { radius: 8, color: "#fff", weight: 2, fillColor: color, fillOpacity: 0.9 });
    m.addTo(state.map);
    m.on("click", () => selectDevice(d.id));
    state.markers.set(d.id, m);
  } else {
    m.setLatLng(ll);
    m.setStyle({ fillColor: color });
  }
  m.bindTooltip((d.vehicle_registration || d.reporting_id) + " · " + Math.round(d.position.speed) + " km/h");
}

function renderSummary(summary) {
  const el = document.getElementById("summary");
  const chip = (cls, n, label) => `<div class="chip ${cls}"><b>${n}</b><span>${label}</span></div>`;
  el.innerHTML =
    chip("", summary.total, "All") +
    chip("online", summary.online, "Online") +
    chip("moving", summary.moving, "Moving") +
    chip("offline", summary.offline, "Offline") +
    chip("", summary.no_position, "No GPS");
}

function renderList() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const list = document.getElementById("device-list");
  const items = [...state.devices.values()].filter((d) => {
    if (!q) return true;
    return (d.reporting_id || "").toLowerCase().includes(q) ||
           (d.vehicle_registration || "").toLowerCase().includes(q) ||
           (d.plate || "").toLowerCase().includes(q);
  });
  list.innerHTML = items.map((d) => {
    const cls = classify(d);
    const name = d.vehicle_registration || d.plate || d.reporting_id;
    const spd = d.position ? Math.round(d.position.speed) + " km/h" : "no GPS";
    const sim = d.simulated ? '<span class="badge-sim">SIM</span>' : "";
    return `<div class="device ${state.selected === d.id ? "selected" : ""}" data-id="${d.id}">
      <div class="dot ${cls}"></div>
      <div class="meta">
        <div class="title">${name}${sim}</div>
        <div class="sub">${spd} · ${fmtAge(d.last_seen_age_s)}</div>
      </div></div>`;
  }).join("") || '<div class="muted" style="padding:14px">No devices.</div>';
  list.querySelectorAll(".device").forEach((el) =>
    el.addEventListener("click", () => selectDevice(Number(el.dataset.id))));
}

function selectDevice(id) {
  state.selected = id;
  const d = state.devices.get(id);
  if (d && d.position) state.map.setView([d.position.latitude, d.position.longitude], 15);
  renderList();
  renderInfo();
}

function renderInfo() {
  const panel = document.getElementById("info");
  const d = state.devices.get(state.selected);
  if (!d) { panel.classList.add("hidden"); return; }
  const cls = classify(d);
  const p = d.position;
  const row = (a, b) => `<div class="info-row"><span>${a}</span><span>${b}</span></div>`;
  const rowId = (id, a, b) => `<div class="info-row"><span>${a}</span><span id="${id}">${b}</span></div>`;
  panel.innerHTML = `
    <h3>${d.vehicle_registration || d.plate || d.reporting_id}
      <span id="inf-pill" class="status-pill ${cls}">${cls}</span></h3>
    ${row("Reporting ID", d.reporting_id)}
    ${row("Serial", d.serial_number || "—")}
    ${row("Model", d.model || "—")}
    ${rowId("inf-ign", "Ignition", p ? (p.acc ? "ON" : "OFF") : "—")}
    ${rowId("inf-speed", "Speed", p ? Math.round(p.speed) + " km/h" : "—")}
    ${rowId("inf-hdg", "Heading", p ? p.heading + "°" : "—")}
    ${rowId("inf-fix", "GPS fix", p ? (p.fresh ? "fresh" : "stale/invalid") : "—")}
    ${rowId("inf-last", "Last comm", fmtAge(d.last_seen_age_s))}
    ${d.simulated ? row("Source", "SIMULATED") : ""}
    <div class="info-actions">
      <button id="hist-btn">History</button>
      <button id="trips-btn">Trips</button>
      <button id="cams-btn">Cameras</button>
      <button id="close-info">Close</button>
    </div>
    <div id="trip-list"></div>
    <div id="cam-list"></div>`;
  panel.classList.remove("hidden");
  document.getElementById("close-info").onclick = () => { state.selected = null; clearHistory(); stopStreamPoll(); panel.classList.add("hidden"); renderList(); };
  document.getElementById("hist-btn").onclick = () => loadHistory(d.id);
  document.getElementById("trips-btn").onclick = () => loadTrips(d.id);
  document.getElementById("cams-btn").onclick = () => loadCameras(d.id, d.reporting_id);
}

// ---- Video (JT/T 1078) ---------------------------------------------------
async function loadCameras(id, reportingId) {
  const box = document.getElementById("cam-list");
  if (!box) return;
  const data = await api(`/api/devices/${id}/cameras`);
  box.innerHTML = '<div class="muted" style="margin:6px 0">Camera channels:</div>' +
    data.channels.map((c) =>
      `<button class="cam-btn" data-ch="${c.channel_no}">CH${c.channel_no} ▶ Live</button>`).join("") +
    '<div id="video-panel"></div>';
  box.querySelectorAll(".cam-btn").forEach((el) =>
    el.addEventListener("click", () => requestLive(id, reportingId, Number(el.dataset.ch))));
}

async function requestLive(id, reportingId, channel) {
  const vp = document.getElementById("video-panel");
  vp.innerHTML = '<div class="muted" style="padding:6px 0">Requesting channel ' + channel + '…</div>';
  try {
    const res = await api(`/api/devices/${id}/video/live`, {
      method: "POST", body: JSON.stringify({ channel }),
    });
    vp.innerHTML = `
      <div class="video-box">
        <div class="video-ph">No live picture — JT/T 1078 relay pending hardware</div>
        <div class="video-note">${res.note}</div>
        <div id="stream-stat" class="muted">waiting for stream…</div>
      </div>`;
    startStreamPoll(reportingId, channel);
  } catch (e) {
    const msg = (e && e.message) ? e.message : "request failed";
    vp.innerHTML = `<div class="video-box"><div class="error">Could not start stream: ${msg}</div></div>`;
  }
}

function stopStreamPoll() { if (state.streamTimer) { clearInterval(state.streamTimer); state.streamTimer = null; } }
function startStreamPoll(reportingId, channel) {
  stopStreamPoll();
  const tick = async () => {
    try {
      const data = await api("/api/video/streams");
      const s = (data.streams || []).find((x) => String(x.sim) === String(reportingId) && Number(x.channel) === channel);
      const el = document.getElementById("stream-stat");
      if (!el) { stopStreamPoll(); return; }
      el.innerHTML = s
        ? `<b style="color:var(--green)">● receiving</b> · ${s.packets} pkts · ${s.video_frames} video frames · ${s.key_frames} keyframes · ${Math.round((s.bytes||0)/1024)} KB`
        : "no stream received yet (device must support/accept JT/T 1078)";
    } catch { stopStreamPoll(); }
  };
  tick();
  state.streamTimer = setInterval(tick, 2000);
}

async function loadTrips(id) {
  const data = await api(`/api/devices/${id}/trips?limit=50`);
  const box = document.getElementById("trip-list");
  if (!box) return;
  if (data.count === 0) { box.innerHTML = '<div class="muted" style="padding:6px 0">No trips yet.</div>'; return; }
  box.innerHTML = data.trips.map((t) => {
    const km = t.distance_km.toFixed(1);
    const when = t.started_at ? new Date(t.started_at).toLocaleString() : "";
    return `<div class="trip-item" data-tid="${t.id}">${when} · ${km} km · max ${Math.round(t.max_speed)} km/h</div>`;
  }).join("");
  box.querySelectorAll(".trip-item").forEach((el) =>
    el.addEventListener("click", () => drawTrip(Number(el.dataset.tid))));
}

async function drawTrip(tid) {
  clearHistory();
  const t = await api(`/api/trips/${tid}`);
  if (!t.path || t.path.length < 2) { alert("Trip has no path."); return; }
  state.histLayer = L.polyline(t.path, { color: "#7c3aed", weight: 4, opacity: 0.85 }).addTo(state.map);
  state.map.fitBounds(state.histLayer.getBounds(), { padding: [40, 40] });
}

// Update only the live values in the open info panel so buttons stay interactive.
function updateInfoLive() {
  const d = state.devices.get(state.selected);
  if (!d || !d.position) return;
  const panel = document.getElementById("info");
  if (panel.classList.contains("hidden")) return;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const p = d.position, cls = classify(d);
  set("inf-ign", p.acc ? "ON" : "OFF");
  set("inf-speed", Math.round(p.speed) + " km/h");
  set("inf-hdg", p.heading + "°");
  set("inf-fix", p.fresh ? "fresh" : "stale/invalid");
  set("inf-last", fmtAge(d.last_seen_age_s));
  const pill = document.getElementById("inf-pill");
  if (pill) { pill.className = "status-pill " + cls; pill.textContent = cls; }
}

// ---- History / trip playback --------------------------------------------
function clearHistory() { if (state.histLayer) { state.map.removeLayer(state.histLayer); state.histLayer = null; } }
async function loadHistory(id) {
  clearHistory();
  const data = await api(`/api/devices/${id}/history?limit=2000`);
  const pts = data.positions.filter((p) => p.valid).map((p) => [p.latitude, p.longitude]);
  if (pts.length === 0) { alert("No history yet for this device."); return; }
  state.histLayer = L.polyline(pts, { color: "#2563eb", weight: 3, opacity: 0.8 }).addTo(state.map);
  state.map.fitBounds(state.histLayer.getBounds(), { padding: [40, 40] });
}

// ---- Live WebSocket ------------------------------------------------------
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/ws/live?token=${encodeURIComponent(token())}`);
  state.ws = ws;
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") {
      msg.devices.forEach((d) => { state.devices.set(d.id, d); upsertMarker(d); });
      renderList(); renderInfo();
    } else if (msg.type === "update") {
      msg.positions.forEach((u) => {
        const d = state.devices.get(u.device_id);
        if (!d) return;
        d.position = Object.assign(d.position || {}, {
          latitude: u.latitude, longitude: u.longitude, speed: u.speed,
          heading: u.heading, acc: u.acc, valid: u.valid, fresh: true,
        });
        d.last_seen_age_s = 0; d.online = true; d.has_position = true;
        upsertMarker(d);
      });
      renderList();
      if (state.selected) updateInfoLive();
    }
  };
  ws.onclose = () => { if (token()) setTimeout(connectWS, 3000); };
}

// ---- Geofences -----------------------------------------------------------
async function loadGeofences() {
  if (!state.geoLayer) { state.geoLayer = L.layerGroup().addTo(state.map); }
  state.geoLayer.clearLayers();
  const data = await api("/api/geofences");
  data.geofences.forEach((g) => {
    const poly = L.polygon(g.ring, { color: "#0ea5e9", weight: 2, fillOpacity: 0.08, dashArray: "6 4" });
    poly.bindTooltip("Geofence: " + g.name);
    poly.addTo(state.geoLayer);
  });
}

// Simple click-to-draw polygon geofence (no external plugin).
function startDraw() {
  state.draw = { pts: [], markers: [], line: null };
  document.getElementById("draw-bar").classList.remove("hidden");
  state.map.on("click", onDrawClick);
}
function onDrawClick(e) {
  const d = state.draw;
  d.pts.push([e.latlng.lat, e.latlng.lng]);
  d.markers.push(L.circleMarker(e.latlng, { radius: 4, color: "#0ea5e9" }).addTo(state.map));
  if (d.line) state.map.removeLayer(d.line);
  d.line = L.polyline(d.pts, { color: "#0ea5e9", dashArray: "4 4" }).addTo(state.map);
  document.getElementById("draw-hint").textContent = `${d.pts.length} point(s) added (min 3)`;
}
function cleanupDraw() {
  const d = state.draw;
  if (!d) return;
  d.markers.forEach((m) => state.map.removeLayer(m));
  if (d.line) state.map.removeLayer(d.line);
  state.map.off("click", onDrawClick);
  state.draw = null;
  document.getElementById("draw-bar").classList.add("hidden");
}
async function finishDraw() {
  const d = state.draw;
  if (!d || d.pts.length < 3) { alert("Add at least 3 points."); return; }
  const name = prompt("Geofence name:", "New Zone");
  if (name) {
    try {
      await api("/api/geofences", { method: "POST", body: JSON.stringify({ name, ring: d.pts }) });
      await loadGeofences();
    } catch (e) { alert("Could not save geofence: " + e.message); }
  }
  cleanupDraw();
}

// ---- Alerts feed ---------------------------------------------------------
async function pollAlerts() {
  try {
    const data = await api("/api/events?limit=60");
    const alerts = data.events.filter((e) => e.severity !== "info");
    const badge = document.getElementById("alerts-badge");
    badge.textContent = alerts.length;
    badge.classList.toggle("zero", alerts.length === 0);
    const list = document.getElementById("alerts-list");
    list.innerHTML = data.events.map((e) => {
      const when = e.at ? new Date(e.at).toLocaleTimeString() : "";
      const who = e.reporting_id || ("#" + e.device_id);
      const label = e.type.replace(/_/g, " ") + (e.detail ? " · " + e.detail : "");
      return `<div class="alert"><span class="sev ${e.severity}"></span>
        <div><b>${who}</b><br>${label}</div><span class="etime">${when}</span></div>`;
    }).join("") || '<div class="muted" style="padding:10px">No events yet.</div>';
  } catch {}
}

// ---- Startup -------------------------------------------------------------
document.getElementById("search").addEventListener("input", renderList);
document.getElementById("alerts-btn").addEventListener("click", () =>
  document.getElementById("alerts").classList.toggle("hidden"));
document.getElementById("alerts-close").addEventListener("click", () =>
  document.getElementById("alerts").classList.add("hidden"));
document.getElementById("draw-btn").addEventListener("click", startDraw);
document.getElementById("draw-cancel").addEventListener("click", cleanupDraw);
document.getElementById("draw-finish").addEventListener("click", finishDraw);

async function start() {
  showApp();
  ensureMap();
  setTimeout(() => state.map.invalidateSize(), 100);
  const data = await api("/api/devices");
  renderSummary(data.summary);
  data.devices.forEach((d) => { state.devices.set(d.id, d); upsertMarker(d); });
  renderList();
  await loadGeofences();
  await pollAlerts();
  // Refresh summary periodically from REST (counts), live positions via WS.
  setInterval(async () => {
    try { renderSummary((await api("/api/devices")).summary); } catch {}
  }, 10000);
  setInterval(pollAlerts, 4000);
  connectWS();
  const me = await api("/api/auth/me");
  document.getElementById("who").textContent = me.email + " (" + me.role + ")";
}

if (token()) { start().catch(() => showLogin()); } else { showLogin(); }
