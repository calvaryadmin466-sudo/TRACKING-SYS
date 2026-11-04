import { get, post } from "../api.js";
import {
  icon, refreshIcons, qs, qsa, esc, fmtDateTime, emptyHtml, loadingHtml, toast, modal, closeModal,
} from "../ui.js";

export async function render(root, ctx) {
  const isSuper = ctx.user.role === "super_admin";
  root.innerHTML = `
    <div class="page-head"><h2>Users &amp; Roles</h2><div class="grow"></div>
      ${isSuper ? `<button class="btn" id="new-org">${icon("building-2")} New organization</button>` : ""}
      <button class="btn primary" id="new-user">${icon("user-plus")} New user</button></div>
    <div class="card"><div class="card-head">${icon("users")}<h3>Users</h3></div>
      <div class="table-wrap" id="u-table">${loadingHtml()}</div></div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("building-2")}<h3>Organizations</h3></div><div id="o-list"></div></div>
      <div class="card"><div class="card-head">${icon("shield")}<h3>Roles</h3></div><div id="role-list"></div></div>
    </div>`;
  refreshIcons(root);

  let roles = [], orgs = [];

  async function load() {
    const [u, r, o] = await Promise.all([
      get("/api/users"), get("/api/roles"), get("/api/organizations").catch(() => ({ organizations: [] })),
    ]);
    roles = r.roles; orgs = o.organizations;
    const el = qs("#u-table");
    el.innerHTML = u.users.length ? `<table class="tbl"><thead><tr>
      <th>Email</th><th>Name</th><th>Role</th><th>Org</th><th>Active</th><th>Last login</th></tr></thead><tbody>
      ${u.users.map((x) => `<tr><td>${esc(x.email)}</td><td>${esc(x.full_name || "—")}</td>
        <td><span class="badge neutral">${esc(x.role)}</span></td><td>${x.organization_id ?? "<span class='dim'>—</span>"}</td>
        <td>${x.is_active ? "<span class='badge online'><span class='dot'></span>yes</span>" : "<span class='badge offline'>no</span>"}</td>
        <td class="nowrap">${fmtDateTime(x.last_login_at)}</td></tr>`).join("")}</tbody></table>`
      : emptyHtml("users", "No users");
    refreshIcons(el);
    qs("#o-list").innerHTML = orgs.length ? orgs.map((o2) =>
      `<div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">${icon("building-2", "i-sm")}
        <div class="grow">${esc(o2.name)}</div><span class="dim">#${o2.id}</span></div>`).join("")
      : emptyHtml("building-2", "No organizations");
    qs("#role-list").innerHTML = roles.map((r2) =>
      `<div class="row" style="padding:10px 16px;border-bottom:1px solid var(--border-soft)">${icon("shield", "i-sm")}
        <div class="grow">${esc(r2.name)}</div></div>`).join("");
    refreshIcons(root);
  }

  function newUser() {
    const assignable = isSuper ? roles : roles.filter((r) => ["fleet_manager", "dispatcher", "operator", "readonly"].includes(r.name));
    modal({
      title: "Create user",
      bodyHtml: `
        <div class="field-group"><label class="field">Email</label><input class="input" id="nu-email" type="email"></div>
        <div class="field-group"><label class="field">Full name</label><input class="input" id="nu-name"></div>
        <div class="field-group"><label class="field">Password (min 8)</label><input class="input" id="nu-pass" type="password"></div>
        <div class="field-group"><label class="field">Role</label><select class="input" id="nu-role">
          ${assignable.map((r) => `<option value="${r.name}">${r.name}</option>`).join("")}</select></div>
        ${isSuper ? `<div class="field-group"><label class="field">Organization</label><select class="input" id="nu-org">
          <option value="">— none (platform) —</option>${orgs.map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select></div>` : ""}`,
      actions: [{ label: "Cancel", onClick: closeModal }, { label: "Create", variant: "primary", onClick: async () => {
        const body = { email: qs("#nu-email").value.trim(), full_name: qs("#nu-name").value.trim(),
          password: qs("#nu-pass").value, role: qs("#nu-role").value };
        if (isSuper && qs("#nu-org").value) body.organization_id = Number(qs("#nu-org").value);
        if (!body.email || body.password.length < 8) { toast("Email and 8+ char password required", "warn"); return; }
        try { await post("/api/users", body); toast("User created", "success"); closeModal(); load(); }
        catch (e) { toast(e.detail || "Create failed", "error"); } } }],
      onMount: () => qs("#nu-email").focus(),
    });
  }

  function newOrg() {
    modal({ title: "Create organization", bodyHtml: `
      <div class="field-group"><label class="field">Name</label><input class="input" id="no-name"></div>
      <div class="field-group"><label class="field">Slug</label><input class="input" id="no-slug" placeholder="acme"></div>`,
      actions: [{ label: "Cancel", onClick: closeModal }, { label: "Create", variant: "primary", onClick: async () => {
        try { await post("/api/organizations", { name: qs("#no-name").value.trim(), slug: qs("#no-slug").value.trim() });
          toast("Organization created", "success"); closeModal(); load(); }
        catch (e) { toast(e.detail || "Create failed", "error"); } } }] });
  }

  qs("#new-user").addEventListener("click", newUser);
  if (isSuper) qs("#new-org").addEventListener("click", newOrg);
  await load();
}
