import { get } from "../api.js";
import { baseLayers } from "../map.js";
import { icon, refreshIcons, qs, qsa, esc, fmtDateTime, num, emptyHtml, loadingHtml } from "../ui.js";

export async function render(root, ctx) {
  root.innerHTML = `
    <div class="page-head"><h2>Trips &amp; Playback</h2></div>
    <div class="toolbar">
      <select class="input" id="t-device" style="max-width:260px"><option value="">Select a vehicle…</option></select>
      <input class="input" type="date" id="t-from" style="max-width:170px">
      <input class="input" type="date" id="t-to" style="max-width:170px">
      <button class="btn" id="t-apply">${icon("filter")} Apply</button>
    </div>
    <div class="grid-2">
      <div class="card"><div class="card-head">${icon("list")}<h3>Trips</h3></div><div id="t-list" style="max-height:440px;overflow:auto"></div></div>
      <div class="card"><div class="card-head">${icon("map")}<h3>Route playback</h3></div>
        <div style="position:relative;height:440px"><div class="mapel" id="t-map"></div></div></div>
    </div>`;
  refreshIcons(root);

  const map = L.map(qs("#t-map"), { zoomControl: true }).setView([22.57, 88.36], 5);
  baseLayers()["Dark"].addTo(map);
  setTimeout(() => map.invalidateSize(), 80);
  let layer = null;

  const devices = (await get("/api/devices")).devices;
  qs("#t-device").innerHTML += devices.map((d) =>
    `<option value="${d.id}">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</option>`).join("");

  async function loadTrips() {
    const id = qs("#t-device").value;
    const el = qs("#t-list");
    if (!id) { el.innerHTML = emptyHtml("route", "Select a vehicle", "Choose a vehicle to see its trips."); refreshIcons(el); return; }
    el.innerHTML = loadingHtml();
    let trips = (await get(`/api/devices/${id}/trips?limit=200`)).trips;
    const from = qs("#t-from").value, to = qs("#t-to").value;
    if (from) trips = trips.filter((t) => t.started_at && t.started_at >= from);
    if (to) trips = trips.filter((t) => t.started_at && t.started_at <= to + "T23:59:59");
    if (!trips.length) { el.innerHTML = emptyHtml("route", "No trips", "No stored trips for this vehicle in the selected range."); refreshIcons(el); return; }
    el.innerHTML = trips.map((t) => `<div class="veh-item" data-tid="${t.id}">
      ${icon("route", "i-sm")}<div class="meta"><div class="title">${fmtDateTime(t.started_at)}</div>
      <div class="sub">${num(t.distance_km, 1)} km · ${t.point_count} points · max ${Math.round(t.max_speed)} km/h</div></div>
      ${icon("play", "i-sm")}</div>`).join("");
    refreshIcons(el);
    qsa(".veh-item", el).forEach((it) => it.addEventListener("click", () => { qsa(".veh-item", el).forEach((x) => x.classList.remove("sel")); it.classList.add("sel"); playTrip(Number(it.dataset.tid)); }));
  }

  async function playTrip(tid) {
    const t = await get(`/api/trips/${tid}`);
    if (layer) { map.removeLayer(layer); layer = null; }
    if (!t.path || t.path.length < 2) return;
    layer = L.layerGroup().addTo(map);
    const line = L.polyline(t.path, { color: "#3282F6", weight: 4 }).addTo(layer);
    L.circleMarker(t.path[0], { radius: 6, color: "#fff", fillColor: "#20C997", fillOpacity: 1 }).bindTooltip("Start").addTo(layer);
    L.circleMarker(t.path[t.path.length - 1], { radius: 6, color: "#fff", fillColor: "#F06464", fillOpacity: 1 }).bindTooltip("End").addTo(layer);
    map.fitBounds(line.getBounds().pad(0.2));
  }

  qs("#t-apply").addEventListener("click", loadTrips);
  qs("#t-device").addEventListener("change", loadTrips);
  qs("#t-list").innerHTML = emptyHtml("route", "Select a vehicle", "Choose a vehicle to see its trips.");
  refreshIcons(qs("#t-list"));
  return () => map.remove();
}
