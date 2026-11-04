import { live } from "../store.js";
import { baseLayers, COLORS, vehicleIcon } from "../map.js";
import { openMessageDialog } from "../message_dialog.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtAge, deviceStatus, isMoving, statusBadge, simBadge,
} from "../ui.js";

const FILTERS = ["online", "offline", "moving", "idle", "stale", "simulated"];

export async function render(root, ctx) {
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
        <div class="map-overlay map-tools">
          <button class="btn icon" id="btn-collapse" title="Toggle list">${icon("panel-left")}</button>
          <button class="btn icon" id="btn-fit" title="Fit all vehicles">${icon("maximize")}</button>
          <button class="btn icon" id="btn-follow" title="Follow selected">${icon("crosshair")}</button>
        </div>
        <div class="detail-panel card hidden" id="detail"></div>
      </div>
    </div>`;
  refreshIcons(root);

  const map = L.map(qs("#map"), { zoomControl: true, attributionControl: true }).setView([22.5726, 88.3639], 11);
  const layers = baseLayers();
  layers["Dark"].addTo(map);
  L.control.layers(layers, {}, { position: "topright" }).addTo(map);
  const cluster = L.markerClusterGroup({ maxClusterRadius: 48, showCoverageOnHover: false });
  map.addLayer(cluster);

  const state = { markers: new Map(), selected: null, follow: false, search: "", filters: new Set() };

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
      const ic = vehicleIcon(colorOf(d), d.position.heading, isMoving(d));
      if (!m) {
        m = L.marker(ll, { icon: ic });
        m.on("click", () => select(d.id));
        m.bindTooltip(d.vehicle_registration || d.plate || d.reporting_id, { direction: "top" });
        state.markers.set(d.id, m); cluster.addLayer(m);
      } else { m.setLatLng(ll); m.setIcon(ic); }
    }
    for (const [id, m] of state.markers) if (!keep.has(id)) { cluster.removeLayer(m); state.markers.delete(id); }
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
      const st = deviceStatus(d);
      const spd = d.position ? Math.round(d.position.speed) + " km/h" : "no GPS";
      return `<div class="veh-item ${state.selected === d.id ? "sel" : ""}" data-id="${d.id}">
        <span class="dot" style="width:10px;height:10px;border-radius:50%;background:${colorOf(d)}"></span>
        <div class="meta"><div class="title">${esc(d.vehicle_registration || d.plate || d.reporting_id)} ${d.simulated ? simBadge(d) : ""}</div>
          <div class="sub">${spd} · ${fmtAge(d.last_seen_age_s)}</div></div></div>`;
    }).join("") : `<div class="state">${icon("search-x", "i-lg")}<div class="muted">No vehicles match</div></div>`;
    qsa(".veh-item", el).forEach((it) => it.addEventListener("click", () => select(Number(it.dataset.id), true)));
    refreshIcons(el);
  }

  function renderDetail() {
    const d = state.selected && live.get(state.selected);
    const panel = qs("#detail");
    if (!d) { panel.classList.add("hidden"); return; }
    const p = d.position;
    const kv = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
    panel.classList.remove("hidden");
    panel.innerHTML = `<div class="card-pad">
      <div class="row" style="margin-bottom:8px"><b style="font-size:15px">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</b>
        <div class="grow"></div><button class="btn ghost icon sm" data-x>${icon("x")}</button></div>
      <div class="row wrap" style="margin-bottom:10px">${statusBadge(d)} ${simBadge(d)}</div>
      ${kv("Reporting ID", esc(d.reporting_id))}
      ${kv("Serial", esc(d.serial_number || "—"))}
      ${kv("Speed", p ? Math.round(p.speed) + " km/h" : "—")}
      ${kv("Heading", p ? p.heading + "°" : "—")}
      ${kv("Ignition", p ? (p.acc ? "ON" : "OFF") : "—")}
      ${kv("GPS fix", p ? (p.fresh ? "fresh" : "stale/invalid") : "—")}
      ${kv("Last comm", fmtAge(d.last_seen_age_s))}
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
        vehicleName: d.vehicle_registration || d.plate || d.reporting_id,
        reportingId: d.reporting_id,
      });
    });
  }

  function select(id, pan) {
    state.selected = id; renderDetail(); renderList(live.list());
    const d = live.get(id);
    if (pan && d && d.position) map.setView([d.position.latitude, d.position.longitude], Math.max(map.getZoom(), 15));
  }

  function refresh() { const devices = live.list(); renderMarkers(devices); renderList(devices); renderDetail(); }

  // Wire controls
  qs("#veh-search").addEventListener("input", (e) => { state.search = e.target.value; refresh(); });
  qsa(".chip-toggle", root).forEach((c) => c.addEventListener("click", () => {
    const f = c.dataset.f; c.classList.toggle("on");
    if (state.filters.has(f)) state.filters.delete(f); else state.filters.add(f); refresh();
  }));
  qs("#btn-collapse").addEventListener("click", () => { qs("#side").classList.toggle("collapsed"); setTimeout(() => map.invalidateSize(), 60); });
  qs("#btn-fit").addEventListener("click", () => {
    const pts = live.list().filter((d) => d.has_position && d.position).map((d) => [d.position.latitude, d.position.longitude]);
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.2));
  });
  qs("#btn-follow").addEventListener("click", () => { state.follow = !state.follow; qs("#btn-follow").classList.toggle("primary", state.follow); renderDetail(); });

  setTimeout(() => map.invalidateSize(), 80);
  const unsub = live.subscribe(() => refresh());
  live.connect();
  refresh();
  if (live.list().some((d) => d.has_position)) qs("#btn-fit").click();

  return () => { unsub(); map.remove(); };
}
