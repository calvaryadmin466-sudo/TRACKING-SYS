// Service hub — an app-style grid of every tool, grouped and role-filtered.
// On phones this is the entry point to everything that isn't a primary tab; on
// desktop the same tools also live in the sidebar.
import { session } from "../store.js";
import { serviceToolGroups } from "../router.js";
import { icon, refreshIcons, esc } from "../ui.js";

export async function render(root) {
  const groups = serviceToolGroups(session.user);
  const sections = Object.entries(groups);
  root.innerHTML = `
    <div class="page-head"><h2>Service</h2>
      <div class="grow"></div>
      <span class="muted" style="font-size:12px">All fleet tools &amp; reports</span></div>
    ${sections.map(([g, items]) => `
      <div class="service-group">
        <div class="service-title">${esc(g)}</div>
        <div class="service-grid">
          ${items.map((r) => `
            <a class="service-tile" href="#${r.path}">
              <span class="ti">${icon(r.icon, "i-lg")}</span>
              <span class="tl">${esc(r.title)}</span>
            </a>`).join("")}
        </div>
      </div>`).join("")}
    ${sections.length ? "" : `<div class="state">${icon("grid", "i-lg")}<div class="muted">No tools available for your role.</div></div>`}
  `;
  refreshIcons(root);
}
