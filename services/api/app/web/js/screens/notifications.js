import { get, post, put, del } from "../api.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtDateTime, emptyHtml, loadingHtml, toast,
  modal, closeModal, confirmDialog,
} from "../ui.js";

const SEVERITIES = ["info", "warning", "alarm"];

export async function render(root, ctx) {
  const canManage = ["super_admin", "company_admin", "fleet_manager"].includes(ctx.user.role);
  root.innerHTML = `
    <div class="page-head"><h2>Notification Rules</h2><div class="grow"></div>
      ${canManage ? `<button class="btn primary" id="n-new">${icon("plus")} New rule</button>` : ""}</div>
    <div class="card"><div class="card-head">${icon("webhook")}<h3>Rules</h3>
      <span class="grow right muted" style="font-size:12px">Webhook delivery is live; email needs SMTP</span></div>
      <div class="table-wrap" id="n-rules">${loadingHtml()}</div></div>
    <div class="card section-gap"><div class="card-head">${icon("list")}<h3>Recent deliveries</h3></div>
      <div class="table-wrap" id="n-log">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  async function load() {
    const [rules, logd] = await Promise.all([get("/api/notifications/rules"), get("/api/notifications/log?limit=50")]);
    const el = qs("#n-rules");
    el.innerHTML = rules.rules.length ? `<table class="tbl"><thead><tr>
      <th>Name</th><th>Events</th><th>Min severity</th><th>Channel</th><th>Target</th><th>Active</th><th></th></tr></thead><tbody>
      ${rules.rules.map((r) => `<tr>
        <td>${esc(r.name)}</td>
        <td>${r.event_types.length ? r.event_types.map((t) => `<span class="badge neutral">${esc(t)}</span>`).join(" ") : "<span class='dim'>any</span>"}</td>
        <td>${esc(r.min_severity)}</td><td>${esc(r.channel)}</td>
        <td class="mono" style="max-width:220px;overflow:hidden;text-overflow:ellipsis">${esc(r.target || "—")}</td>
        <td>${r.active ? "<span class='badge online'><span class='dot'></span>on</span>" : "<span class='badge offline'>off</span>"}</td>
        <td class="right nowrap">${canManage ? `
          <button class="btn ghost sm" data-test="${r.id}">${icon("send", "i-sm")} Test</button>
          <button class="btn ghost sm icon" data-edit="${r.id}" title="Edit">${icon("pencil")}</button>
          <button class="btn ghost sm icon" data-del="${r.id}" title="Delete">${icon("trash-2")}</button>` : ""}</td>
      </tr>`).join("")}</tbody></table>`
      : emptyHtml("webhook", "No rules", canManage ? "Create a rule to push events to a webhook." : "");
    refreshIcons(el);
    qsa("[data-test]", el).forEach((b) => b.addEventListener("click", () => testRule(Number(b.dataset.test))));
    qsa("[data-edit]", el).forEach((b) => b.addEventListener("click", () => editRule(rules.rules.find((x) => x.id === Number(b.dataset.edit)))));
    qsa("[data-del]", el).forEach((b) => b.addEventListener("click", () => removeRule(Number(b.dataset.del))));

    const lg = qs("#n-log");
    lg.innerHTML = logd.entries.length ? `<table class="tbl"><thead><tr>
      <th>Time</th><th>Event</th><th>Channel</th><th>Target</th><th>Status</th><th>Detail</th></tr></thead><tbody>
      ${logd.entries.map((n) => `<tr><td class="nowrap">${fmtDateTime(n.at)}</td><td>${esc(n.event_type)}</td>
        <td>${esc(n.channel)}</td><td class="mono" style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${esc(n.target)}</td>
        <td>${n.status === "delivered" ? "<span class='badge online'><span class='dot'></span>delivered</span>"
          : n.status === "failed" ? "<span class='badge offline'>failed</span>" : "<span class='badge warning'>" + esc(n.status) + "</span>"}</td>
        <td class="muted">${esc(n.detail || "")}</td></tr>`).join("")}</tbody></table>`
      : emptyHtml("list", "No deliveries yet");
    refreshIcons(lg);
  }

  async function testRule(id) {
    try { const r = await post(`/api/notifications/rules/${id}/test`); toast(`Test: ${r.status} — ${r.detail}`, r.status === "delivered" ? "success" : "warn"); load(); }
    catch (e) { toast(e.detail || "Test failed", "error"); }
  }
  async function removeRule(id) {
    if (!(await confirmDialog("Delete rule", "Delete this notification rule?", "Delete"))) return;
    try { await del(`/api/notifications/rules/${id}`); toast("Deleted", "success"); load(); }
    catch (e) { toast(e.detail || "Failed", "error"); }
  }

  function ruleForm(r) {
    const isEdit = !!r;
    r = r || { name: "", event_types: [], min_severity: "warning", channel: "webhook", target: "", active: true };
    modal({
      title: isEdit ? "Edit rule" : "New rule",
      bodyHtml: `
        <div class="field-group"><label class="field">Name</label><input class="input" id="nr-name" value="${esc(r.name)}"></div>
        <div class="field-group"><label class="field">Event types (comma-separated, blank = any; supports alarm_*)</label>
          <input class="input" id="nr-types" value="${esc(r.event_types.join(', '))}" placeholder="overspeed, alarm_*, geofence_enter"></div>
        <div class="field-group"><label class="field">Minimum severity</label>
          <select class="input" id="nr-sev">${SEVERITIES.map((s) => `<option ${s === r.min_severity ? "selected" : ""}>${s}</option>`).join("")}</select></div>
        <div class="field-group"><label class="field">Channel</label>
          <select class="input" id="nr-chan"><option value="webhook" ${r.channel === "webhook" ? "selected" : ""}>webhook</option>
            <option value="email" ${r.channel === "email" ? "selected" : ""}>email (needs SMTP)</option></select></div>
        <div class="field-group"><label class="field">Target (webhook URL or email)</label><input class="input" id="nr-target" value="${esc(r.target)}" placeholder="https://hooks.example.com/..."></div>
        <label class="row" style="gap:8px"><input type="checkbox" id="nr-active" ${r.active ? "checked" : ""}> Active</label>`,
      actions: [{ label: "Cancel", onClick: closeModal }, { label: "Save", variant: "primary", onClick: async () => {
        const body = { name: qs("#nr-name").value.trim(),
          event_types: qs("#nr-types").value.split(",").map((s) => s.trim()).filter(Boolean),
          min_severity: qs("#nr-sev").value, channel: qs("#nr-chan").value,
          target: qs("#nr-target").value.trim(), active: qs("#nr-active").checked };
        if (!body.name) { toast("Name required", "warn"); return; }
        try {
          if (isEdit) await put(`/api/notifications/rules/${r.id}`, body);
          else await post("/api/notifications/rules", body);
          toast("Saved", "success"); closeModal(); load();
        } catch (e) { toast(e.detail || "Failed", "error"); } } }],
      onMount: () => qs("#nr-name").focus(),
    });
  }
  const editRule = (r) => ruleForm(r);

  if (canManage) qs("#n-new").addEventListener("click", () => ruleForm(null));
  await load();
  const timer = setInterval(load, 15000);
  return () => clearInterval(timer);
}
