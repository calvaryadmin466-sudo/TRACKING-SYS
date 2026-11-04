import { get, getToken } from "../api.js";
import { baseLayers } from "../map.js";
import { icon, refreshIcons, qs, qsa, esc, fmtDateTime, num, emptyHtml, loadingHtml, toast } from "../ui.js";

// Speed tier palette (matches geo_playback.py)
const TIER = {
  L: { label: "0–40 km/h",   color: "#3282F6" },
  M: { label: "41–80 km/h",  color: "#20C997" },
  H: { label: "81–120 km/h", color: "#F7931A" },
  S: { label: ">120 km/h",   color: "#F06464" },
};

function fmtDuration(secs) {
  if (!secs || secs < 0) return "0s";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.round(secs % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// Return ISO string for N hours ago
function hoursAgo(n) {
  return new Date(Date.now() - n * 3600 * 1000).toISOString();
}

// Return start-of-day (UTC) offset by daysAgo
function dayBoundary(daysAgo, end = false) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - daysAgo);
  if (end) {
    d.setUTCHours(23, 59, 59, 999);
  } else {
    d.setUTCHours(0, 0, 0, 0);
  }
  return d.toISOString();
}

// Build a parking icon DivIcon for Leaflet
function parkingDivIcon() {
  return L.divIcon({
    className: "",
    html: `<div style="width:22px;height:22px;background:#1e40af;border:2px solid #fff;border-radius:50%;
                       display:flex;align-items:center;justify-content:center;
                       color:#fff;font-weight:700;font-size:11px;box-shadow:0 1px 4px rgba(0,0,0,.5)">P</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

export async function render(root, ctx) {
  root.innerHTML = `
    <div class="page-head"><h2>${icon("route")} Trips &amp; Playback</h2></div>
    <div class="toolbar" style="flex-wrap:wrap;gap:6px">
      <select class="input" id="t-device" style="max-width:240px"><option value="">Select a vehicle…</option></select>
      <div style="display:flex;gap:4px;flex-wrap:wrap" id="t-presets">
        <button class="btn sm" data-preset="1h">1h ago</button>
        <button class="btn sm" data-preset="today">Today</button>
        <button class="btn sm" data-preset="yesterday">Yesterday</button>
        <button class="btn sm" data-preset="2d">2D ago</button>
      </div>
      <input class="input" type="datetime-local" id="t-from" style="max-width:190px" title="Begin time">
      <input class="input" type="datetime-local" id="t-to"   style="max-width:190px" title="End time">
      <label style="display:flex;align-items:center;gap:6px;font-size:.85rem">
        ${icon("map-pin","i-sm")} Parking ≥
        <input class="input" id="t-min-stop" type="number" value="300" min="60" max="86400" style="width:72px"> s
      </label>
      <button class="btn" id="t-apply">${icon("filter")} Apply</button>
    </div>
    <div class="grid-2">
      <div class="card">
        <div class="card-head">${icon("list")}<h3>Trips</h3></div>
        <div id="t-list" style="max-height:460px;overflow:auto"></div>
      </div>
      <div class="card">
        <div class="card-head">${icon("map")}<h3>Route Playback</h3></div>
        <div style="position:relative;height:460px">
          <div class="mapel" id="t-map"></div>
          <!-- Speed legend overlay -->
          <div id="t-legend" style="
            position:absolute;top:10px;right:10px;z-index:800;
            background:rgba(15,20,30,.82);border-radius:8px;padding:8px 12px;
            font-size:.78rem;color:#e2e8f0;line-height:1.9;pointer-events:none;display:none">
            ${Object.entries(TIER).reverse().map(([k, v]) =>
              `<div><span style="display:inline-block;width:12px;height:12px;border-radius:3px;
                background:${v.color};margin-right:6px"></span>${k} ${v.label}</div>`
            ).join("")}
          </div>
          <!-- Stop list panel -->
          <div id="t-stops" style="
            position:absolute;bottom:0;left:0;right:0;z-index:800;
            background:rgba(15,20,30,.88);border-radius:0 0 8px 8px;
            max-height:160px;overflow-y:auto;display:none;font-size:.8rem;padding:4px 0"></div>
        </div>
      </div>
    </div>`;
  refreshIcons(root);

  const map = L.map(qs("#t-map"), { zoomControl: true }).setView([22.57, 88.36], 5);
  baseLayers()["Dark"].addTo(map);
  setTimeout(() => map.invalidateSize(), 80);
  let layer = null;

  // --- Populate vehicle selector ---
  const devices = (await get("/api/devices")).devices;
  if (!qs("#t-device")) return;   // navigated away
  qs("#t-device").innerHTML += devices.map((d) =>
    `<option value="${d.id}" data-rid="${esc(d.reporting_id)}">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</option>`
  ).join("");

  // --- Preset buttons ---
  qsa("[data-preset]", root).forEach((btn) => {
    btn.addEventListener("click", () => {
      qsa("[data-preset]", root).forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const p = btn.dataset.preset;
      const toLocal = (iso) => new Date(iso).toISOString().slice(0, 16);
      if (p === "1h") {
        qs("#t-from").value = toLocal(hoursAgo(1));
        qs("#t-to").value   = toLocal(new Date().toISOString());
      } else if (p === "today") {
        qs("#t-from").value = toLocal(dayBoundary(0, false));
        qs("#t-to").value   = toLocal(dayBoundary(0, true));
      } else if (p === "yesterday") {
        qs("#t-from").value = toLocal(dayBoundary(1, false));
        qs("#t-to").value   = toLocal(dayBoundary(1, true));
      } else if (p === "2d") {
        qs("#t-from").value = toLocal(dayBoundary(2, false));
        qs("#t-to").value   = toLocal(dayBoundary(1, true));
      }
    });
  });

  // --- Trip list loader ---
  async function loadTrips() {
    const id = qs("#t-device") && qs("#t-device").value;
    const el  = qs("#t-list");
    if (!el) return;
    if (!id) {
      el.innerHTML = emptyHtml("route", "Select a vehicle", "Choose a vehicle to see its trips.");
      refreshIcons(el); return;
    }
    el.innerHTML = loadingHtml();
    const fromVal = qs("#t-from") && qs("#t-from").value;
    const toVal   = qs("#t-to")   && qs("#t-to").value;
    let url = `/api/devices/${id}/trips?limit=200`;
    if (fromVal) url += `&from=${encodeURIComponent(new Date(fromVal).toISOString())}`;
    if (toVal)   url += `&to=${encodeURIComponent(new Date(toVal).toISOString())}`;

    let trips;
    try { trips = (await get(url)).trips; } catch { trips = []; }

    if (!qs("#t-list")) return;  // navigated away during await
    if (!trips || !trips.length) {
      el.innerHTML = emptyHtml("route", "No trips", "No stored trips for this vehicle in the selected range.");
      refreshIcons(el); return;
    }
    el.innerHTML = trips.map((t) => `<div class="veh-item" data-tid="${t.id}" data-did="${id}">
      ${icon("route", "i-sm")}<div class="meta">
        <div class="title">${fmtDateTime(t.started_at)}</div>
        <div class="sub">${num(t.distance_km, 1)} km · ${t.point_count} pts · max ${Math.round(t.max_speed)} km/h</div>
      </div>${icon("play", "i-sm")}</div>`).join("");
    refreshIcons(el);
    qsa(".veh-item", el).forEach((it) =>
      it.addEventListener("click", () => {
        qsa(".veh-item", el).forEach((x) => x.classList.remove("sel"));
        it.classList.add("sel");
        playTrip(Number(it.dataset.tid), Number(it.dataset.did));
      })
    );
  }

  // --- Playback renderer ---
  async function playTrip(tid, deviceId) {
    if (layer) { map.removeLayer(layer); layer = null; }
    const legendEl = qs("#t-legend");
    const stopsEl  = qs("#t-stops");
    if (legendEl) legendEl.style.display = "none";
    if (stopsEl)  stopsEl.style.display  = "none";

    // Load the trip to get its time window
    let tripData;
    try { tripData = await get(`/api/trips/${tid}`); } catch { toast("Failed to load trip.", "error"); return; }
    if (!qs("#t-map")) return;  // navigated away

    const minStopEl = qs("#t-min-stop");
    const minStopS  = minStopEl ? (parseInt(minStopEl.value, 10) || 300) : 300;

    const from = encodeURIComponent(tripData.started_at);
    const to   = encodeURIComponent(tripData.ended_at);
    let pb;
    try {
      pb = await get(`/api/devices/${deviceId}/playback?from=${from}&to=${to}&min_stop_s=${minStopS}&limit=10000`);
    } catch { toast("Playback data unavailable.", "error"); return; }
    if (!qs("#t-map")) return;

    const { segments = [], stops = [], positions = [] } = pb;
    if (!positions.length) {
      toast("No position data for this trip.", "info"); return;
    }

    layer = L.layerGroup().addTo(map);
    const allCoords = [];

    // Draw speed-colored segments
    for (const seg of segments) {
      if (!seg.path || seg.path.length < 2) continue;
      L.polyline(seg.path, { color: seg.color, weight: 4, opacity: 0.9 }).addTo(layer);
      allCoords.push(...seg.path);
    }

    // Start / End markers
    const first = positions[0];
    const last  = positions[positions.length - 1];
    L.circleMarker([first.latitude, first.longitude],
      { radius: 7, color: "#fff", weight: 2, fillColor: "#20C997", fillOpacity: 1 })
      .bindTooltip(`<b>Start</b><br>${fmtDateTime(first.device_time)}`)
      .addTo(layer);
    L.circleMarker([last.latitude, last.longitude],
      { radius: 7, color: "#fff", weight: 2, fillColor: "#F06464", fillOpacity: 1 })
      .bindTooltip(`<b>End</b><br>${fmtDateTime(last.device_time)}`)
      .addTo(layer);

    // Parking stop markers
    for (const stop of stops) {
      L.marker([stop.latitude, stop.longitude], { icon: parkingDivIcon() })
        .bindPopup(`
          <div style="min-width:180px">
            <b style="font-size:.9rem">Parking Stop</b><br>
            <span style="color:#94a3b8;font-size:.8rem">From:</span> ${fmtDateTime(stop.started_at)}<br>
            <span style="color:#94a3b8;font-size:.8rem">To:</span> ${fmtDateTime(stop.ended_at)}<br>
            <span style="color:#94a3b8;font-size:.8rem">Duration:</span> <b>${fmtDuration(stop.duration_s)}</b>
          </div>`)
        .addTo(layer);
    }

    // Fit map
    if (allCoords.length) {
      map.fitBounds(L.latLngBounds(allCoords).pad(0.15));
    }

    // Show legend
    if (legendEl) legendEl.style.display = "block";

    // Show stop list panel
    if (stopsEl) {
      if (stops.length) {
        stopsEl.style.display = "block";
        stopsEl.innerHTML = `<div style="padding:4px 10px;color:#94a3b8;font-size:.75rem">${icon("map-pin","i-sm")} ${stops.length} parking stop${stops.length > 1 ? "s" : ""}</div>` +
          stops.map((s, i) => `
            <div style="padding:3px 10px;border-top:1px solid rgba(255,255,255,.07);cursor:pointer"
                 class="stop-row" data-idx="${i}">
              <span style="font-weight:600">P${i + 1}</span>
              <span style="color:#94a3b8;margin:0 6px">·</span>
              ${fmtDateTime(s.started_at)} → ${fmtDateTime(s.ended_at)}
              <span style="float:right;color:#60a5fa">${fmtDuration(s.duration_s)}</span>
            </div>`).join("");
        refreshIcons(stopsEl);
        qsa(".stop-row", stopsEl).forEach((row) => {
          const s = stops[Number(row.dataset.idx)];
          row.addEventListener("click", () => map.setView([s.latitude, s.longitude], 16));
        });
      } else {
        stopsEl.style.display = "none";
      }
    }

    // Summary toast
    const su = pb.summary || {};
    toast(
      `${positions.length} pts · max ${su.max_speed_kmh ?? "—"} km/h · ${stops.length} stop${stops.length !== 1 ? "s" : ""}`,
      "info"
    );
  }

  qs("#t-apply").addEventListener("click", loadTrips);
  qs("#t-device").addEventListener("change", loadTrips);

  // Initial empty state
  qs("#t-list").innerHTML = emptyHtml("route", "Select a vehicle", "Choose a vehicle to see its trips.");
  refreshIcons(qs("#t-list"));

  return () => map.remove();
}
