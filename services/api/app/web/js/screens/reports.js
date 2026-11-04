import { get, getToken } from "../api.js";
import { icon, refreshIcons, qs, esc, num, emptyHtml, loadingHtml, toast } from "../ui.js";

export async function render(root) {
  root.innerHTML = `
    <div class="page-head"><h2>Reports &amp; Analytics</h2><div class="grow"></div>
      <button class="btn" id="r-csv">${icon("download")} Export CSV</button></div>
    <div class="toolbar">
      <input class="input" type="date" id="r-from" style="max-width:170px">
      <input class="input" type="date" id="r-to" style="max-width:170px">
      <button class="btn primary" id="r-apply">${icon("filter")} Apply</button>
      <span class="muted" id="r-note"></span>
    </div>
    <div class="stats" id="r-stats"></div>
    <div class="card section-gap"><div class="card-head">${icon("table")}<h3>Per-vehicle</h3></div>
      <div class="table-wrap" id="r-table">${loadingHtml()}</div></div>`;
  refreshIcons(root);

  function query() {
    const f = qs("#r-from").value, t = qs("#r-to").value;
    const p = []; if (f) p.push("from=" + f + "T00:00:00"); if (t) p.push("to=" + t + "T23:59:59");
    return p.length ? "?" + p.join("&") : "";
  }

  async function load() {
    qs("#r-table").innerHTML = loadingHtml();
    const data = await get("/api/reports/fleet" + query());
    const T = data.totals;
    const stat = (cls, ic, val, label, sub = "") => `<div class="stat ${cls}"><div class="ico">${icon(ic)}</div>
      <div class="label">${label}</div><div class="value">${val}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
    qs("#r-stats").innerHTML =
      stat("pri", "truck", T.devices, "Vehicles") +
      stat("ok", "milestone", num(T.total_distance_km, 1), "Distance (km)") +
      stat("", "route", T.total_trips, "Trips") +
      stat("warn", "gauge", T.total_overspeed_events, "Overspeed events") +
      stat("ok", "activity", T.availability_pct + "%", "Availability") +
      stat("", "timer", "n/a", "Idle time", "not tracked");
    refreshIcons(qs("#r-stats"));
    qs("#r-note").textContent = data.unavailable_metrics.length
      ? "Unavailable with current data: " + data.unavailable_metrics.join(", ") : "";

    const el = qs("#r-table");
    el.innerHTML = data.rows.length ? `<table class="tbl"><thead><tr>
      <th>Vehicle</th><th>Reporting ID</th><th class="num">Trips</th><th class="num">Distance (km)</th>
      <th class="num">Max km/h</th><th class="num">Overspeed</th><th class="num">Harsh</th><th>Online</th></tr></thead><tbody>
      ${data.rows.map((r) => `<tr>
        <td>${esc(r.vehicle || "—")} ${r.simulated ? "<span class='badge sim'>SIM</span>" : ""}</td>
        <td class="mono">${esc(r.reporting_id)}</td><td class="num">${r.trips}</td>
        <td class="num">${num(r.distance_km, 1)}</td><td class="num">${num(r.max_speed_kmh, 0)}</td>
        <td class="num">${r.overspeed_events}</td><td class="num">${r.harsh_events}</td>
        <td>${r.online ? "<span class='badge online'><span class='dot'></span>yes</span>" : "<span class='badge offline'><span class='dot'></span>no</span>"}</td></tr>`).join("")}
      </tbody></table>` : emptyHtml("bar-chart-3", "No data", "No vehicles or records in range.");
    refreshIcons(el);
  }

  async function csv() {
    try {
      const res = await fetch("/api/reports/fleet.csv" + query(), { headers: { Authorization: "Bearer " + getToken() } });
      if (!res.ok) throw new Error();
      const blob = await res.blob(), url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "fleet_report.csv"; a.click();
      URL.revokeObjectURL(url); toast("CSV exported", "success");
    } catch { toast("Export failed", "error"); }
  }

  qs("#r-apply").addEventListener("click", load);
  qs("#r-csv").addEventListener("click", csv);
  await load();
}
