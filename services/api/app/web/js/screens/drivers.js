import { get, post, put, del } from "../api.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtDate, emptyHtml, loadingHtml, toast,
  modal, closeModal, confirmDialog,
} from "../ui.js";

export async function render(root, ctx) {
  const canManage = ["super_admin", "company_admin", "fleet_manager"].includes(ctx.user.role);
  root.innerHTML = `
    <div class="page-head"><h2>Drivers</h2><div class="grow"></div>
      ${canManage ? `<button class="btn primary" id="dr-new">${icon("plus")} New driver</button>` : ""}</div>
    <div class="stats" id="dr-stats"></div>
    <div class="card section-gap"><div class="table-wrap" id="dr-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  let vehicles = [];

  function licenseBadge(state, days) {
    if (state === "expired") {
      const txt = days != null ? `${-days}d expired` : "Expired";
      return `<span class="badge offline"><span class="dot"></span>${txt}</span>`;
    }
    if (state === "expiring_soon") {
      const txt = days != null ? `${days}d left` : "Expiring soon";
      return `<span class="badge stale"><span class="dot"></span>${txt}</span>`;
    }
    return `<span class="badge online"><span class="dot"></span>Valid</span>`;
  }

  async function load() {
    const [data, vehData] = await Promise.all([
      get("/api/drivers"),
      get("/api/vehicles").then((r) => r.vehicles).catch(() => []),
    ]);
    vehicles = vehData;

    const statsEl = qs("#dr-stats");
    if (!statsEl) return;

    const items = data.drivers || [];
    const total = items.length;
    const active = items.filter((d) => d.status === "active").length;
    const expired = items.filter((d) => d.license_state === "expired").length;
    const expiringSoon = items.filter((d) => d.license_state === "expiring_soon").length;

    const stat = (cls, ic, v, l) => `<div class="stat ${cls}"><div class="ico">${icon(ic)}</div>
      <div class="label">${l}</div><div class="value">${v}</div></div>`;
    statsEl.innerHTML =
      stat("pri", "id-card", total, "Total drivers") +
      stat("ok", "check-circle", active, "Active") +
      stat("warn", "clock", expiringSoon, "Expiring soon") +
      stat("bad", "triangle-alert", expired, "License expired");
    refreshIcons(statsEl);

    const el = qs("#dr-table");
    if (!el) return;

    el.innerHTML = items.length ? `<table class="tbl"><thead><tr>
      <th>Driver</th><th>License #</th><th>Class</th><th>License expiry</th><th>Assigned vehicle</th><th>Status</th><th></th>
    </tr></thead><tbody>
      ${items.map((d) => `<tr>
        <td>
          <b>${esc(d.name)}</b>
          ${d.employee_id ? `<span class="muted" style="font-size:11px"> (ID: ${esc(d.employee_id)})</span>` : ""}
          ${d.phone ? `<div class="muted" style="font-size:12px">${esc(d.phone)}</div>` : ""}
        </td>
        <td class="mono">${esc(d.license_number || "—")}</td>
        <td>${esc(d.license_class || "—")}</td>
        <td class="nowrap">${d.license_expiry ? esc(d.license_expiry) : "—"} ${licenseBadge(d.license_state, d.days_left)}</td>
        <td>${d.assigned_vehicle ? `<span class="badge neutral">${icon("truck", "i-sm")} ${esc(d.assigned_vehicle)}</span>` : "<span class='dim'>Unassigned</span>"}</td>
        <td><span class="badge ${d.status === 'active' ? 'online' : 'neutral'}">${esc(d.status)}</span></td>
        <td class="right nowrap">${canManage ? `
          <button class="btn ghost sm" data-assign="${d.id}">Assign</button>
          <button class="btn ghost sm icon" data-edit="${d.id}" title="Edit">${icon("pencil")}</button>
          <button class="btn ghost sm icon" data-del="${d.id}" title="Delete">${icon("trash-2")}</button>` : ""}
        </td>
      </tr>`).join("")}</tbody></table>`
      : emptyHtml("id-card", "No drivers registered", canManage ? "Add drivers to track license expiry and attribute vehicle trips." : "");
    refreshIcons(el);

    qsa("[data-assign]", el).forEach((b) => b.addEventListener("click", () => assignModal(items.find((x) => x.id === Number(b.dataset.assign)))));
    qsa("[data-edit]", el).forEach((b) => b.addEventListener("click", () => driverForm(items.find((x) => x.id === Number(b.dataset.edit)))));
    qsa("[data-del]", el).forEach((b) => b.addEventListener("click", () => removeDriver(Number(b.dataset.del))));
  }

  function assignModal(driver) {
    if (!driver) return;
    const currentVeh = vehicles.find((v) => v.driver_id === driver.id || v.registration === driver.assigned_vehicle);
    modal({
      title: `Assign vehicle — ${driver.name}`,
      bodyHtml: `
        <div class="field-group"><label class="field">Vehicle</label>
          <select class="input" id="dr-veh-select">
            <option value="">(None / Unassign)</option>
            ${vehicles.map((v) => `<option value="${v.id}" ${currentVeh && currentVeh.id === v.id ? "selected" : ""}>${esc(v.registration)} ${v.vehicle_type ? `(${esc(v.vehicle_type)})` : ""}</option>`).join("")}
          </select></div>`,
      actions: [
        { label: "Cancel", onClick: closeModal },
        { label: "Save assignment", variant: "primary", onClick: async () => {
          const val = qs("#dr-veh-select").value;
          const vehicleId = val ? Number(val) : null;
          try {
            await post(`/api/drivers/${driver.id}/assign`, { vehicle_id: vehicleId });
            toast("Assignment updated", "success");
            closeModal();
            load();
          } catch (e) {
            toast(e.detail || "Assignment failed", "error");
          }
        }}
      ]
    });
  }

  function driverForm(driver) {
    const isEdit = !!driver;
    const d = driver || { name: "", license_number: "", license_class: "", license_expiry: "", phone: "", employee_id: "", status: "active", notes: "" };
    modal({
      title: isEdit ? "Edit driver" : "New driver",
      bodyHtml: `
        <div class="field-group"><label class="field">Full name *</label><input class="input" id="df-name" value="${esc(d.name)}" placeholder="Driver name"></div>
        <div class="grid-2">
          <div class="field-group"><label class="field">License number</label><input class="input" id="df-lic" value="${esc(d.license_number || "")}"></div>
          <div class="field-group"><label class="field">License class</label><input class="input" id="df-class" value="${esc(d.license_class || "")}" placeholder="e.g. C, CE, D"></div>
        </div>
        <div class="grid-2">
          <div class="field-group"><label class="field">License expiry date</label><input class="input" type="date" id="df-exp" value="${d.license_expiry ? d.license_expiry.slice(0, 10) : ""}"></div>
          <div class="field-group"><label class="field">Phone number</label><input class="input" id="df-phone" value="${esc(d.phone || "")}"></div>
        </div>
        <div class="grid-2">
          <div class="field-group"><label class="field">Employee ID</label><input class="input" id="df-emp" value="${esc(d.employee_id || "")}"></div>
          <div class="field-group"><label class="field">Status</label>
            <select class="input" id="df-status">
              <option value="active" ${d.status === "active" ? "selected" : ""}>active</option>
              <option value="inactive" ${d.status === "inactive" ? "selected" : ""}>inactive</option>
            </select></div>
        </div>
        <div class="field-group"><label class="field">Notes</label><textarea class="input" id="df-notes" rows="2">${esc(d.notes || "")}</textarea></div>`,
      actions: [
        { label: "Cancel", onClick: closeModal },
        { label: "Save", variant: "primary", onClick: async () => {
          const body = {
            name: qs("#df-name").value.trim(),
            license_number: qs("#df-lic").value.trim(),
            license_class: qs("#df-class").value.trim(),
            license_expiry: qs("#df-exp").value || null,
            phone: qs("#df-phone").value.trim(),
            employee_id: qs("#df-emp").value.trim(),
            status: qs("#df-status").value,
            notes: qs("#df-notes").value.trim(),
          };
          if (!body.name) { toast("Name is required", "warn"); return; }
          try {
            if (isEdit) await put(`/api/drivers/${driver.id}`, body);
            else await post("/api/drivers", body);
            toast("Driver saved", "success");
            closeModal();
            load();
          } catch (e) {
            toast(e.detail || "Failed to save driver", "error");
          }
        }}
      ],
      onMount: () => qs("#df-name").focus(),
    });
  }

  async function removeDriver(id) {
    if (!(await confirmDialog("Delete driver", "Delete this driver? Vehicle assignments will be removed.", "Delete"))) return;
    try {
      await del(`/api/drivers/${id}`);
      toast("Driver deleted", "success");
      load();
    } catch (e) {
      toast(e.detail || "Failed to delete driver", "error");
    }
  }

  if (canManage) qs("#dr-new").addEventListener("click", () => driverForm(null));
  await load();
}
