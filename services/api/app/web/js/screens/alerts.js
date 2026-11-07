import { get, post } from "../api.js";
import { baseLayers } from "../map.js?v=20261105";
import {
  icon, refreshIcons, qs, qsa, esc, fmtDateTime, sevBadge, emptyHtml, loadingHtml, toast,
  modal, closeModal,
} from "../ui.js";

export async function render(root, ctx) {
  const canAct = ctx.user.role !== "readonly";
  root.innerHTML = `
    <div class="page-head"><h2>Alerts &amp; Events</h2><div class="grow"></div>
      <span class="badge alarm" id="open-count" style="display:none"></span></div>
    <div class="toolbar">
      <select class="input" id="f-sev" style="max-width:150px">
        <option value="">All severities</option><option value="alarm">Alarm</option>
        <option value="warning">Warning</option><option value="info">Info</option></select>
      <input class="input" id="f-type" placeholder="Event type contains…" style="max-width:200px">
      <select class="input" id="f-ack" style="max-width:170px">
        <option value="">Acknowledged + open</option><option value="false">Unacknowledged</option><option value="true">Acknowledged</option></select>
      <button class="btn" id="f-apply">${icon("filter")} Apply</button>
    </div>
    <div class="card"><div class="table-wrap" id="ev-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  async function load() {
    const sev = qs("#f-sev").value, type = qs("#f-type").value.trim(), ack = qs("#f-ack").value;
    let url = "/api/events?limit=500";
    if (sev) url += "&severity=" + encodeURIComponent(sev);
    if (ack) url += "&acknowledged=" + ack;
    const data = await get(url);
    if (!qs("#ev-table")) return;  // navigated away
    let evs = data.events;
    if (type) evs = evs.filter((e) => e.type.includes(type.toLowerCase()));
    const oc = qs("#open-count");
    oc.style.display = data.open_alarms ? "inline-flex" : "none";
    oc.textContent = `${data.open_alarms} open`;
    const el = qs("#ev-table");
    if (!el) return;
    if (!evs.length) { el.innerHTML = emptyHtml("bell-off", "No events", "No events match the current filters."); refreshIcons(el); return; }
    el.innerHTML = `<table class="tbl"><thead><tr>
      <th>Severity</th><th>Type</th><th>Device</th><th>Detail</th><th>Time</th><th>Location</th><th>Status</th><th></th></tr></thead><tbody>
      ${evs.map((e) => `<tr>
        <td>${sevBadge(e.severity)}</td><td>${esc(e.type.replace(/_/g, " "))}</td>
        <td class="mono">${esc(e.reporting_id)}</td><td class="muted">${esc(e.detail || "—")}</td>
        <td class="nowrap">${fmtDateTime(e.at)}</td>
        <td>${e.latitude != null ? `<button class="btn ghost sm icon" data-loc="${e.latitude},${e.longitude}" title="View location">${icon("map-pin")}</button>` : "<span class='dim'>—</span>"}</td>
        <td>${e.resolved ? "<span class='badge online'><span class='dot'></span>resolved</span>"
              : e.acknowledged ? "<span class='badge warning'>acknowledged</span>" : "<span class='badge neutral'>open</span>"}</td>
        <td class="right nowrap">${canAct && !e.resolved ? `
          ${!e.acknowledged ? `<button class="btn ghost sm" data-ack="${e.id}">Ack</button>` : ""}
          <button class="btn ghost sm" data-res="${e.id}">Resolve</button>` : ""}</td></tr>`).join("")}
      </tbody></table>`;
    refreshIcons(el);
    qsa("[data-ack]", el).forEach((b) => b.addEventListener("click", () => act(b.dataset.ack, "ack")));
    qsa("[data-res]", el).forEach((b) => b.addEventListener("click", () => act(b.dataset.res, "resolve")));
    qsa("[data-loc]", el).forEach((b) => b.addEventListener("click", () => showLoc(b.dataset.loc)));
  }

  async function act(id, kind) {
    try { await post(`/api/events/${id}/${kind}`); toast(kind === "ack" ? "Acknowledged" : "Resolved", "success"); load(); }
    catch (e) { toast(e.detail || "Action failed", "error"); }
  }

  function showLoc(latlon) {
    const [lat, lon] = latlon.split(",").map(Number);
    modal({ title: "Event location", bodyHtml: `<div style="position:relative;height:300px"><div class="mapel" id="loc-map"></div></div>`,
      actions: [{ label: "Close", onClick: closeModal }],
      onMount: () => { const m = L.map(qs("#loc-map")).setView([lat, lon], 15); baseLayers()["Satellite"].addTo(m);
        L.marker([lat, lon]).addTo(m); setTimeout(() => m.invalidateSize(), 60); } });
  }

  qs("#f-apply").addEventListener("click", load);
  await load();
  const timer = setInterval(load, 20000);
  return () => clearInterval(timer);
}
