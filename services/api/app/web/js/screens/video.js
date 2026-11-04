import { get, post } from "../api.js";
import { icon, refreshIcons, qs, qsa, esc, fmtDateTime, emptyHtml, toast, statusBadge } from "../ui.js";

export async function render(root, ctx) {
  const canVideo = ctx.user.role !== "readonly";
  root.innerHTML = `
    <div class="page-head"><h2>Video Monitoring</h2><div class="grow"></div>
      <select class="input" id="v-dev" style="max-width:280px"><option value="">Select a device…</option></select></div>
    <div class="card card-pad" id="v-head"></div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("cctv")}<h3>Camera channels</h3></div><div class="card-pad" id="v-channels"></div></div>
      <div class="card"><div class="card-head">${icon("monitor-play")}<h3>Live view</h3></div><div class="card-pad" id="v-live"></div></div>
    </div>
    <div class="card section-gap"><div class="card-head">${icon("radio")}<h3>Gateway stream diagnostics</h3>
      <span class="grow right muted" style="font-size:12px">updates every 2s</span></div>
      <div class="table-wrap card-pad" id="v-streams"></div></div>
    <div class="card section-gap"><div class="card-head">${icon("history")}<h3>Recent video sessions</h3></div>
      <div class="table-wrap" id="v-sessions"></div></div>`;
  refreshIcons(root);

  const devices = (await get("/api/devices")).devices;
  qs("#v-dev").innerHTML += devices.map((d) =>
    `<option value="${d.id}">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</option>`).join("");

  let currentReportingId = null;

  async function selectDevice(id) {
    const head = qs("#v-head"), chEl = qs("#v-channels"), liveEl = qs("#v-live");
    liveEl.innerHTML = "";
    if (!id) { head.innerHTML = `<div class="muted">Select a device to view its cameras and request streams.</div>`; chEl.innerHTML = ""; currentReportingId = null; return; }
    const d = devices.find((x) => x.id === Number(id));
    currentReportingId = d.reporting_id;
    head.innerHTML = `<div class="row wrap"><b style="font-size:15px">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</b>
      ${statusBadge(d)} <span class="mono muted">${esc(d.reporting_id)}</span></div>
      <div class="muted" style="margin-top:6px;font-size:12px">${d.online ? "Device connected — control commands can be sent." : "Device offline — video commands will be rejected until it connects."}</div>`;
    const cams = await get(`/api/devices/${id}/cameras`);
    chEl.innerHTML = `<div class="row wrap">${cams.channels.map((c) => `
      <button class="btn ${canVideo ? "" : "ghost"}" data-ch="${c.channel_no}" ${canVideo ? "" : "disabled"}>
        ${icon("play")} CH${c.channel_no}</button>`).join("")}</div>
      ${canVideo ? "" : `<div class="muted" style="margin-top:8px;font-size:12px">Your role cannot open video streams.</div>`}`;
    refreshIcons(chEl);
    qsa("[data-ch]", chEl).forEach((b) => b.addEventListener("click", () => requestLive(id, Number(b.dataset.ch))));
  }

  async function requestLive(id, channel) {
    const liveEl = qs("#v-live");
    liveEl.innerHTML = `<div class="state"><div class="spinner"></div><div class="muted">Requesting channel ${channel}…</div></div>`;
    try {
      const res = await post(`/api/devices/${id}/video/live`, { channel });
      liveEl.innerHTML = `
        <div style="background:#0b1320;border:1px solid var(--border);border-radius:var(--r);overflow:hidden">
          <div style="aspect-ratio:16/9;display:grid;place-items:center;color:var(--text-dim);text-align:center;padding:16px">
            <div>${icon("video-off", "i-lg")}<div style="margin-top:8px">No decoded picture</div>
            <div style="font-size:12px">JT/T 1078 → browser playback requires a connected device<br>and the media relay (pending hardware validation)</div></div></div>
          <div style="padding:10px;border-top:1px solid var(--border);font-size:12px" class="muted">${esc(res.note)}</div>
          <div style="padding:10px;border-top:1px solid var(--border)" id="v-livestat" class="muted">waiting for stream…</div>
        </div>`;
      refreshIcons(liveEl);
      toast(`Live command sent for CH${channel}`, "success");
      pollLiveStat(channel);
    } catch (e) {
      liveEl.innerHTML = `<div class="badge offline" style="width:100%;justify-content:flex-start">${esc((e.detail && e.detail.error) || e.detail || "Could not start stream")}</div>`;
    }
  }

  async function pollLiveStat(channel) {
    const el = qs("#v-livestat"); if (!el) return;
    try {
      const data = await get("/api/video/streams");
      const s = (data.streams || []).find((x) => String(x.sim) === String(currentReportingId) && Number(x.channel) === channel);
      el.innerHTML = s
        ? `<b style="color:var(--teal)">● receiving</b> · ${s.packets} pkts · ${s.video_frames} video frames · ${s.key_frames} keyframes · ${Math.round((s.bytes || 0) / 1024)} KB`
        : (data.note ? esc(data.note) : "no stream received yet (device must accept JT/T 1078)");
    } catch {}
  }

  async function refreshStreams() {
    try {
      const data = await get("/api/video/streams");
      const el = qs("#v-streams");
      if (!el) return;
      el.innerHTML = (data.streams && data.streams.length)
        ? `<table class="tbl"><thead><tr><th>SIM</th><th>Ch</th><th class="num">Packets</th><th class="num">Video</th><th class="num">Keyframes</th><th class="num">KB</th></tr></thead><tbody>
           ${data.streams.map((s) => `<tr><td class="mono">${esc(s.sim)}</td><td>${s.channel}</td>
             <td class="num">${s.packets}</td><td class="num">${s.video_frames}</td><td class="num">${s.key_frames}</td>
             <td class="num">${Math.round((s.bytes || 0) / 1024)}</td></tr>`).join("")}</tbody></table>`
        : emptyHtml("radio", "No active streams", data.note || "No device is currently streaming to the media gateway.");
      refreshIcons(el);
    } catch { qs("#v-streams").innerHTML = emptyHtml("radio", "Gateway unavailable"); }
  }

  async function refreshSessions() {
    try {
      const data = await get("/api/video/sessions");
      const el = qs("#v-sessions");
      if (!el) return;
      el.innerHTML = data.sessions.length ? `<table class="tbl"><thead><tr>
        <th>Device</th><th>Channel</th><th>Kind</th><th>Status</th><th>Started</th></tr></thead><tbody>
        ${data.sessions.map((s) => `<tr><td class="mono">${esc(s.reporting_id)}</td><td>${s.channel}</td><td>${s.kind}</td>
          <td>${s.status === "active" ? "<span class='badge online'><span class='dot'></span>active</span>"
            : s.status === "failed" ? "<span class='badge offline'>failed</span>" : "<span class='badge neutral'>" + esc(s.status) + "</span>"}</td>
          <td class="nowrap">${fmtDateTime(s.started_at)}</td></tr>`).join("")}</tbody></table>`
        : emptyHtml("history", "No sessions yet");
      refreshIcons(el);
    } catch { qs("#v-sessions").innerHTML = emptyHtml("history", "No sessions"); }
  }

  qs("#v-dev").addEventListener("change", (e) => selectDevice(e.target.value));
  selectDevice("");
  await refreshStreams(); await refreshSessions();
  const timer = setInterval(() => { refreshStreams(); const el = qs("#v-livestat"); if (el) { const ch = el.dataset.ch; } }, 2500);
  const sessTimer = setInterval(refreshSessions, 8000);
  return () => { clearInterval(timer); clearInterval(sessTimer); };
}
