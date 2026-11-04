import { post } from "./api.js";
import { icon, refreshIcons, qs, qsa, esc, modal, closeModal, toast } from "./ui.js";

const TEMPLATES = [
  "Please contact fleet dispatch immediately.",
  "Route diversion: proceed to designated checkpoint.",
  "Vehicle service inspection scheduled for today.",
  "Drive safely. Adverse road conditions ahead.",
  "Scheduled break due. Please pull over safely.",
  "Return to base depot upon delivery completion.",
];

export function openMessageDialog({ deviceId, vehicleName, reportingId }) {
  const label = vehicleName || reportingId || `Device #${deviceId}`;
  const bodyHtml = `
    <div style="font-size:.85rem;color:var(--text-dim,#94a3b8);margin-bottom:10px">
      Target: <b style="color:var(--text,#f8fafc)">${esc(label)}</b> <span class="mono" style="font-size:.78rem">(${esc(reportingId)})</span>
    </div>
    <div style="position:relative;margin-bottom:10px">
      <textarea id="msg-text" class="input" rows="4" maxlength="240" placeholder="Type text message to send to MDVR terminal..." style="width:100%;resize:vertical;font-family:inherit"></textarea>
      <div id="msg-counter" style="text-align:right;font-size:.75rem;color:var(--text-dim,#94a3b8);margin-top:2px">0/240</div>
    </div>
    <div style="margin-bottom:12px">
      <div style="font-size:.8rem;font-weight:600;margin-bottom:6px">Delivery Flags (JT/T 808 0x8300):</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.82rem">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="flag-display" checked> Terminal Display (LCD)
        </label>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="flag-tts" checked> Voice Broadcast (TTS)
        </label>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="flag-emergency"> Emergency / Urgent
        </label>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="flag-ad"> Advertisement Screen
        </label>
      </div>
    </div>
    <div>
      <div style="font-size:.8rem;font-weight:600;margin-bottom:4px">Quick Templates:</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">
        ${TEMPLATES.map((t) => `<button class="chip-toggle" type="button" data-tpl="${esc(t)}" style="font-size:.75rem;padding:3px 8px">${esc(t.length > 32 ? t.slice(0, 30) + '…' : t)}</button>`).join("")}
      </div>
    </div>`;

  modal({
    title: "Send Text Message",
    bodyHtml,
    actions: [
      { label: "Cancel", onClick: closeModal },
      {
        label: "Send Message",
        variant: "primary",
        onClick: async () => {
          const txtEl = qs("#msg-text");
          const text = txtEl ? txtEl.value.trim() : "";
          if (!text) {
            toast("Please enter a message.", "warn");
            return;
          }

          // Compute bitmask:
          // bit 0 = 1 (emergency)
          // bit 2 = 4 (display)
          // bit 3 = 8 (tts)
          // bit 4 = 16 (ad)
          let flag = 0;
          if (qs("#flag-emergency")?.checked) flag |= 1;
          if (qs("#flag-display")?.checked)   flag |= 4;
          if (qs("#flag-tts")?.checked)       flag |= 8;
          if (qs("#flag-ad")?.checked)        flag |= 16;

          try {
            await post(`/api/devices/${deviceId}/messages`, { text, flag });
            toast("Message dispatched to terminal.", "success");
            closeModal();
          } catch (err) {
            toast(err.message || "Failed to dispatch message.", "error");
          }
        },
      },
    ],
    onMount(el) {
      const txt = qs("#msg-text", el);
      const cnt = qs("#msg-counter", el);
      if (txt && cnt) {
        txt.focus();
        txt.addEventListener("input", () => {
          cnt.textContent = `${txt.value.length}/240`;
        });
      }
      qsa("[data-tpl]", el).forEach((b) => {
        b.addEventListener("click", () => {
          if (txt) {
            txt.value = b.dataset.tpl;
            if (cnt) cnt.textContent = `${txt.value.length}/240`;
            txt.focus();
          }
        });
      });
    },
  });
}
