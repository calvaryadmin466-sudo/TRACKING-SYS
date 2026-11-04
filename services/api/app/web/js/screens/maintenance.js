import { get, post, del } from "../api.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtDateTime, num, emptyHtml, loadingHtml, toast,
  modal, closeModal, confirmDialog,
} from "../ui.js";

const KINDS = ["service", "inspection", "insurance", "license", "other"];

export async function render(root, ctx) {
  const canManage = ["super_admin", "company_admin", "fleet_manager"].includes(ctx.user.role);
  root.innerHTML = `
    <div class="page-head"><h2>Maintenance</h2><div class="grow"></div>
      ${canManage ? `<button class="btn primary" id="m-new">${icon("plus")} New reminder</button>` : ""}</div>
    <div class="stats" id="m-stats"></div>
    <div class="card section-gap"><div class="table-wrap" id="m-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  let devices = [];

  function stateBadge(s) {
    const map = { overdue: "offline", due_soon: "stale", ok: "online", done: "neutral" };
    const label = { overdue: "Overdue", due_soon: "Due soon", ok: "OK", done: "Done" }[s] || s;
    return `<span class="badge ${map[s] || "neutral"}">${s !== "done" && s !== "ok" ? '<span class="dot"></span>' : ""}${label}</span>`;
  }

  async function load() {
    const [data, devs] = await Promise.all([
      get("/api/maintenance"), get("/api/devices").then((r) => r.devices).catch(() => []),
    ]);
    devices = devs;
    const s = data.summary;
    const stat = (cls, ic, v, l) => `<div class="stat ${cls}"><div class="ico">${icon(ic)}</div>
      <div class="label">${l}</div><div class="value">${v}</div></div>`;
    qs("#m-stats").innerHTML =
      stat("pri", "wrench", s.total, "Reminders") +
      stat("bad", "triangle-alert", s.overdue, "Overdue") +
      stat("warn", "clock", s.due_soon, "Due soon") +
      stat("ok", "check-circle", s.total - s.open, "Completed");
    refreshIcons(qs("#m-stats"));

    const el = qs("#m-table");
    el.innerHTML = data.items.length ? `<table class="tbl"><thead><tr>
      <th>Vehicle / device</th><th>Task</th><th>Type</th><th>Due date</th><th>Due odometer</th>
      <th>Status</th><th></th></tr></thead><tbody>
      ${data.items.map((m) => `<tr>
        <td>${esc(m.device_label || ("#" + m.device_id))}</td>
        <td>${esc(m.title)}${m.notes ? `<div class="muted" style="font-size:12px">${esc(m.notes)}</div>` : ""}</td>
        <td><span class="badge neutral">${esc(m.kind)}</span></td>
        <td class="nowrap">${m.due_date ? fmtDateTime(m.due_date) : "—"} ${m.days_left != null && m.status !== "done" ? `<div class="muted" style="font-size:11px">${m.days_left >= 0 ? m.days_left + "d left" : (-m.days_left) + "d over"}</div>` : ""}</td>
        <td class="num">${m.due_odometer_km != null ? num(m.due_odometer_km, 0) + " km" : "—"}${m.km_left != null && m.status !== "done" ? `<div class="muted" style="font-size:11px">${num(m.km_left, 0)} km</div>` : ""}</td>
        <td>${stateBadge(m.due_state)}</td>
        <td class="right nowrap">${canManage && m.status !== "done" ? `<button class="btn ghost sm" data-done="${m.id}">Mark done</button>` : ""}
          ${canManage ? `<button class="btn ghost sm icon" data-del="${m.id}" title="Delete">${icon("trash-2")}</button>` : ""}</td>
      </tr>`).join("")}</tbody></table>`
      : emptyHtml("wrench", "No maintenance reminders", canManage ? "Add service, inspection, insurance or license reminders." : "");
    refreshIcons(el);
    qsa("[data-done]", el).forEach((b) => b.addEventListener("click", () => complete(Number(b.dataset.done))));
    qsa("[data-del]", el).forEach((b) => b.addEventListener("click", () => remove(Number(b.dataset.del))));
  }

  async function complete(id) {
    try { await post(`/api/maintenance/${id}/complete`); toast("Marked done", "success"); load(); }
    catch (e) { toast(e.detail || "Failed", "error"); }
  }
  async function remove(id) {
    if (!(await confirmDialog("Delete reminder", "Delete this maintenance reminder?", "Delete"))) return;
    try { await del(`/api/maintenance/${id}`); toast("Deleted", "success"); load(); }
    catch (e) { toast(e.detail || "Failed", "error"); }
  }

  function newItem() {
    modal({
      title: "New maintenance reminder",
      bodyHtml: `
        <div class="field-group"><label class="field">Device / vehicle</label>
          <select class="input" id="mi-dev">${devices.map((d) => `<option value="${d.id}">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</option>`).join("")}</select></div>
        <div class="field-group"><label class="field">Task</label><input class="input" id="mi-title" placeholder="e.g. Oil change"></div>
        <div class="field-group"><label class="field">Type</label>
          <select class="input" id="mi-kind">${KINDS.map((k) => `<option>${k}</option>`).join("")}</select></div>
        <div class="field-group"><label class="field">Due date</label><input class="input" type="date" id="mi-date"></div>
        <div class="field-group"><label class="field">Due odometer (km, optional)</label><input class="input" type="number" id="mi-odo"></div>
        <div class="field-group"><label class="field">Notes</label><input class="input" id="mi-notes"></div>`,
      actions: [{ label: "Cancel", onClick: closeModal }, { label: "Create", variant: "primary", onClick: async () => {
        const body = { device_id: Number(qs("#mi-dev").value), title: qs("#mi-title").value.trim(),
          kind: qs("#mi-kind").value, notes: qs("#mi-notes").value.trim() };
        if (qs("#mi-date").value) body.due_date = qs("#mi-date").value;
        if (qs("#mi-odo").value) body.due_odometer_km = Number(qs("#mi-odo").value);
        if (!body.device_id || !body.title) { toast("Device and task required", "warn"); return; }
        try { await post("/api/maintenance", body); toast("Reminder created", "success"); closeModal(); load(); }
        catch (e) { toast(e.detail || "Failed", "error"); } } }],
      onMount: () => qs("#mi-title").focus(),
    });
  }

  if (canManage) qs("#m-new").addEventListener("click", newItem);
  await load();
}
