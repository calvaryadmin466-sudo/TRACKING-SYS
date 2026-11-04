"""Convert store records to JSON-serialisable dicts, computing derived status
(online vs offline, fresh vs stale GPS) from configurable thresholds."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .config import Settings
from .store.base import (
    CameraChannel, DeviceStatus, Event, Geofence, LivePosition, Position, Trip, Vehicle,
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
        "created_at": _iso(v.created_at),
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
