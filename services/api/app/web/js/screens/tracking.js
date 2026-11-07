import { live } from "../store.js";
import { baseLayers, COLORS, vehicleIcon } from "../map.js?v=20261105";
import { openMessageDialog } from "../message_dialog.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtAge, fmtDateTime, num, deviceStatus, isMoving, statusBadge, simBadge,
} from "../ui.js";

const FILTERS = ["online", "offline", "moving", "idle", "stale", "simulated"];

// Live fleet-status summary shown over the map; each cell is a quick filter.
const STATS = [
  { f: "",        cls: "pri",  label: "Total" },
  { f: "online",  cls: "ok",   label: "Online" },
  { f: "moving",  cls: "pri",  label: "Moving" },
  { f: "idle",    cls: "",     label: "Idle" },
  { f: "offline", cls: "bad",  label: "Offline" },
  { f: "stale",   cls: "warn", label: "Stale" },
];

// Map display preferences, persisted per browser (per-viewer convenience only).
const SETTINGS_KEY = "ft.map.settings";
const DEFAULTS = { labels: false, cluster: true, size: "m", translucent: false };
const SIZE_PX = { s: 12, m: 16, l: 22 };

function loadSettings() {
  try { return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}")) }; }
  catch { return { ...DEFAULTS }; }
}

export async function render(root, ctx) {
  const settings = loadSettings();
  const saveSettings = () => { try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch {} };

  root.innerHTML = `
    <div class="map-layout">
      <div class="map-side" id="side">
        <div style="padding:12px;border-bottom:1px solid var(--border-soft)">
          <div class="input-icon">${icon("search")}<input class="input" id="veh-search" placeholder="Search plate, device ID, name"></div>
          <div class="filters" style="margin-top:10px">
            ${FILTERS.map((f) => `<button class="chip-toggle" data-f="${f}">${f}</button>`).join("")}
          </div>
        </div>
        <div class="veh-list" id="veh-list"></div>
      </div>
      <div class="map-wrap">
        <div class="mapel" id="map"></div>
        <div class="map-overlay status-top"><div class="status-strip" id="status-strip"></div></div>
        <div class="map-overlay map-tools">
          <button class="btn icon" id="btn-collapse" title="Toggle list">${icon("panel-left")}</button>
          <button class="btn icon" id="btn-fit" title="Fit all vehicles">${icon("maximize")}</button>
          <button class="btn icon" id="btn-follow" title="Follow selected">${icon("crosshair")}</button>
          <button class="btn icon" id="btn-settings" title="Map settings">${icon("settings")}</button>
        </div>
        <div class="map-overlay map-settings card hidden" id="map-settings"></div>
        <div class="detail-panel card hidden" id="detail"></div>
      </div>
    </div>`;
  refreshIcons(root);

  const map = L.map(qs("#map"), { zoomControl: true, attributionControl: true }).setView([22.5726, 88.3639], 11);
  const layers = baseLayers();
  layers["Satellite"].addTo(map);
  L.control.layers(layers, {}, { position: "topright" }).addTo(map);

  const clusterGroup = L.markerClusterGroup({ maxClusterRadius: 48, showCoverageOnHover: false });
  const plainGroup = L.layerGroup();
  let markerLayer = settings.cluster ? clusterGroup : plainGroup;
  map.addLayer(markerLayer);

  const state = { markers: new Map(), selected: null, follow: false, search: "", filters: new Set() };

  const labelOf = (d) => d.vehicle_registration || d.plate || d.reporting_id;
  const tooltipOpts = () => settings.labels
    ? { permanent: true, direction: "right", offset: [9, 0], className: "veh-label" }
    : { direction: "top", className: "veh-tip" };
  const makeIcon = (d) => vehicleIcon(colorOf(d), d.position.heading, isMoving(d),
    { size: SIZE_PX[settings.size] || 16, opacity: settings.translucent ? 0.62 : 1 });

  function visible(d) {
    const st = deviceStatus(d);
    if (state.search) {
      const q = state.search.toLowerCase();
      const hay = `${d.reporting_id} ${d.vehicle_registration || ""} ${d.plate || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (state.filters.size) {
      const tags = new Set([st]);
      if (isMoving(d)) tags.add("moving");
      if (st === "online" && !isMoving(d)) tags.add("idle");
      if (d.simulated) tags.add("simulated");
      for (const f of state.filters) if (!tags.has(f)) return false;
    }
    return true;
  }

  function colorOf(d) {
    const st = deviceStatus(d);
    return st === "online" ? (isMoving(d) ? COLORS.moving : COLORS.online) : COLORS[st];
  }

  function renderMarkers(devices) {
    const keep = new Set();
    for (const d of devices) {
      if (!d.has_position || !d.position || !visible(d)) continue;
      keep.add(d.id);
      const ll = [d.position.latitude, d.position.longitude];
      let m = state.markers.get(d.id);
      if (!m) {
        m = L.marker(ll, { icon: makeIcon(d) });
        m.on("click", () => select(d.id));
        m.bindTooltip(labelOf(d), tooltipOpts());
        state.markers.set(d.id, m); markerLayer.addLayer(m);
      } else { m.setLatLng(ll); m.setIcon(makeIcon(d)); }
    }
    for (const [id, m] of state.markers) if (!keep.has(id)) { markerLayer.removeLayer(m); state.markers.delete(id); }
    if (state.follow && state.selected) {
      const d = live.get(state.selected);
      if (d && d.position) map.panTo([d.position.latitude, d.position.longitude], { animate: true });
    }
  }

  function renderList(devices) {
    const list = devices.filter(visible).sort((a, b) =>
      (a.vehicle_registration || a.reporting_id).localeCompare(b.vehicle_registration || b.reporting_id));
    const el = qs("#veh-list");
    el.innerHTML = list.length ? list.map((d) => {
      const spd = d.position ? Math.round(d.position.speed) + " km/h" : "no GPS";
      return `<div class="veh-item ${state.selected === d.id ? "sel" : ""}" data-id="${d.id}">
        <span class="dot" style="width:10px;height:10px;border-radius:50%;background:${colorOf(d)}"></span>
        <div class="meta"><div class="title">${esc(labelOf(d))} ${d.simulated ? simBadge(d) : ""}</div>
          <div class="sub">${spd} · ${fmtAge(d.last_seen_age_s)}</div></div></div>`;
    }).join("") : `<div class="state">${icon("search-x", "i-lg")}<div class="muted">No vehicles match</div></div>`;
    qsa(".veh-item", el).forEach((it) => it.addEventListener("click", () => select(Number(it.dataset.id), true)));
    refreshIcons(el);
  }

  function renderDetail() {
    const d = state.selected && live.get(state.selected);
    const panel = qs("#detail");
    // The settings sheet and the detail panel share the map overlay space; show
    // only one at a time so they never collide.
    const settingsOpen = !qs("#map-settings").classList.contains("hidden");
    if (!d || settingsOpen) { panel.classList.add("hidden"); return; }
    const p = d.position;
    const kv = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
    const ign = p ? (p.acc ? `<span class="badge online"><span class="dot"></span>ON</span>` : `<span class="badge idle">OFF</span>`) : "—";
    const gps = p ? (p.fresh ? `<span class="badge online"><span class="dot"></span>Fresh</span>`
      : `<span class="badge stale"><span class="dot"></span>Stale</span>`) : "—";
    panel.classList.remove("hidden");
    panel.innerHTML = `<div class="card-pad">
      <div class="row" style="margin-bottom:8px"><b style="font-size:15px">${esc(labelOf(d))}</b>
        <div class="grow"></div><button class="btn ghost icon sm" data-x>${icon("x")}</button></div>
      <div class="row wrap" style="margin-bottom:12px">${statusBadge(d)} ${simBadge(d)}</div>
      <div class="detail-metrics">
        <div class="dm"><div class="dm-l">Speed</div><div class="dm-v">${p ? Math.round(p.speed) : "—"}<span class="dm-u">km/h</span></div></div>
        <div class="dm"><div class="dm-l">Heading</div><div class="dm-v">${p ? p.heading : "—"}<span class="dm-u">°</span></div></div>
        <div class="dm"><div class="dm-l">Odometer</div><div class="dm-v">${d.odometer_km != null ? num(d.odometer_km, 1) : "—"}<span class="dm-u">km</span></div></div>
      </div>
      <div class="detail-kv">
        ${kv("Ignition", ign)}
        ${kv("GPS fix", gps)}
        ${kv("Altitude", p && p.altitude != null ? num(p.altitude) + " m" : "—")}
        ${kv("Last comm", fmtAge(d.last_seen_age_s))}
        ${kv("Device time", p ? fmtDateTime(p.device_time) : "—")}
        ${kv("Position", p ? `${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}` : "—")}
        ${kv("Reporting ID", esc(d.reporting_id))}
        ${kv("Model", esc(d.model || "—"))}
      </div>
      <div class="row" style="margin-top:12px;gap:8px">
        <a class="btn sm" href="#/vehicle/${d.id}">${icon("info")} Details</a>
        <button class="btn sm" data-msg>${icon("send")} Message</button>
        <button class="btn sm ${state.follow ? "primary" : ""}" data-follow>${icon("crosshair")} Follow</button>
      </div></div>`;
    refreshIcons(panel);
    qs("[data-x]", panel).addEventListener("click", () => { state.selected = null; renderDetail(); renderList(live.list()); });
    qs("[data-follow]", panel).addEventListener("click", () => { state.follow = !state.follow; renderDetail(); });
    qs("[data-msg]", panel)?.addEventListener("click", () => {
      openMessageDialog({
        deviceId: d.id,
        vehicleName: labelOf(d),
        reportingId: d.reporting_id,
      });
    });
  }

  function countStatuses(devices) {
    const c = { "": devices.length, online: 0, moving: 0, idle: 0, offline: 0, stale: 0 };
    for (const d of devices) {
      const st = deviceStatus(d);
      if (st === "online") { c.online++; if (isMoving(d)) c.moving++; else c.idle++; }
      else if (st === "offline") c.offline++;
      if (d.has_position && d.position && !d.position.fresh) c.stale++;
    }
    return c;
  }

  function syncChips() {
    qsa(".chip-toggle", root).forEach((c) => c.classList.toggle("on", state.filters.has(c.dataset.f)));
  }

  function renderStrip(devices) {
    const el = qs("#status-strip");
    if (!el) return;
    const c = countStatuses(devices);
    el.innerHTML = STATS.map((s) => `<div class="sc ${s.cls} ${s.f && state.filters.has(s.f) ? "on" : ""}" data-f="${s.f}">
      <span class="n">${c[s.f]}</span><span class="l">${s.label}</span></div>`).join("");
    qsa(".sc", el).forEach((sc) => sc.addEventListener("click", () => {
      const f = sc.dataset.f;
      if (!f) state.filters.clear();
      else if (state.filters.has(f)) state.filters.delete(f);
      else state.filters.add(f);
      syncChips(); refresh();
    }));
  }

  function refresh() {
    const devices = live.list();
    renderStrip(devices); renderMarkers(devices); renderList(devices); renderDetail();
  }

  // ---- Map settings sheet ------------------------------------------------
  function swapClusterLayer() {
    const want = settings.cluster ? clusterGroup : plainGroup;
    if (markerLayer === want) return;
    for (const m of state.markers.values()) markerLayer.removeLayer(m);
    map.removeLayer(markerLayer);
    markerLayer = want;
    map.addLayer(markerLayer);
    for (const m of state.markers.values()) markerLayer.addLayer(m);
  }

  function relabelAll() {
    for (const [id, m] of state.markers) {
      const d = live.get(id); if (!d) continue;
      m.unbindTooltip(); m.bindTooltip(labelOf(d), tooltipOpts());
    }
  }

  function renderSettingsPanel() {
    const sw = (key, label) => `<div class="set-row"><span>${label}</span>
      <button class="switch ${settings[key] ? "on" : ""}" data-toggle="${key}" role="switch" aria-checked="${!!settings[key]}"></button></div>`;
    const sizeBtn = (v, label) => `<button class="seg ${settings.size === v ? "on" : ""}" data-size="${v}">${label}</button>`;
    const panel = qs("#map-settings");
    panel.innerHTML = `<div class="card-pad">
      <div class="row" style="margin-bottom:10px"><b style="font-size:13px">Map settings</b>
        <div class="grow"></div><button class="btn ghost icon sm" data-close>${icon("x")}</button></div>
      ${sw("labels", "Show vehicle labels")}
      ${sw("cluster", "Cluster markers")}
      ${sw("translucent", "Translucent markers")}
      <div class="set-row"><span>Marker size</span>
        <div class="seg-group">${sizeBtn("s", "S")}${sizeBtn("m", "M")}${sizeBtn("l", "L")}</div></div>
      <button class="btn sm" data-reset style="width:100%;margin-top:6px">${icon("maximize")} Reset view</button>
    </div>`;
    refreshIcons(panel);
    qs("[data-close]", panel).addEventListener("click", () => { panel.classList.add("hidden"); renderDetail(); });
    qsa("[data-toggle]", panel).forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.toggle; settings[k] = !settings[k]; saveSettings();
      if (k === "cluster") swapClusterLayer();
      if (k === "labels") relabelAll();
      refresh(); renderSettingsPanel();
    }));
    qsa("[data-size]", panel).forEach((b) => b.addEventListener("click", () => {
      settings.size = b.dataset.size; saveSettings(); refresh(); renderSettingsPanel();
    }));
    qs("[data-reset]", panel).addEventListener("click", () => { fitAll(); panel.classList.add("hidden"); renderDetail(); });
  }

  function fitAll() {
    const pts = live.list().filter((d) => d.has_position && d.position).map((d) => [d.position.latitude, d.position.longitude]);
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.2));
  }

  function select(id, pan) {
    qs("#map-settings").classList.add("hidden");   // selecting a vehicle closes settings
    state.selected = id; renderDetail(); renderList(live.list());
    const d = live.get(id);
    if (pan && d && d.position) map.setView([d.position.latitude, d.position.longitude], Math.max(map.getZoom(), 15));
  }

  // Wire controls
  qs("#veh-search").addEventListener("input", (e) => { state.search = e.target.value; refresh(); });
  qsa(".chip-toggle", root).forEach((c) => c.addEventListener("click", () => {
    const f = c.dataset.f;
    if (state.filters.has(f)) state.filters.delete(f); else state.filters.add(f);
    syncChips(); refresh();
  }));
  qs("#btn-collapse").addEventListener("click", () => { qs("#side").classList.toggle("collapsed"); setTimeout(() => map.invalidateSize(), 60); });
  qs("#btn-fit").addEventListener("click", fitAll);
  qs("#btn-follow").addEventListener("click", () => { state.follow = !state.follow; qs("#btn-follow").classList.toggle("primary", state.follow); renderDetail(); });
  qs("#btn-settings").addEventListener("click", () => {
    const panel = qs("#map-settings");
    panel.classList.toggle("hidden");
    if (!panel.classList.contains("hidden")) renderSettingsPanel();
    renderDetail();   // hide the detail panel while settings is open, restore on close
  });

  setTimeout(() => map.invalidateSize(), 80);
  const unsub = live.subscribe(() => refresh());
  live.connect();
  refresh();
  if (live.list().some((d) => d.has_position)) fitAll();

  return () => { unsub(); map.remove(); };
}
