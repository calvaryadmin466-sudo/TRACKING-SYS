import { get, post } from "../api.js";
import { icon, refreshIcons, qs, qsa, esc, fmtDateTime, emptyHtml, toast, statusBadge, modal, closeModal } from "../ui.js";

export async function render(root, ctx) {
  const canVideo = ctx.user.role !== "readonly";
  root.innerHTML = `
    <div class="page-head">
      <h2>${icon("video")} Video Monitoring</h2>
      <div class="grow"></div>
      <button class="btn" id="v-btn-query" ${canVideo ? "" : "disabled"}>${icon("file-search")} Search Device Files (0x9205)</button>
      <select class="input" id="v-dev" style="max-width:280px"><option value="">Select a device…</option></select>
    </div>
    <div class="card card-pad" id="v-head"></div>
    <div class="grid-2 section-gap">
      <div class="card"><div class="card-head">${icon("cctv")}<h3>Camera channels</h3></div><div class="card-pad" id="v-channels"></div></div>
      <div class="card"><div class="card-head">${icon("monitor-play")}<h3>Live view</h3></div><div class="card-pad" id="v-live"></div></div>
    </div>
    <!-- Remote Video Files Query (0x9205) Results -->
    <div class="card section-gap" id="v-query-card" style="display:none">
      <div class="card-head">${icon("file-search")}<h3>Remote Storage Files (JT/T 1078 0x9205)</h3>
        <span class="grow right muted" style="font-size:12px" id="v-query-status"></span>
      </div>
      <div class="table-wrap card-pad" id="v-query-results"></div>
    </div>
    <div class="card section-gap"><div class="card-head">${icon("radio")}<h3>Gateway stream diagnostics</h3>
      <span class="grow right muted" style="font-size:12px">updates every 2s</span></div>
      <div class="table-wrap card-pad" id="v-streams"></div></div>
    <div class="card section-gap"><div class="card-head">${icon("history")}<h3>Recent video sessions</h3></div>
      <div class="table-wrap" id="v-sessions"></div></div>`;
  refreshIcons(root);

  const devices = (await get("/api/devices")).devices;
  if (!qs("#v-dev")) return;
  qs("#v-dev").innerHTML += devices.map((d) =>
    `<option value="${d.id}">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</option>`).join("");

  let currentReportingId = null;
  let currentDeviceId = null;

  async function selectDevice(id) {
    currentDeviceId = id ? Number(id) : null;
    const head = qs("#v-head"), chEl = qs("#v-channels"), liveEl = qs("#v-live");
    if (!head || !chEl || !liveEl) return;
    liveEl.innerHTML = "";
    if (!id) {
      head.innerHTML = `<div class="muted">Select a device to view its cameras and request streams.</div>`;
      chEl.innerHTML = "";
      currentReportingId = null;
      return;
    }
    const d = devices.find((x) => x.id === Number(id));
    if (!d) return;
    currentReportingId = d.reporting_id;
    head.innerHTML = `<div class="row wrap"><b style="font-size:15px">${esc(d.vehicle_registration || d.plate || d.reporting_id)}</b>
      ${statusBadge(d)} <span class="mono muted">${esc(d.reporting_id)}</span></div>
      <div class="muted" style="margin-top:6px;font-size:12px">${d.online ? "Device connected — control commands can be sent." : "Device offline — video commands will be rejected until it connects."}</div>`;
    const cams = await get(`/api/devices/${id}/cameras`);
    if (!qs("#v-channels")) return;
    chEl.innerHTML = `<div class="row wrap">${cams.channels.map((c) => `
      <button class="btn ${canVideo ? "" : "ghost"}" data-ch="${c.channel_no}" ${canVideo ? "" : "disabled"}>
        ${icon("play")} CH${c.channel_no}</button>`).join("")}</div>
      ${canVideo ? "" : `<div class="muted" style="margin-top:8px;font-size:12px">Your role cannot open video streams.</div>`}`;
    refreshIcons(chEl);
    qsa("[data-ch]", chEl).forEach((b) => b.addEventListener("click", () => requestLive(id, Number(b.dataset.ch))));
  }

  async function requestLive(id, channel) {
    const liveEl = qs("#v-live");
    if (!liveEl) return;
    liveEl.innerHTML = `<div class="state"><div class="spinner"></div><div class="muted">Requesting channel ${channel}…</div></div>`;
    try {
      const res = await post(`/api/devices/${id}/video/live`, { channel });
      if (!qs("#v-live")) return;
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
      if (!qs("#v-live")) return;
      liveEl.innerHTML = `<div class="badge offline" style="width:100%;justify-content:flex-start">${esc((e.detail && e.detail.error) || e.detail || "Could not start stream")}</div>`;
    }
  }

  // --- Remote Video File Query (0x9205) Dialog ---
  function openQueryModal() {
    if (!currentDeviceId) {
      toast("Please select a device first.", "warn");
      return;
    }
    const dev = devices.find((x) => x.id === currentDeviceId);
    const today = new Date().toISOString().slice(0, 10);

    const bodyHtml = `
      <div style="font-size:.85rem;color:var(--text-dim);margin-bottom:12px">
        Device: <b>${esc(dev.vehicle_registration || dev.plate || dev.reporting_id)}</b>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:.85rem">
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Channel</label>
          <select class="input" id="q-channel" style="width:100%">
            <option value="0">All Channels</option>
            ${[1, 2, 3, 4, 5, 6, 7, 8].map((i) => `<option value="${i}">CH${i}</option>`).join("")}
          </select>
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Location / Storage</label>
          <select class="input" id="q-storage" style="width:100%">
            <option value="1" selected>Terminal Disk</option>
            <option value="2">SD / Backup Card</option>
            <option value="0">All Storage</option>
          </select>
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Media Type</label>
          <select class="input" id="q-media" style="width:100%">
            <option value="0" selected>Audio and Video</option>
            <option value="2">Video Only</option>
            <option value="1">Audio Only</option>
            <option value="3">Any Media</option>
          </select>
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Stream Type</label>
          <select class="input" id="q-stream" style="width:100%">
            <option value="0" selected>All</option>
            <option value="1">Main Stream</option>
            <option value="2">Sub Stream</option>
          </select>
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Select Date</label>
          <input class="input" type="date" id="q-date" value="${today}" style="width:100%">
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Store Type</label>
          <select class="input" id="q-store" style="width:100%">
            <option value="0" selected>All</option>
            <option value="1">Normal Video</option>
            <option value="2">Alarm Video</option>
          </select>
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">Begin Time</label>
          <input class="input" type="time" id="q-begin" value="00:00:00" step="1" style="width:100%">
        </div>
        <div>
          <label class="field" style="font-weight:600;margin-bottom:4px;display:block">End Time</label>
          <input class="input" type="time" id="q-end" value="23:59:59" step="1" style="width:100%">
        </div>
      </div>`;

    modal({
      title: "Please select a playback search type (0x9205)",
      bodyHtml,
      actions: [
        { label: "Cancel", onClick: closeModal },
        {
          label: "Ok",
          variant: "primary",
          onClick: async () => {
            const dateVal = qs("#q-date")?.value || today;
            const bVal = qs("#q-begin")?.value || "00:00:00";
            const eVal = qs("#q-end")?.value || "23:59:59";
            const channel = Number(qs("#q-channel")?.value || 0);
            const storageType = Number(qs("#q-storage")?.value || 0);
            const mediaType = Number(qs("#q-media")?.value || 0);
            const streamType = Number(qs("#q-stream")?.value || 0);

            // Format date+time to YYMMDDhhmmss
            const datePart = dateVal.replace(/-/g, "").slice(2); // YYYYMMDD -> YYMMDD
            const bPart = bVal.replace(/:/g, "").padEnd(6, "0").slice(0, 6);
            const ePart = eVal.replace(/:/g, "").padEnd(6, "0").slice(0, 6);
            const startTime = datePart + bPart;
            const endTime = datePart + ePart;

            closeModal();
            await executeQuery({
              deviceId: currentDeviceId,
              channel,
              startTime,
              endTime,
              mediaType,
              streamType,
              storageType,
            });
          },
        },
      ],
    });
  }

  async function executeQuery({ deviceId, channel, startTime, endTime, mediaType, streamType, storageType }) {
    const card = qs("#v-query-card");
    const resEl = qs("#v-query-results");
    const stEl = qs("#v-query-status");
    if (!card || !resEl) return;
    card.style.display = "block";
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    resEl.innerHTML = `<div class="state"><div class="spinner"></div><div class="muted">Sending JT/T 1078 0x9205 query to MDVR terminal…</div></div>`;
    if (stEl) stEl.textContent = "Querying…";

    try {
      const resp = await post(`/api/devices/${deviceId}/video/query`, {
        channel,
        start_time: startTime,
        end_time: endTime,
        alarm_type: 0,
        media_type: mediaType,
        stream_type: streamType,
        storage_type: storageType,
      });

      if (!qs("#v-query-results")) return;
      const resources = resp.resources || [];
      if (stEl) stEl.textContent = `${resources.length} resource${resources.length !== 1 ? "s" : ""} found`;

      if (!resources.length) {
        resEl.innerHTML = `
          <div style="padding:16px;text-align:center;color:var(--text-dim)">
            <div>${icon("file-search", "i-lg")}</div>
            <div style="margin-top:8px;font-weight:600">0x9205 Query Dispatched</div>
            <div style="font-size:12px;margin-top:4px;color:var(--text-dim)">${esc(resp.note)}</div>
            <div style="font-size:11px;margin-top:4px" class="muted">Query window: ${esc(startTime)} → ${esc(endTime)} · Channel ${channel === 0 ? "All" : channel}</div>
          </div>`;
        refreshIcons(resEl);
        toast("0x9205 file query dispatched to terminal.", "info");
        return;
      }

      resEl.innerHTML = `
        <table class="tbl"><thead><tr>
          <th>Channel</th><th>Start Time</th><th>End Time</th><th>Size</th><th>Action</th>
        </tr></thead><tbody>
        ${resources.map((r, i) => `
          <tr>
            <td>CH${r.channel}</td>
            <td class="mono">${esc(r.start_time)}</td>
            <td class="mono">${esc(r.end_time)}</td>
            <td>${r.file_size ? Math.round(r.file_size / (1024 * 1024)) + ' MB' : '—'}</td>
            <td>
              <button class="btn sm" data-play-res="${i}">${icon("play")} Play</button>
            </td>
          </tr>`).join("")}
        </tbody></table>`;
      refreshIcons(resEl);

      qsa("[data-play-res]", resEl).forEach((btn) => {
        btn.addEventListener("click", async () => {
          const res = resources[Number(btn.dataset.playRes)];
          try {
            await post(`/api/devices/${deviceId}/video/playback`, {
              channel: res.channel,
              start_time: res.start_time,
              end_time: res.end_time,
            });
            toast(`Playback started for CH${res.channel}`, "success");
            refreshSessions();
          } catch (err) {
            toast(err.message || "Playback failed", "error");
          }
        });
      });
      toast(`Found ${resources.length} video resource(s)`, "success");
    } catch (e) {
      if (!qs("#v-query-results")) return;
      resEl.innerHTML = `<div class="badge offline" style="width:100%;justify-content:flex-start">${esc((e.detail && e.detail.error) || e.detail || "Query failed")}</div>`;
      if (stEl) stEl.textContent = "Failed";
    }
  }

  qs("#v-btn-query")?.addEventListener("click", openQueryModal);

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
    } catch { const el = qs("#v-streams"); if (el) el.innerHTML = emptyHtml("radio", "Gateway unavailable"); }
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
    } catch { const el = qs("#v-sessions"); if (el) el.innerHTML = emptyHtml("history", "No sessions"); }
  }

  qs("#v-dev").addEventListener("change", (e) => selectDevice(e.target.value));
  selectDevice("");
  await refreshStreams(); await refreshSessions();
  const timer = setInterval(() => { refreshStreams(); }, 2500);
  const sessTimer = setInterval(refreshSessions, 8000);
  return () => { clearInterval(timer); clearInterval(sessTimer); };
}
