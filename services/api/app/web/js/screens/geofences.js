import { get, post, del } from "../api.js";
import { baseLayers } from "../map.js";
import {
  icon, refreshIcons, qs, qsa, esc, emptyHtml, toast, modal, closeModal, confirmDialog,
} from "../ui.js";

export async function render(root, ctx) {
  const canManage = ["super_admin", "company_admin", "fleet_manager"].includes(ctx.user.role);
  root.innerHTML = `
    <div class="map-layout">
      <div class="map-side">
        <div style="padding:12px;border-bottom:1px solid var(--border-soft)" class="row">
          <b class="grow">Geofences</b>
          ${canManage ? `<button class="btn primary sm" id="gf-draw">${icon("pencil")} Draw zone</button>` : ""}</div>
        <div class="veh-list" id="gf-list"></div>
      </div>
      <div class="map-wrap">
        <div class="mapel" id="gf-map"></div>
        <div class="map-overlay" style="top:12px;left:12px;right:12px" id="gf-bar"></div>
      </div>
    </div>`;
  refreshIcons(root);

  const map = L.map(qs("#gf-map"), { zoomControl: true }).setView([22.57, 88.36], 11);
  baseLayers()["Dark"].addTo(map);
  setTimeout(() => map.invalidateSize(), 80);
  const shapes = L.layerGroup().addTo(map);
  let draw = null, geofences = [];

  async function load() {
    geofences = (await get("/api/geofences")).geofences;
    shapes.clearLayers();
    geofences.forEach((g) => {
      if (g.ring && g.ring.length >= 3)
        L.polygon(g.ring, { color: "#3282F6", weight: 2, fillOpacity: .1, dashArray: "6 4" }).bindTooltip(g.name).addTo(shapes);
    });
    const el = qs("#gf-list");
    el.innerHTML = geofences.length ? geofences.map((g) => `<div class="veh-item">
      ${icon("hexagon", "i-sm")}<div class="meta"><div class="title">${esc(g.name)}</div>
      <div class="sub">${g.ring.length} points</div></div>
      ${canManage ? `<button class="btn ghost sm icon" data-del="${g.id}" title="Delete">${icon("trash-2")}</button>` : ""}</div>`).join("")
      : emptyHtml("hexagon", "No geofences", canManage ? "Use ‘Draw zone’ to create one." : "");
    refreshIcons(el);
    qsa("[data-del]", el).forEach((b) => b.addEventListener("click", () => remove(Number(b.dataset.del))));
  }

  async function remove(id) {
    const g = geofences.find((x) => x.id === id);
    if (!(await confirmDialog("Delete geofence", `Delete “${g.name}”? This cannot be undone.`, "Delete"))) return;
    try { await del(`/api/geofences/${id}`); toast("Geofence deleted", "success"); load(); }
    catch (e) { toast(e.detail || "Delete failed", "error"); }
  }

  function startDraw() {
    draw = { pts: [], markers: L.layerGroup().addTo(map), line: null };
    qs("#gf-bar").innerHTML = `<div class="card card-pad row" style="gap:10px">
      <span class="muted" id="gf-hint">Click the map to add points (min 3)</span><div class="grow"></div>
      <button class="btn sm" id="gf-cancel">Cancel</button>
      <button class="btn primary sm" id="gf-finish">${icon("check")} Finish &amp; save</button></div>`;
    refreshIcons(qs("#gf-bar"));
    map.on("click", onClick);
    qs("#gf-cancel").addEventListener("click", endDraw);
    qs("#gf-finish").addEventListener("click", finishDraw);
  }
  function onClick(e) {
    draw.pts.push([e.latlng.lat, e.latlng.lng]);
    L.circleMarker(e.latlng, { radius: 4, color: "#3282F6" }).addTo(draw.markers);
    if (draw.line) map.removeLayer(draw.line);
    draw.line = L.polyline(draw.pts, { color: "#3282F6", dashArray: "4 4" }).addTo(map);
    qs("#gf-hint").textContent = `${draw.pts.length} point(s)`;
  }
  function endDraw() {
    if (!draw) return;
    map.off("click", onClick); map.removeLayer(draw.markers); if (draw.line) map.removeLayer(draw.line);
    draw = null; qs("#gf-bar").innerHTML = "";
  }
  function finishDraw() {
    if (!draw || draw.pts.length < 3) { toast("Add at least 3 points", "warn"); return; }
    const pts = draw.pts.slice();
    modal({ title: "Save geofence", bodyHtml: `<div class="field-group"><label class="field">Name</label>
      <input class="input" id="gf-name" placeholder="e.g. Central Depot"></div>`,
      actions: [{ label: "Cancel", onClick: closeModal }, { label: "Save", variant: "primary", onClick: async () => {
        const name = qs("#gf-name").value.trim(); if (!name) { toast("Enter a name", "warn"); return; }
        try { await post("/api/geofences", { name, ring: pts }); toast("Geofence created", "success"); closeModal(); endDraw(); load(); }
        catch (e) { toast(e.detail || "Create failed", "error"); } } }],
      onMount: () => qs("#gf-name").focus() });
  }

  if (canManage) qs("#gf-draw").addEventListener("click", () => { if (!draw) startDraw(); });
  await load();
  return () => map.remove();
}
