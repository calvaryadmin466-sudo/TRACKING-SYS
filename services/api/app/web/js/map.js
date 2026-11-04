// Shared Leaflet helpers: base layers, status colors, heading marker icons.
export const COLORS = { online: "#20C997", moving: "#3282F6", stale: "#F5B942", offline: "#F06464" };

// Base layers, all keyless (no API key / token required). "Dark" reuses the OSM
// tiles with a CSS filter (class dark-tiles) so the dark theme needs no keyed
// provider; "Street" is the standard OSM render; "Satellite" is Esri World
// Imagery (note the {z}/{y}/{x} tile order and maxZoom 17).
export function baseLayers() {
  const OSM = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const attr = "&copy; OpenStreetMap contributors";
  const dark = L.tileLayer(OSM, { maxZoom: 19, attribution: attr, className: "dark-tiles" });
  const street = L.tileLayer(OSM, { maxZoom: 19, attribution: attr });
  const ESRI_SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const satellite = L.tileLayer(ESRI_SAT, {
    maxZoom: 17,
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
  });
  return { "Dark": dark, "Street": street, "Satellite": satellite };
}

// A circular marker with a heading arrow, colored by status.
// opts: { size } marker diameter in px (default 14); { opacity } 0..1 (default 1).
export function vehicleIcon(color, heading, moving, opts = {}) {
  const dot = opts.size || 14;
  const op = opts.opacity == null ? 1 : opts.opacity;
  const box = dot + 4;
  const aw = Math.round(dot * 0.86);
  const arrow = moving
    ? `<div style="position:absolute;top:${-Math.round(dot * 0.62)}px;left:50%;transform:translateX(-50%) rotate(${heading || 0}deg);transform-origin:50% ${dot + 2}px">
         <svg width="${aw}" height="${aw}" viewBox="0 0 12 12"><path d="M6 0 L11 11 L6 8 L1 11 Z" fill="${color}"/></svg></div>`
    : "";
  return L.divIcon({
    className: "", iconSize: [box, box], iconAnchor: [box / 2, box / 2],
    html: `<div style="position:relative;opacity:${op}"><div class="marker-veh" style="width:${dot}px;height:${dot}px;background:${color}"></div>${arrow}</div>`,
  });
}
