import { get } from "../api.js";
import { baseLayers } from "../map.js?v=20261105";
import { openMessageDialog } from "../message_dialog.js";
import {
  icon, refreshIcons, qs, esc, fmtAge, fmtDateTime, statusBadge, simBadge, sevBadge, num, emptyHtml,
} from "../ui.js";

export async function render(root, ctx) {
  const id = Number(ctx.params.id);
  const d = await get(`/api/devices/${id}`);
  const name = d.vehicle_registration || d.plate || d.reporting_id;
  const p = d.position;

  root.innerHTML = `
    <div class="page-head">
      <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
        <a class="btn ghost icon" href="#/devices">${icon("arrow-left")}</a>
        <h2>${esc(name)}</h2> ${statusBadge(d)} ${simBadge(d)}
      </div>
      <div class="veh-actions">
        <button class="btn" id="v-btn-msg">${icon("send")} Message</button>
        <a class="btn" href="#/tracking">${icon("map-pin")} Track</a>
        <a class="btn" href="#/video">${icon("video")} Cameras</a>
      </div>
    </div>
    <div class="grid-2">
      <div class="card"><div class="card-head">${icon("truck")}<h3>Identity &amp; assignment</h3></div>
        <div class="card-pad" id="v-identity"></div></div>
      <div class="card"><div class="card-head">${icon("gauge")}<h3>Latest telemetry</h3></div>
        <div class="card-pad" id="v-telemetry"></div></div>
    </div>
    <div class="card section-gap"><div class="card-head">${icon("map")}<h3>Location</h3></div>
      <div style="position:relative;height:280px"><div class="mapel" id="v-map"></div></div></div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("route")}<h3>Recent trips</h3><a class="grow right" href="#/trips" style="font-size:12px">All trips</a></div><div id="v-trips"></div></div>
      <div class="card"><div class="card-head">${icon("bell")}<h3>Recent events</h3></div><div id="v-events"></div></div>
    </div>
    <div class="card section-gap"><div class="card-head">${icon("cctv")}<h3>Camera channels</h3></div><div class="card-pad" id="v-cams"></div></div>`;
  refreshIcons(root);

  qs("#v-btn-msg")?.addEventListener("click", () => {
    openMessageDialog({
      deviceId: id,
      vehicleName: name,
      reportingId: d.reporting_id,
    });
  });

  let driverName = "—";
  if (d.vehicle_id) {
    try {
      const vdata = await get("/api/vehicles");
      const veh = (vdata.vehicles || []).find((x) => x.id === d.vehicle_id);
      if (veh) {
        if (veh.driver_name) driverName = veh.driver_name;
        if (veh.driver_id) {
          const drData = await get("/api/drivers");
          const dr = (drData.drivers || []).find((x) => x.id === veh.driver_id);
          if (dr) driverName = dr.name;
        }
      }
    } catch {}
  }
  if (!qs("#v-identity")) return;

  const kv = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  qs("#v-identity").innerHTML =
    kv("Registration", esc(d.vehicle_registration || d.plate || "—")) +
    kv("Assigned driver", esc(driverName)) +
    kv("Model", esc(d.model || "—")) + kv("Manufacturer", esc(d.manufacturer || "—")) +
    kv("Reporting ID", `<span class="mono">${esc(d.reporting_id)}</span>`) +
    kv("SIM / Phone", d.sim_number ? `<span class="mono">${esc(d.sim_number)}</span>` : "—") +
    kv("Hardware serial", `<span class="mono">${esc(d.serial_number || "—")}</span>`) +
    kv("Protocol", esc(d.protocol || "—")) + kv("Active", d.active ? "yes" : "no");
  qs("#v-telemetry").innerHTML =
    kv("Communication", `${statusBadge(d)}`) +
    kv("Last comm", fmtAge(d.last_seen_age_s)) +
    kv("GPS fix", p ? (p.fresh ? "fresh" : "stale/invalid") : "—") +
    kv("Speed", p ? Math.round(p.speed) + " km/h" : "—") +
    kv("Heading", p ? p.heading + "°" : "—") + kv("Ignition", p ? (p.acc ? "ON" : "OFF") : "—") +
    kv("Device time", p ? fmtDateTime(p.device_time) : "—") + kv("Server time", p ? fmtDateTime(p.server_time) : "—");

  // Map with last position + recent track
  const map = L.map(qs("#v-map"), { zoomControl: true }).setView(p ? [p.latitude, p.longitude] : [22.57, 88.36], p ? 14 : 4);
  const layers = baseLayers();
  layers["Satellite"].addTo(map);
  L.control.layers(layers, {}, { position: "topright" }).addTo(map);
  setTimeout(() => map.invalidateSize(), 80);
  try {
    const hist = await get(`/api/devices/${id}/history?limit=300`);
    const pts = hist.positions.filter((x) => x.valid).map((x) => [x.latitude, x.longitude]);
    if (pts.length > 1) { const line = L.polyline(pts, { color: "#3282F6", weight: 3 }).addTo(map); map.fitBounds(line.getBounds().pad(0.3)); }
    if (p) L.marker([p.latitude, p.longitude]).addTo(map);
  } catch {}

  // Trips
  try {
    const t = await get(`/api/devices/${id}/trips?limit=8`);
    qs("#v-trips").innerHTML = t.count ? t.trips.map((tr) => `
      <div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">
        ${icon("route", "i-sm")}<div class="grow"><div style="font-weight:600">${fmtDateTime(tr.started_at)}</div>
        <div class="muted" style="font-size:12px">${num(tr.distance_km, 1)} km · max ${Math.round(tr.max_speed)} km/h</div></div></div>`).join("")
      : emptyHtml("route", "No trips recorded");
  } catch { qs("#v-trips").innerHTML = emptyHtml("route", "No trips"); }

  // Events
  try {
    const ev = await get(`/api/events?device_id=${id}&limit=8`);
    qs("#v-events").innerHTML = ev.count ? ev.events.map((e) => `
      <div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">${sevBadge(e.severity)}
        <div class="grow"><div style="font-weight:600">${esc(e.type.replace(/_/g, " "))}</div>
        <div class="muted" style="font-size:12px">${esc(e.detail || "")}</div></div>
        <div class="dim" style="font-size:12px">${fmtDateTime(e.at)}</div></div>`).join("")
      : emptyHtml("check-circle", "No events");
  } catch { qs("#v-events").innerHTML = emptyHtml("bell", "No events"); }

  // Cameras
  try {
    const c = await get(`/api/devices/${id}/cameras`);
    qs("#v-cams").innerHTML = `<div class="row wrap">${c.channels.map((ch) =>
      `<span class="badge neutral">${icon("cctv", "i-sm")} CH${ch.channel_no}</span>`).join("")}</div>
      <div class="muted" style="margin-top:8px;font-size:12px">Open the Video Monitoring workspace to request live or playback.</div>`;
    refreshIcons(qs("#v-cams"));
  } catch { qs("#v-cams").innerHTML = emptyHtml("video-off", "No channels"); }

  return () => { map.remove(); };
}
