// Shared Leaflet helpers: base layers, status colors, heading marker icons.
export const COLORS = { online: "#20C997", moving: "#3282F6", stale: "#F5B942", offline: "#F06464" };

// Base layers: Google Hybrid Satellite (default), Google Pure Satellite, Google Street, and Esri.
export function baseLayers() {
  const GOOGLE_HYBRID = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}";
  const satellite = L.tileLayer(GOOGLE_HYBRID, {
    maxZoom: 22,
    maxNativeZoom: 20,
    attribution: "&copy; Google Maps",
  });

  const GOOGLE_SAT = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}";
  const satPure = L.tileLayer(GOOGLE_SAT, {
    maxZoom: 22,
    maxNativeZoom: 20,
    attribution: "&copy; Google Maps",
  });

  const GOOGLE_ROADS = "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}";
  const street = L.tileLayer(GOOGLE_ROADS, {
    maxZoom: 22,
    maxNativeZoom: 20,
    attribution: "&copy; Google Maps",
  });

  const ESRI_SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const esri = L.tileLayer(ESRI_SAT, {
    maxZoom: 22,
    maxNativeZoom: 17,
    attribution: "Imagery &copy; Esri, Maxar",
  });

  return {
    "Satellite": satellite,
    "Satellite (No Labels)": satPure,
    "Street": street,
    "Esri Imagery": esri,
    "Dark": satellite,
  };
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
