// UI toolkit: formatters, status helpers, icons, badges, states, toasts, modals.
import { ICONS } from "./icons.js";

export const qs = (sel, root = document) => root.querySelector(sel);
export const qsa = (sel, root = document) => [...root.querySelectorAll(sel)];

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function icon(name, cls = "") {
  const body = ICONS[name] || ICONS._fallback;
  return `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}
// Icons are inlined SVG now; refreshIcons is retained as a no-op so existing call
// sites keep working.
export function refreshIcons(_root) {}

// ---------- formatters ----------
export function fmtAge(seconds) {
  if (seconds == null) return "never";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
export function fmtDateTime(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleString(); }
export function fmtDate(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleDateString(); }
export function fmtTime(iso) { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleTimeString(); }
export function num(n, dp = 0) { return (n == null) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: dp }); }
export function initials(s) { return (s || "?").slice(0, 2).toUpperCase(); }

// ---------- device status ----------
export function deviceStatus(d) {
  if (!d.online) return "offline";
  if (d.position && d.position.fresh) return "online";
  return "stale";
}
export function isMoving(d) { return !!(d.position && d.position.fresh && d.position.speed > 3); }

export function statusBadge(d) {
  const st = deviceStatus(d);
  const label = st === "online" ? (isMoving(d) ? "Moving" : "Online") : st === "stale" ? "Stale GPS" : "Offline";
  const cls = st === "online" ? (isMoving(d) ? "moving" : "online") : st;
  return `<span class="badge ${cls}"><span class="dot"></span>${label}</span>`;
}
export function simBadge(d) { return d.simulated ? `<span class="badge sim">SIMULATED</span>` : ""; }
export function sevBadge(sev) {
  const c = sev === "alarm" ? "alarm" : sev === "warning" ? "warning" : "info";
  return `<span class="badge ${c}">${esc(sev)}</span>`;
}

// ---------- states ----------
export function loadingHtml(msg = "Loading…") {
  return `<div class="state"><div class="spinner"></div><div class="muted">${esc(msg)}</div></div>`;
}
export function emptyHtml(ic, title, sub = "") {
  return `<div class="state">${icon(ic, "i-lg")}<h4>${esc(title)}</h4>${sub ? `<div class="muted">${esc(sub)}</div>` : ""}</div>`;
}
export function errorHtml(msg) {
  return `<div class="state">${icon("triangle-alert", "i-lg")}<h4>Something went wrong</h4><div class="muted">${esc(msg)}</div></div>`;
}

// ---------- toasts ----------
export function toast(msg, type = "info", timeout = 3800) {
  const root = qs("#toasts"); if (!root) return;
  const ic = type === "success" ? "check-circle" : type === "error" ? "circle-x" : type === "warn" ? "triangle-alert" : "info";
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(ic)}<div>${esc(msg)}</div>`;
  root.appendChild(el); refreshIcons(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .25s"; setTimeout(() => el.remove(), 260); }, timeout);
}

// ---------- modal ----------
export function closeModal() { const r = qs("#modal-root"); if (r) r.innerHTML = ""; }
export function modal({ title, bodyHtml, actions = [], onMount }) {
  const root = qs("#modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" data-close>
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head"><h3>${esc(title)}</h3><button class="btn ghost icon" data-close style="margin-left:auto">${icon("x")}</button></div>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-foot">${actions.map((a, i) =>
          `<button class="btn ${a.variant || ""}" data-act="${i}">${esc(a.label)}</button>`).join("")}</div>
      </div>
    </div>`;
  refreshIcons(root);
  qsa("[data-close]", root).forEach((e) => e.addEventListener("click", (ev) => { if (ev.target === e) closeModal(); }));
  actions.forEach((a, i) => { const b = qs(`[data-act="${i}"]`, root); if (b) b.addEventListener("click", () => a.onClick?.()); });
  if (onMount) onMount(qs(".modal", root));
}

export async function confirmDialog(title, message, confirmLabel = "Confirm", variant = "danger") {
  return new Promise((resolve) => {
    modal({
      title, bodyHtml: `<div class="muted">${esc(message)}</div>`,
      actions: [
        { label: "Cancel", onClick: () => { closeModal(); resolve(false); } },
        { label: confirmLabel, variant, onClick: () => { closeModal(); resolve(true); } },
      ],
    });
  });
}
