import { get, patch, post } from "../api.js";
import { openMessageDialog } from "../message_dialog.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtAge, fmtDateTime, statusBadge, simBadge, deviceStatus,
  modal, closeModal, toast, emptyHtml, loadingHtml,
} from "../ui.js";

export async function render(root, ctx) {
  const canManage = ["super_admin", "company_admin", "fleet_manager"].includes(ctx.user.role);
  root.innerHTML = `
    <div class="page-head"><h2>Device Management</h2><div class="grow"></div>
      <div class="input-icon">${icon("search")}<input class="input" id="dev-search" placeholder="Search reporting ID, serial, vehicle"></div>
      ${canManage ? `<button class="btn primary" id="dev-register">${icon("plus")} Register device</button>` : ""}</div>
    <div class="card"><div class="table-wrap" id="dev-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  let devices = [], vehicles = [], search = "";

  async function load() {
    [devices, vehicles] = await Promise.all([
      get("/api/devices").then((r) => r.devices),
      get("/api/vehicles").then((r) => r.vehicles).catch(() => []),
    ]);
    draw();
  }

  function draw() {
    const rows = devices.filter((d) => {
      if (!search) return true;
      const q = search.toLowerCase();
      return `${d.reporting_id} ${d.serial_number} ${d.vehicle_registration || ""} ${d.plate || ""} ${d.model}`.toLowerCase().includes(q);
    });
    const el = qs("#dev-table");
    if (!el) return;
    if (!rows.length) { el.innerHTML = emptyHtml("cpu", "No devices", "Devices appear here once they connect or are registered."); refreshIcons(el); return; }
    el.innerHTML = `<table class="tbl"><thead><tr>
      <th>Status</th><th>Reporting ID</th><th>Plate</th><th>Decoder IP</th><th>Serial no.</th><th>Model</th><th>Vehicle</th>
      <th>Last comm</th><th>Last GPS</th><th>Active</th><th></th></tr></thead><tbody>
      ${rows.map((d) => `<tr>
        <td>${statusBadge(d)} ${simBadge(d)}</td>
        <td class="mono">${esc(d.reporting_id)}</td>
        <td>${d.plate ? esc(d.plate) : "<span class='dim'>—</span>"}</td>
        <td class="mono">${d.ip_address ? esc(d.ip_address) : "<span class='dim'>—</span>"}</td>
        <td class="mono">${esc(d.serial_number || "—")}</td>
        <td>${esc(d.model || "—")}</td>
        <td>${d.vehicle_registration ? esc(d.vehicle_registration) : `<span class="dim">unassigned</span>`}</td>
        <td class="nowrap">${fmtAge(d.last_seen_age_s)}</td>
        <td class="nowrap">${d.has_position ? (d.position.fresh ? "fresh" : `<span class="badge stale"><span class="dot"></span>stale</span>`) : "<span class='dim'>none</span>"}</td>
        <td>${d.active ? "<span class='badge online'><span class='dot'></span>yes</span>" : "<span class='badge offline'><span class='dot'></span>no</span>"}</td>
        <td class="right nowrap">
          <a class="btn ghost sm icon" href="#/vehicle/${d.id}" title="Details">${icon("info")}</a>
          <button class="btn ghost sm icon" data-msg="${d.id}" title="Send text message">${icon("send")}</button>
          ${canManage ? `<button class="btn ghost sm icon" data-edit="${d.id}" title="Edit plate / decoder IP">${icon("pencil")}</button>
          <button class="btn ghost sm icon" data-assign="${d.id}" title="Assign vehicle">${icon("link")}</button>
          <button class="btn ghost sm icon" data-active="${d.id}" title="${d.active ? "Deactivate" : "Activate"}">${icon(d.active ? "power-off" : "power")}</button>
          <button class="btn ghost sm icon" data-pkts="${d.id}" title="Raw packet diagnostics">${icon("file-search")}</button>` : ""}
        </td></tr>`).join("")}</tbody></table>`;
    refreshIcons(el);
    qsa("[data-msg]", el).forEach((b) => b.addEventListener("click", () => {
      const dev = devices.find((x) => x.id === Number(b.dataset.msg));
      if (dev) {
        openMessageDialog({
          deviceId: dev.id,
          vehicleName: dev.vehicle_registration || dev.plate || dev.reporting_id,
          reportingId: dev.reporting_id,
        });
      }
    }));
    qsa("[data-edit]", el).forEach((b) => b.addEventListener("click", () => editDevice(Number(b.dataset.edit))));
    qsa("[data-assign]", el).forEach((b) => b.addEventListener("click", () => assign(Number(b.dataset.assign))));
    qsa("[data-active]", el).forEach((b) => b.addEventListener("click", () => toggleActive(Number(b.dataset.active))));
    qsa("[data-pkts]", el).forEach((b) => b.addEventListener("click", () => showPackets(Number(b.dataset.pkts))));
  }

  function assign(id) {
    const d = devices.find((x) => x.id === id);
    modal({
      title: `Assign vehicle — ${d.reporting_id}`,
      bodyHtml: `<div class="field-group"><label class="field">Vehicle</label>
        <select class="input" id="veh-sel"><option value="">— unassigned —</option>
        ${vehicles.map((v) => `<option value="${v.id}" ${v.id === d.vehicle_id ? "selected" : ""}>${esc(v.registration)}</option>`).join("")}</select></div>
        ${vehicles.length ? "" : `<div class="muted">No vehicles yet. Create vehicles first.</div>`}`,
      actions: [{ label: "Cancel", onClick: closeModal },
        { label: "Save", variant: "primary", onClick: async () => {
          const vid = qs("#veh-sel").value;
          try { await patch(`/api/devices/${id}`, { vehicle_id: vid ? Number(vid) : null });
            toast("Vehicle assignment updated", "success"); closeModal(); load();
          } catch (e) { toast(e.detail || "Update failed", "error"); } } }],
    });
  }

  async function toggleActive(id) {
    const d = devices.find((x) => x.id === id);
    try { await patch(`/api/devices/${id}`, { active: !d.active }); toast(`Device ${d.active ? "deactivated" : "activated"}`, "success"); load(); }
    catch (e) { toast(e.detail || "Update failed", "error"); }
  }

  async function showPackets(id) {
    const d = devices.find((x) => x.id === id);
    modal({ title: `Raw packets — ${d.reporting_id}`, bodyHtml: loadingHtml(), actions: [{ label: "Close", onClick: closeModal }] });
    try {
      const data = await get(`/api/devices/${id}/packets?limit=50`);
      const body = qs(".modal-body");
      body.innerHTML = data.count ? `<div class="table-wrap"><table class="tbl"><thead><tr>
        <th>Received</th><th>Message</th><th>Decoded</th><th>Checksum</th><th>Len</th></tr></thead><tbody>
        ${data.packets.map((p) => `<tr><td class="nowrap">${fmtDateTime(p.received_at)}</td>
          <td>${esc(p.message_name)}</td>
          <td>${p.decoded ? "<span class='badge online'><span class='dot'></span>yes</span>" : "<span class='badge offline'><span class='dot'></span>no</span>"}</td>
          <td>${p.checksum_ok ? "ok" : "<span class='badge warning'>bad</span>"}</td><td class="num">${p.length}</td></tr>`).join("")}
        </tbody></table></div>`
        : emptyHtml("file-x", "No stored packets", "Raw packets are captured by the ingestion server into PostgreSQL. In the in-memory dev store none are kept.");
      refreshIcons(body);
    } catch (e) { qs(".modal-body").innerHTML = `<div class="muted">${esc(e.detail || "Failed to load")}</div>`; }
  }

  function registerDevice() {
    modal({
      title: "Register device",
      bodyHtml: `
        <p class="muted" style="margin:0 0 14px;font-size:12.5px">Pre-register an MDVR by its identifiers. It shows up immediately and links automatically when the unit dials in over JT/T 808.</p>
        <div class="field-group"><label class="field" for="rd-id">Device ID — JT/T 808 reporting ID</label>
          <input class="input" id="rd-id" placeholder="e.g. 013800138000" autocomplete="off" inputmode="numeric"></div>
        <div class="field-group"><label class="field" for="rd-plate">Plate number</label>
          <input class="input" id="rd-plate" placeholder="e.g. T-786EUH"></div>
        <div class="field-group"><label class="field" for="rd-ip">Decoder IP address</label>
          <input class="input" id="rd-ip" placeholder="e.g. 10.0.0.42" autocomplete="off"></div>
        <div class="field-group"><label class="field" for="rd-model">Model (optional)</label>
          <input class="input" id="rd-model" placeholder="e.g. XV-900-8"></div>`,
      onMount: () => qs("#rd-id") && qs("#rd-id").focus(),
      actions: [{ label: "Cancel", onClick: closeModal },
        { label: "Register", variant: "primary", onClick: async () => {
          const device_id = qs("#rd-id").value.trim();
          if (!device_id) { toast("Device ID is required", "warn"); return; }
          try {
            const r = await post("/api/devices", {
              device_id, plate: qs("#rd-plate").value.trim(),
              ip_address: qs("#rd-ip").value.trim(), model: qs("#rd-model").value.trim() });
            toast(r.created ? "Device registered" : "Device details updated", "success");
            closeModal(); load();
          } catch (e) { toast((e.detail && (e.detail.error || e.detail)) || "Registration failed", "error"); }
        } }],
    });
  }

  function editDevice(id) {
    const d = devices.find((x) => x.id === id);
    if (!d) return;
    modal({
      title: `Edit — ${d.reporting_id}`,
      bodyHtml: `
        <div class="field-group"><label class="field" for="ed-plate">Plate number</label>
          <input class="input" id="ed-plate" value="${esc(d.plate || "")}"></div>
        <div class="field-group"><label class="field" for="ed-ip">Decoder IP address</label>
          <input class="input" id="ed-ip" value="${esc(d.ip_address || "")}"></div>`,
      actions: [{ label: "Cancel", onClick: closeModal },
        { label: "Save", variant: "primary", onClick: async () => {
          try {
            await patch(`/api/devices/${id}`, { plate: qs("#ed-plate").value.trim(), ip_address: qs("#ed-ip").value.trim() });
            toast("Device updated", "success"); closeModal(); load();
          } catch (e) { toast(e.detail || "Update failed", "error"); }
        } }],
    });
  }

  qs("#dev-register")?.addEventListener("click", registerDevice);
  qs("#dev-search").addEventListener("input", (e) => { search = e.target.value; draw(); });
  await load();
  const timer = setInterval(load, 20000);
  return () => clearInterval(timer);
}
