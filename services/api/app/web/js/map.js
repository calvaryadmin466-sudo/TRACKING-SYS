// Shared Leaflet helpers: base layers, status colors, heading marker icons.
export const COLORS = { online: "#20C997", moving: "#3282F6", stale: "#F5B942", offline: "#F06464" };

// Base layers from OpenStreetMap (no API key required). "Dark" reuses the OSM
// tiles with a CSS filter (class dark-tiles) so the dark theme needs no keyed
// provider; "Street" is the standard OSM render.
export function baseLayers() {
  const OSM = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const attr = "&copy; OpenStreetMap contributors";
  const dark = L.tileLayer(OSM, { maxZoom: 19, attribution: attr, className: "dark-tiles" });
  const street = L.tileLayer(OSM, { maxZoom: 19, attribution: attr });
  return { "Dark": dark, "Street": street };
}

// A circular marker with a heading arrow, colored by status.
export function vehicleIcon(color, heading, moving) {
  const arrow = moving
    ? `<div style="position:absolute;top:-9px;left:50%;transform:translateX(-50%) rotate(${heading || 0}deg);transform-origin:50% 16px">
         <svg width="12" height="12" viewBox="0 0 12 12"><path d="M6 0 L11 11 L6 8 L1 11 Z" fill="${color}"/></svg></div>`
    : "";
  return L.divIcon({
    className: "", iconSize: [18, 18], iconAnchor: [9, 9],
    html: `<div style="position:relative"><div class="marker-veh" style="width:14px;height:14px;background:${color}"></div>${arrow}</div>`,
  });
}
