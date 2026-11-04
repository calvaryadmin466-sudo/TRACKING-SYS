"""Convert store records to JSON-serialisable dicts, computing derived status
(online vs offline, fresh vs stale GPS) from configurable thresholds."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from .config import Settings
from .store.base import (
    CameraChannel, DeviceMessage, DeviceStatus, Driver, Event, Geofence, LivePosition, Position, Trip, Vehicle,
    VideoSession,
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _age_seconds(dt: Optional[datetime]) -> Optional[float]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds()


def device_to_dict(d: DeviceStatus, s: Settings) -> dict:
    last_age = _age_seconds(d.last_seen)
    online = last_age is not None and last_age <= s.online_threshold_s
    pos_age = _age_seconds(d.server_time) if d.has_position else None
    fresh = d.has_position and d.valid and pos_age is not None and pos_age <= s.stale_threshold_s
    return {
        "id": d.id,
        "reporting_id": d.reporting_id,
        "serial_number": d.serial_number,
        "model": d.model,
        "manufacturer": d.manufacturer,
        "plate": d.plate,
        "protocol": d.protocol,
        "simulated": d.simulated,
        "active": d.active,
        "organization_id": d.organization_id,
        "vehicle_id": d.vehicle_id,
        "vehicle_registration": d.vehicle_registration,
        "first_seen": _iso(d.first_seen),
        "last_seen": _iso(d.last_seen),
        "last_seen_age_s": last_age,
        "odometer_km": d.mileage_km,
        "online": online,
        "has_position": d.has_position,
        "position": None if not d.has_position else {
            "latitude": d.latitude,
            "longitude": d.longitude,
            "speed": d.speed,
            "heading": d.heading,
            "altitude": d.altitude,
            "acc": d.acc,
            "positioned": d.positioned,
            "valid": d.valid,
            "fresh": fresh,
            "age_s": pos_age,
            "device_time": _iso(d.device_time),
            "server_time": _iso(d.server_time),
        },
    }


def vehicle_to_dict(v: Vehicle) -> dict:
    return {
        "id": v.id,
        "organization_id": v.organization_id,
        "fleet_id": v.fleet_id,
        "registration": v.registration,
        "vehicle_type": v.vehicle_type,
        "driver_name": v.driver_name,
        "driver_id": v.driver_id,
        "created_at": _iso(v.created_at),
    }


def driver_to_dict(d: Driver, today: Optional[date] = None) -> dict:
    today = today or date.today()
    state = "ok"
    days_left = None
    if d.license_expiry:
        exp = d.license_expiry.date() if isinstance(d.license_expiry, datetime) else d.license_expiry
        days_left = (exp - today).days
        if days_left < 0:
            state = "expired"
        elif days_left <= 30:
            state = "expiring_soon"
        else:
            state = "ok"
    return {
        "id": d.id,
        "organization_id": d.organization_id,
        "name": d.name,
        "license_number": d.license_number,
        "license_class": d.license_class,
        "phone": d.phone,
        "employee_id": d.employee_id,
        "license_expiry": d.license_expiry.isoformat() if d.license_expiry else None,
        "license_state": state,
        "days_left": days_left,
        "status": d.status,
        "notes": d.notes,
        "assigned_vehicle": d.assigned_vehicle or "",
        "created_at": _iso(d.created_at),
    }


def position_to_dict(p: Position) -> dict:
    return {
        "device_id": p.device_id,
        "reporting_id": p.reporting_id,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "speed": p.speed,
        "heading": p.heading,
        "altitude": p.altitude,
        "acc": p.acc,
        "positioned": p.positioned,
        "valid": p.valid,
        "satellites": p.satellites,
        "simulated": p.simulated,
        "device_time": _iso(p.device_time),
        "server_time": _iso(p.server_time),
    }


def event_to_dict(e: Event) -> dict:
    return {
        "id": e.id,
        "device_id": e.device_id,
        "reporting_id": e.reporting_id,
        "type": e.type,
        "severity": e.severity,
        "detail": e.detail,
        "value": e.value,
        "at": _iso(e.at),
        "latitude": e.latitude,
        "longitude": e.longitude,
        "acknowledged": e.acknowledged,
        "acknowledged_by": e.acknowledged_by,
        "acknowledged_at": _iso(e.acknowledged_at),
        "resolved": e.resolved,
        "resolved_at": _iso(e.resolved_at),
    }


def user_to_dict(u) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role_name,
        "role_id": u.role_id,
        "organization_id": u.organization_id,
        "is_active": u.is_active,
        "created_at": _iso(u.created_at),
        "last_login_at": _iso(u.last_login_at),
    }


def audit_to_dict(a) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "action": a.action,
        "entity": a.entity,
        "entity_id": a.entity_id,
        "detail": a.detail,
        "at": _iso(a.at),
    }


def packet_to_dict(p) -> dict:
    return {
        "id": p.id,
        "reporting_id": p.reporting_id,
        "received_at": _iso(p.received_at),
        "length": p.length,
        "message_name": p.message_name,
        "decoded": p.decoded,
        "checksum_ok": p.checksum_ok,
        "hex": p.hex,
        "ascii": p.ascii,
        "note": p.note,
    }


def geofence_to_dict(g: Geofence) -> dict:
    return {
        "id": g.id,
        "organization_id": g.organization_id,
        "name": g.name,
        "ring": [[lat, lon] for (lat, lon) in g.ring],
    }


def trip_to_dict(t: Trip, with_path: bool = False) -> dict:
    d = {
        "id": t.id,
        "device_id": t.device_id,
        "reporting_id": t.reporting_id,
        "started_at": _iso(t.started_at),
        "ended_at": _iso(t.ended_at),
        "distance_km": t.distance_km,
        "max_speed": t.max_speed,
        "point_count": len(t.path),
    }
    if with_path:
        d["path"] = [[lat, lon] for (lat, lon) in t.path]
    return d


def camera_to_dict(c: CameraChannel) -> dict:
    return {"device_id": c.device_id, "channel_no": c.channel_no, "name": c.name, "enabled": c.enabled}


def video_session_to_dict(v: VideoSession) -> dict:
    return {
        "id": v.id,
        "device_id": v.device_id,
        "reporting_id": v.reporting_id,
        "channel": v.channel,
        "kind": v.kind,
        "status": v.status,
        "started_at": _iso(v.started_at),
        "ended_at": _iso(v.ended_at),
        "video_host": v.video_host,
        "video_tcp_port": v.video_tcp_port,
        "detail": v.detail,
    }


def maintenance_to_dict(m) -> dict:
    return {
        "id": m.id,
        "device_id": m.device_id,
        "device_label": m.device_label,
        "title": m.title,
        "kind": m.kind,
        "due_date": _iso(m.due_date),
        "due_odometer_km": m.due_odometer_km,
        "odometer_at_create": m.odometer_at_create,
        "status": m.status,
        "completed_at": _iso(m.completed_at),
        "notes": m.notes,
        "created_at": _iso(m.created_at),
    }


def rule_to_dict(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "organization_id": r.organization_id,
        "event_types": list(r.event_types or []),
        "min_severity": r.min_severity,
        "channel": r.channel,
        "target": r.target,
        "active": r.active,
        "created_at": _iso(r.created_at),
    }


def notification_to_dict(n) -> dict:
    return {
        "id": n.id, "rule_id": n.rule_id, "event_id": n.event_id, "event_type": n.event_type,
        "channel": n.channel, "target": n.target, "status": n.status, "detail": n.detail,
        "at": _iso(n.at),
    }


def live_to_dict(p: LivePosition) -> dict:
    return {
        "device_id": p.device_id,
        "reporting_id": p.reporting_id,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "speed": p.speed,
        "heading": p.heading,
        "acc": p.acc,
        "valid": p.valid,
        "device_time": _iso(p.device_time),
        "server_time": _iso(p.server_time),
    }


def device_message_to_dict(m: DeviceMessage) -> dict:
    return {
        "id": m.id,
        "organization_id": m.organization_id,
        "device_id": m.device_id,
        "reporting_id": m.reporting_id,
        "user_id": m.user_id,
        "user_email": m.user_email,
        "flag": m.flag,
        "text": m.text,
        "status": m.status,
        "detail": m.detail,
        "created_at": _iso(m.created_at),
    }
