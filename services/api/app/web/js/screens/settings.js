import { get } from "../api.js";
import { icon, refreshIcons, qs, esc, emptyHtml } from "../ui.js";

export async function render(root, ctx) {
  const health = await get("/api/health").catch(() => ({}));
  const kv = (k, v) => `<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  root.innerHTML = `
    <div class="page-head"><h2>Settings</h2></div>
    <div class="grid-2">
      <div class="card"><div class="card-head">${icon("server")}<h3>Platform</h3></div><div class="card-pad">
        ${kv("Status", health.status === "ok" ? "<span class='badge online'><span class='dot'></span>healthy</span>" : "unknown")}
        ${kv("Storage backend", esc(health.store || "—"))}
        ${kv("Demo feed", health.demo_feed ? "<span class='badge sim'>ENABLED (dev)</span>" : "disabled")}
      </div></div>
      <div class="card"><div class="card-head">${icon("user")}<h3>Your account</h3></div><div class="card-pad">
        ${kv("Email", esc(ctx.user.email))}
        ${kv("Role", esc(ctx.user.role))}
        ${kv("Organization", ctx.user.organization_id ?? "platform (all)")}
      </div></div>
    </div>
    <div class="card section-gap"><div class="card-head">${icon("shield-check")}<h3>Security &amp; configuration</h3></div><div class="card-pad">
      <div class="muted" style="font-size:13px">Secrets (JWT signing key, database credentials, internal control token) are configured via
      environment variables on the server and are never exposed in this interface.</div>
      <ul class="muted" style="font-size:13px;margin-top:10px;line-height:1.9">
        <li>Online / stale thresholds, speed limit and engine settings: server env (<span class="mono">*_THRESHOLD_SECONDS</span>, <span class="mono">SPEED_LIMIT_KMH</span>…).</li>
        <li>Production guard refuses the default JWT secret when <span class="mono">APP_ENV=production</span>.</li>
        <li>Login attempts are rate-limited per IP; all sensitive actions are audited.</li>
      </ul>
    </div></div>`;
  refreshIcons(root);
}
