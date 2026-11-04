"""In-memory Store for development and tests (no database required).

In memory mode there is no Go ingestion process writing to a shared database, so
this store also exposes helpers (`inject_device`, `add_position`) used only by the
clearly-labelled demo feed to simulate device movement for UI verification.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from .base import (
    AuditEntry, CameraChannel, DevicePatch, DeviceStatus, Event, Geofence, LivePosition,
    MaintenanceItem, NotificationLogEntry, NotificationRule, Organization, Position,
    RawPacketView, Role, Store, Trip, User, Vehicle, VideoSession,
)

DEFAULT_ROLES = [
    "super_admin", "company_admin", "fleet_manager", "dispatcher", "operator", "readonly",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryStore(Store):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._users_by_email: dict[str, User] = {}
        self._users_by_id: dict[int, User] = {}
        self._orgs: dict[int, str] = {}
        self._vehicles: dict[int, Vehicle] = {}
        self._devices: dict[int, DeviceStatus] = {}
        self._positions: list[Position] = []
        self._audit: list[AuditEntry] = []
        self._events: list[Event] = []
        self._geofences: dict[int, Geofence] = {}
        self._trips: dict[int, Trip] = {}
        self._video: dict[int, VideoSession] = {}
        self._maintenance: dict[int, MaintenanceItem] = {}
        self._rules: dict[int, NotificationRule] = {}
        self._notifications: list[NotificationLogEntry] = []
        self._roles = {name: i + 1 for i, name in enumerate(DEFAULT_ROLES)}
        self._seq = {"user": 0, "org": 0, "vehicle": 0, "device": 0,
                     "event": 0, "geofence": 0, "trip": 0, "video": 0,
                     "maint": 0, "rule": 0, "notif": 0}

    def _next(self, key: str) -> int:
        self._seq[key] += 1
        return self._seq[key]

    # --- auth & tenancy ---
    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with self._lock:
            return self._users_by_email.get(email.lower())

    async def create_user(self, u: User) -> int:
        async with self._lock:
            u.id = self._next("user")
            u.created_at = u.created_at or _utcnow()
            for name, rid in self._roles.items():
                if rid == u.role_id:
                    u.role_name = name
            self._users_by_email[u.email.lower()] = u
            self._users_by_id[u.id] = u
            return u.id

    async def update_user_last_login(self, user_id: int, at: datetime) -> None:
        async with self._lock:
            u = self._users_by_id.get(user_id)
            if u:
                u.last_login_at = at

    async def count_users(self) -> int:
        async with self._lock:
            return len(self._users_by_id)

    async def create_organization(self, name: str, slug: str) -> int:
        async with self._lock:
            oid = self._next("org")
            self._orgs[oid] = name
            return oid

    async def role_id_by_name(self, name: str) -> Optional[int]:
        return self._roles.get(name)

    # --- devices ---
    def _latest_position(self, device_id: int) -> Optional[Position]:
        best: Optional[Position] = None
        for p in self._positions:
            if p.device_id != device_id:
                continue
            if best is None or (p.server_time or _utcnow()) > (best.server_time or _utcnow()):
                best = p
        return best

    def _apply_latest(self, d: DeviceStatus) -> DeviceStatus:
        if d.vehicle_id and d.vehicle_id in self._vehicles:
            d.vehicle_registration = self._vehicles[d.vehicle_id].registration
        p = self._latest_position(d.id)
        if p:
            d.has_position = True
            d.latitude, d.longitude, d.speed = p.latitude, p.longitude, p.speed
            d.heading, d.altitude = p.heading, p.altitude
            d.acc, d.positioned, d.valid = p.acc, p.positioned, p.valid
            d.mileage_km = p.mileage_km
            d.device_time, d.server_time = p.device_time, p.server_time
            d.last_seen = p.server_time
        return d

    async def list_devices(self, org_id: Optional[int]) -> list[DeviceStatus]:
        async with self._lock:
            out = []
            for d in self._devices.values():
                if org_id is not None and d.organization_id != org_id:
                    continue
                out.append(self._apply_latest(d))
            return sorted(out, key=lambda x: x.id)

    async def get_device(self, device_id: int) -> Optional[DeviceStatus]:
        async with self._lock:
            d = self._devices.get(device_id)
            return self._apply_latest(d) if d else None

    async def update_device(self, device_id: int, patch: DevicePatch) -> None:
        async with self._lock:
            d = self._devices.get(device_id)
            if not d:
                return
            if patch.vehicle_id is not None:
                d.vehicle_id = patch.vehicle_id
            if patch.organization_id is not None:
                d.organization_id = patch.organization_id
            if patch.active is not None:
                d.active = patch.active
            if patch.plate is not None:
                d.plate = patch.plate

    # --- vehicles ---
    async def list_vehicles(self, org_id: Optional[int]) -> list[Vehicle]:
        async with self._lock:
            out = [v for v in self._vehicles.values()
                   if org_id is None or v.organization_id == org_id]
            return sorted(out, key=lambda x: x.id)

    async def get_vehicle(self, vehicle_id: int) -> Optional[Vehicle]:
        async with self._lock:
            return self._vehicles.get(vehicle_id)

    async def create_vehicle(self, v: Vehicle) -> int:
        async with self._lock:
            v.id = self._next("vehicle")
            v.created_at = v.created_at or _utcnow()
            self._vehicles[v.id] = v
            return v.id

    async def update_vehicle(self, v: Vehicle) -> None:
        async with self._lock:
            existing = self._vehicles.get(v.id)
            if existing:
                v.created_at = existing.created_at
                if v.organization_id is None:
                    v.organization_id = existing.organization_id
                self._vehicles[v.id] = v

    # --- positions ---
    async def list_positions(self, device_id, frm, to, limit) -> list[Position]:
        async with self._lock:
            out = []
            for p in self._positions:
                if p.device_id != device_id:
                    continue
                ts = p.device_time or p.server_time
                if frm and ts and ts < frm:
                    continue
                if to and ts and ts > to:
                    continue
                out.append(p)
            out.sort(key=lambda x: x.server_time or _utcnow())
            if limit and len(out) > limit:
                out = out[-limit:]
            return out

    async def latest_positions(self, org_id, since) -> list[LivePosition]:
        async with self._lock:
            latest: dict[int, Position] = {}
            for p in self._positions:
                if not p.server_time or p.server_time <= since:
                    continue
                cur = latest.get(p.device_id)
                if cur is None or p.server_time > cur.server_time:
                    latest[p.device_id] = p
            out = []
            for p in latest.values():
                if org_id is not None:
                    d = self._devices.get(p.device_id)
                    if not d or d.organization_id != org_id:
                        continue
                out.append(LivePosition(
                    device_id=p.device_id, reporting_id=p.reporting_id,
                    latitude=p.latitude, longitude=p.longitude, speed=p.speed,
                    heading=p.heading, acc=p.acc, valid=p.valid,
                    device_time=p.device_time, server_time=p.server_time,
                ))
            return sorted(out, key=lambda x: x.device_id)

    # --- audit ---
    async def save_audit(self, entry: AuditEntry) -> None:
        async with self._lock:
            entry.at = entry.at or _utcnow()
            self._audit.append(entry)

    # --- Stage 3: events, geofences, trips ---
    async def positions_since(self, since, org_id) -> list[Position]:
        async with self._lock:
            out = []
            for p in self._positions:
                if not p.server_time or p.server_time <= since:
                    continue
                if org_id is not None:
                    d = self._devices.get(p.device_id)
                    if not d or d.organization_id != org_id:
                        continue
                out.append(p)
            out.sort(key=lambda x: x.server_time or _utcnow())
            return out

    async def save_event(self, e: Event) -> int:
        async with self._lock:
            self._seq["event"] += 1
            e.id = self._seq["event"]
            e.at = e.at or _utcnow()
            self._events.append(e)
            return e.id

    async def list_events(self, org_id, device_id, since, types, limit) -> list[Event]:
        async with self._lock:
            dev_ids = None
            if org_id is not None:
                dev_ids = {d.id for d in self._devices.values() if d.organization_id == org_id}
            out = []
            for e in self._events:
                if device_id is not None and e.device_id != device_id:
                    continue
                if dev_ids is not None and e.device_id not in dev_ids:
                    continue
                if since and e.at and e.at <= since:
                    continue
                if types and e.type not in types:
                    continue
                out.append(e)
            out.sort(key=lambda x: (x.at or _utcnow()), reverse=True)
            return out[:limit] if limit else out

    async def create_geofence(self, g: Geofence) -> int:
        async with self._lock:
            self._seq["geofence"] += 1
            g.id = self._seq["geofence"]
            self._geofences[g.id] = g
            return g.id

    async def list_geofences(self, org_id) -> list[Geofence]:
        async with self._lock:
            return [g for g in self._geofences.values()
                    if org_id is None or g.organization_id == org_id or g.organization_id is None]

    async def get_geofence(self, gid) -> Optional[Geofence]:
        async with self._lock:
            return self._geofences.get(gid)

    async def delete_geofence(self, gid) -> None:
        async with self._lock:
            self._geofences.pop(gid, None)

    async def save_trip(self, t: Trip) -> int:
        async with self._lock:
            self._seq["trip"] += 1
            t.id = self._seq["trip"]
            self._trips[t.id] = t
            return t.id

    async def list_trips(self, device_id, limit) -> list[Trip]:
        async with self._lock:
            out = [t for t in self._trips.values() if t.device_id == device_id]
            out.sort(key=lambda x: x.started_at, reverse=True)
            return out[:limit] if limit else out

    async def get_trip(self, tid) -> Optional[Trip]:
        async with self._lock:
            return self._trips.get(tid)

    # --- Stage 4: video ---
    async def list_camera_channels(self, device_id) -> list[CameraChannel]:
        async with self._lock:
            d = self._devices.get(device_id)
        # The XV-900-8 is an 8-channel MDVR; default to 8 channels until a real
        # device reports its actual channel set.
        n = 8
        return [CameraChannel(device_id=device_id, channel_no=i, name=f"CH{i}") for i in range(1, n + 1)] if d else []

    async def create_video_session(self, v: VideoSession) -> int:
        async with self._lock:
            self._seq["video"] += 1
            v.id = self._seq["video"]
            v.started_at = v.started_at or _utcnow()
            self._video[v.id] = v
            return v.id

    async def list_video_sessions(self, org_id, device_id, limit) -> list[VideoSession]:
        async with self._lock:
            dev_ids = None
            if org_id is not None:
                dev_ids = {d.id for d in self._devices.values() if d.organization_id == org_id}
            out = []
            for v in self._video.values():
                if device_id is not None and v.device_id != device_id:
                    continue
                if dev_ids is not None and v.device_id not in dev_ids:
                    continue
                out.append(v)
            out.sort(key=lambda x: x.started_at or _utcnow(), reverse=True)
            return out[:limit] if limit else out

    async def get_video_session(self, sid) -> Optional[VideoSession]:
        async with self._lock:
            return self._video.get(sid)

    async def end_video_session(self, sid, status) -> None:
        async with self._lock:
            v = self._video.get(sid)
            if v:
                v.status = status
                v.ended_at = _utcnow()

    # --- Redesign: event ack/resolve, admin, audit, diagnostics ---
    async def get_event(self, eid) -> Optional[Event]:
        async with self._lock:
            for e in self._events:
                if e.id == eid:
                    return e
            return None

    async def ack_event(self, eid, user_id) -> None:
        async with self._lock:
            for e in self._events:
                if e.id == eid:
                    e.acknowledged = True
                    e.acknowledged_by = user_id
                    e.acknowledged_at = _utcnow()

    async def resolve_event(self, eid) -> None:
        async with self._lock:
            for e in self._events:
                if e.id == eid:
                    e.resolved = True
                    e.resolved_at = _utcnow()

    async def list_users(self, org_id) -> list[User]:
        async with self._lock:
            out = [u for u in self._users_by_id.values()
                   if org_id is None or u.organization_id == org_id]
            return sorted(out, key=lambda x: x.id)

    async def list_roles(self) -> list[Role]:
        return [Role(id=rid, name=name) for name, rid in sorted(self._roles.items(), key=lambda kv: kv[1])]

    async def list_organizations(self) -> list[Organization]:
        async with self._lock:
            return [Organization(id=i, name=n) for i, n in sorted(self._orgs.items())]

    async def list_audit(self, org_id, limit) -> list[AuditEntry]:
        async with self._lock:
            # Org scoping for audit: entries by users in the org (super admin: all).
            allowed = None
            if org_id is not None:
                allowed = {u.id for u in self._users_by_id.values() if u.organization_id == org_id}
            out = []
            for i, a in enumerate(self._audit):
                if allowed is not None and a.user_id not in allowed:
                    continue
                a.id = a.id or (i + 1)
                out.append(a)
            out.sort(key=lambda x: x.at or _utcnow(), reverse=True)
            return out[:limit] if limit else out

    async def list_raw_packets(self, reporting_id, limit) -> list[RawPacketView]:
        # In memory mode the API has no ingestion raw-packet store (that lives in
        # the Go ingestion process / PostgreSQL). Return empty.
        return []

    # --- Fleet ops: maintenance, rules, notifications ---
    def _device_label(self, device_id):
        d = self._devices.get(device_id)
        if not d:
            return ""
        return d.vehicle_registration or d.plate or d.reporting_id

    async def create_maintenance(self, m: MaintenanceItem) -> int:
        async with self._lock:
            self._seq["maint"] += 1
            m.id = self._seq["maint"]
            m.created_at = m.created_at or _utcnow()
            self._maintenance[m.id] = m
            return m.id

    async def list_maintenance(self, org_id, device_id) -> list[MaintenanceItem]:
        async with self._lock:
            out = []
            for m in self._maintenance.values():
                if org_id is not None and m.organization_id != org_id:
                    continue
                if device_id is not None and m.device_id != device_id:
                    continue
                m.device_label = self._device_label(m.device_id)
                out.append(m)
            out.sort(key=lambda x: (x.status != "open", x.due_date or _utcnow()))
            return out

    async def get_maintenance(self, mid) -> Optional[MaintenanceItem]:
        async with self._lock:
            m = self._maintenance.get(mid)
            if m:
                m.device_label = self._device_label(m.device_id)
            return m

    async def update_maintenance(self, m: MaintenanceItem) -> None:
        async with self._lock:
            if m.id in self._maintenance:
                self._maintenance[m.id] = m

    async def delete_maintenance(self, mid) -> None:
        async with self._lock:
            self._maintenance.pop(mid, None)

    async def create_rule(self, r: NotificationRule) -> int:
        async with self._lock:
            self._seq["rule"] += 1
            r.id = self._seq["rule"]
            r.created_at = r.created_at or _utcnow()
            self._rules[r.id] = r
            return r.id

    async def list_rules(self, org_id) -> list[NotificationRule]:
        async with self._lock:
            out = [r for r in self._rules.values()
                   if org_id is None or r.organization_id == org_id or r.organization_id is None]
            return sorted(out, key=lambda x: x.id)

    async def all_active_rules(self) -> list[NotificationRule]:
        async with self._lock:
            return [r for r in self._rules.values() if r.active]

    async def get_rule(self, rid) -> Optional[NotificationRule]:
        async with self._lock:
            return self._rules.get(rid)

    async def update_rule(self, r: NotificationRule) -> None:
        async with self._lock:
            if r.id in self._rules:
                self._rules[r.id] = r

    async def delete_rule(self, rid) -> None:
        async with self._lock:
            self._rules.pop(rid, None)

    async def save_notification(self, e: NotificationLogEntry) -> None:
        async with self._lock:
            self._seq["notif"] += 1
            e.id = self._seq["notif"]
            e.at = e.at or _utcnow()
            self._notifications.append(e)

    async def list_notifications(self, org_id, limit) -> list[NotificationLogEntry]:
        async with self._lock:
            rule_orgs = {r.id: r.organization_id for r in self._rules.values()}
            out = []
            for n in reversed(self._notifications):
                if org_id is not None and rule_orgs.get(n.rule_id) not in (org_id, None):
                    continue
                out.append(n)
                if limit and len(out) >= limit:
                    break
            return out

    # --- memory-only helpers (used by the labelled demo feed) ---
    async def inject_device(self, reporting_id: str, *, serial: str = "", model: str = "",
                            plate: str = "", simulated: bool = True,
                            organization_id: Optional[int] = None) -> int:
        async with self._lock:
            for d in self._devices.values():
                if d.reporting_id == reporting_id:
                    return d.id
            did = self._next("device")
            self._devices[did] = DeviceStatus(
                id=did, reporting_id=reporting_id, serial_number=serial, model=model,
                plate=plate, simulated=simulated, organization_id=organization_id,
                first_seen=_utcnow(), last_seen=_utcnow(),
            )
            return did

    async def add_position(self, p: Position) -> None:
        async with self._lock:
            p.server_time = p.server_time or _utcnow()
            self._positions.append(p)
