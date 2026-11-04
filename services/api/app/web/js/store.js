// Shared application state and the live WebSocket manager.
// One WebSocket for the whole app (no duplicates); auto-reconnect with backoff;
// derives a connection state of connecting | live | stale | down.
import { getToken } from "./api.js";

export const session = { user: null };

class LiveFeed {
  constructor() {
    this.ws = null;
    this.devices = new Map();     // id -> device object (status + latest position)
    this.listeners = new Set();   // fn({type, devices, connState})
    this.connState = "down";      // connecting | live | stale | down
    this.lastMsgAt = 0;
    this.retry = 0;
    this._wantOpen = false;
    this._staleTimer = null;
    this._reconnectTimer = null;
  }

  subscribe(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit(type) { for (const fn of this.listeners) { try { fn({ type, devices: this.list(), connState: this.connState }); } catch {} } }
  list() { return [...this.devices.values()]; }
  get(id) { return this.devices.get(id); }

  _setState(s) { if (this.connState !== s) { this.connState = s; this._emit("state"); } }

  connect() {
    this._wantOpen = true;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this._setState("connecting");
    let ws;
    try { ws = new WebSocket(`${proto}://${location.host}/api/ws/live?token=${encodeURIComponent(getToken())}`); }
    catch { this._scheduleReconnect(); return; }
    this.ws = ws;
    ws.onopen = () => { this.retry = 0; this.lastMsgAt = Date.now(); this._setState("live"); this._startStaleCheck(); };
    ws.onmessage = (ev) => {
      this.lastMsgAt = Date.now();
      if (this.connState !== "live") this._setState("live");
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "snapshot") {
        this.devices.clear();
        for (const d of msg.devices) this.devices.set(d.id, d);
        this._emit("snapshot");
      } else if (msg.type === "update") {
        for (const u of msg.positions) {
          const d = this.devices.get(u.device_id);
          if (!d) continue;
          d.position = Object.assign(d.position || {}, {
            latitude: u.latitude, longitude: u.longitude, speed: u.speed,
            heading: u.heading, acc: u.acc, valid: u.valid, fresh: true,
          });
          d.has_position = true; d.online = true; d.last_seen_age_s = 0;
        }
        this._emit("update");
      }
    };
    ws.onclose = () => { this._stopStaleCheck(); if (this._wantOpen) { this._setState("down"); this._scheduleReconnect(); } };
    ws.onerror = () => { try { ws.close(); } catch {} };
  }

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    const delay = Math.min(15000, 1000 * Math.pow(2, this.retry++));
    this._reconnectTimer = setTimeout(() => { if (this._wantOpen) this.connect(); }, delay);
  }
  _startStaleCheck() {
    this._stopStaleCheck();
    this._staleTimer = setInterval(() => {
      if (this.connState === "live" && Date.now() - this.lastMsgAt > 12000) this._setState("stale");
    }, 4000);
  }
  _stopStaleCheck() { if (this._staleTimer) { clearInterval(this._staleTimer); this._staleTimer = null; } }

  close() {
    this._wantOpen = false;
    clearTimeout(this._reconnectTimer);
    this._stopStaleCheck();
    if (this.ws) { try { this.ws.close(); } catch {} this.ws = null; }
    this.devices.clear();
    this._setState("down");
  }
}

export const live = new LiveFeed();
