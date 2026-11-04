import { get } from "../api.js";
import { icon, refreshIcons, qs, esc, fmtDateTime, emptyHtml, loadingHtml } from "../ui.js";

export async function render(root) {
  root.innerHTML = `
    <div class="page-head"><h2>Audit Log</h2><div class="grow"></div>
      <div class="input-icon">${icon("search")}<input class="input" id="a-search" placeholder="Filter actions"></div></div>
    <div class="card"><div class="table-wrap" id="a-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  let entries = [], search = "";

  async function load() {
    entries = (await get("/api/audit-logs?limit=500")).entries;
    draw();
  }
  function draw() {
    const rows = entries.filter((e) => !search ||
      `${e.action} ${e.entity} ${e.entity_id} ${e.detail}`.toLowerCase().includes(search.toLowerCase()));
    const el = qs("#a-table");
    el.innerHTML = rows.length ? `<table class="tbl"><thead><tr>
      <th>Time</th><th>Action</th><th>Entity</th><th>Target</th><th>User</th><th>Detail</th></tr></thead><tbody>
      ${rows.map((e) => `<tr><td class="nowrap">${fmtDateTime(e.at)}</td>
        <td><span class="badge neutral">${esc(e.action)}</span></td><td>${esc(e.entity)}</td>
        <td class="mono">${esc(e.entity_id || "—")}</td><td>${e.user_id ?? "—"}</td>
        <td class="muted">${esc(e.detail || "—")}</td></tr>`).join("")}</tbody></table>`
      : emptyHtml("scroll-text", "No audit entries");
    refreshIcons(el);
  }
  qs("#a-search").addEventListener("input", (e) => { search = e.target.value; draw(); });
  await load();
}
