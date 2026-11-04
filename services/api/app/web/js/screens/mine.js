// Mine — account screen: profile, quick settings links, and sign out.
import { session } from "../store.js";
import { clearToken, get } from "../api.js";
import { signOut } from "../router.js";
import { icon, refreshIcons, qs, qsa, esc, initials } from "../ui.js";

const ADMIN = ["super_admin", "company_admin"];
const MGR = ["super_admin", "company_admin", "fleet_manager"];

export async function render(root) {
  const u = session.user;
  let org = "";
  try { const me = await get("/api/auth/me"); org = me.organization_name || me.org_name || ""; } catch {}

  const link = (path, ic, label) => `
    <a class="mine-row" href="#${path}">${icon(ic)}<span class="grow">${label}</span>${icon("chevron-right", "i-sm")}</a>`;

  const adminLinks = ADMIN.includes(u.role) ? link("/admin/users", "users", "Users & Roles") + link("/audit", "scroll-text", "Audit Log") : "";
  const mgrLinks = MGR.includes(u.role) ? link("/notifications", "bell-ring", "Notification Rules") : "";

  root.innerHTML = `
    <div class="mine">
      <div class="card card-pad mine-head">
        <div class="mine-avatar">${initials(u.email)}</div>
        <div style="min-width:0">
          <div class="mine-email">${esc(u.email)}</div>
          <div class="row wrap" style="gap:6px;margin-top:7px">
            <span class="badge info">${icon("shield-check", "i-sm")} ${esc(u.role)}</span>
            ${org ? `<span class="badge neutral">${icon("building-2", "i-sm")} ${esc(org)}</span>` : ""}
          </div>
        </div>
      </div>

      <div class="mine-group-title">Account</div>
      <div class="card mine-list">
        ${link("/settings", "settings", "Settings")}
        ${mgrLinks}
        ${adminLinks}
      </div>

      <div class="mine-group-title">Shortcuts</div>
      <div class="card mine-list">
        ${link("/tracking", "map-pin", "Live Monitor")}
        ${link("/reports", "bar-chart-3", "Reports & Analytics")}
        ${link("/alerts", "bell", "Alarms & Events")}
      </div>

      <button class="btn danger mine-signout" id="mine-logout">${icon("log-out")} Sign out</button>
      <div class="mine-foot">FleetTrack · GPS &amp; Video Tracking</div>
    </div>`;
  refreshIcons(root);
  qs("#mine-logout").addEventListener("click", signOut);
}
