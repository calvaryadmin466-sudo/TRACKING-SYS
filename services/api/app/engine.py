"""Event, alarm and trip detection engine.

Pure, backend-agnostic processing: feed it positions (in order) plus the current
geofences and it returns the events to persist and any completed trips. It keeps
per-device state in memory. The same engine is driven by the background runner in
both in-memory and PostgreSQL deployments.

Detected events:
  ignition_on / ignition_off      (ACC transitions)
  overspeed / overspeed_cleared   (speed vs configured limit)
  harsh_acceleration / harsh_braking
  gps_signal_loss / gps_restored
  geofence_enter / geofence_exit
  device_offline / device_online  (via periodic sweep)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .geo import haversine_m, point_in_ring
from .store.base import Event, Geofence, Position, Trip


@dataclass
class EngineConfig:
    speed_limit_kmh: float = 80.0
    harsh_accel_ms2: float = 3.5
    trip_idle_gap_s: float = 300.0
    min_trip_distance_m: float = 200.0
    offline_threshold_s: float = 120.0
    max_accel_dt_s: float = 60.0  # ignore accel over long gaps (stale data)


@dataclass
class _TripAcc:
    started_at: datetime
    path: list = field(default_factory=list)
    distance_m: float = 0.0
    max_speed: float = 0.0
    last_move_at: Optional[datetime] = None
    last_at: Optional[datetime] = None


@dataclass
class _DevState:
    acc: Optional[bool] = None
    positioned: Optional[bool] = None
    speed: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    at: Optional[datetime] = None
    overspeeding: bool = False
    inside: set = field(default_factory=set)
    online: Optional[bool] = None
    trip: Optional[_TripAcc] = None


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pt(pos: Position) -> datetime:
    return _aware(pos.server_time) or _aware(pos.device_time) or datetime.now(timezone.utc)


class EventEngine:
    def __init__(self, cfg: Optional[EngineConfig] = None) -> None:
        self.cfg = cfg or EngineConfig()
        self._state: dict[int, _DevState] = {}

    def _st(self, device_id: int) -> _DevState:
        st = self._state.get(device_id)
        if st is None:
            st = _DevState()
            self._state[device_id] = st
        return st

    def process_position(self, pos: Position,
                         geofences: list[Geofence]) -> tuple[list[Event], Optional[Trip]]:
        cfg = self.cfg
        st = self._st(pos.device_id)
        now = _pt(pos)
        events: list[Event] = []
        finished: Optional[Trip] = None

        def ev(type_: str, severity: str, detail: str = "", value: float | None = None):
            events.append(Event(device_id=pos.device_id, reporting_id=pos.reporting_id,
                                type=type_, severity=severity, detail=detail, value=value, at=now,
                                latitude=pos.latitude, longitude=pos.longitude))

        # Ignition (ACC) transitions.
        if st.acc is not None and pos.acc != st.acc:
            ev("ignition_on" if pos.acc else "ignition_off", "info")

        # Overspeed (edge-triggered to avoid a flood).
        if pos.speed > cfg.speed_limit_kmh and not st.overspeeding:
            st.overspeeding = True
            ev("overspeed", "alarm", f"{pos.speed:.0f} km/h > {cfg.speed_limit_kmh:.0f}", pos.speed)
        elif pos.speed <= cfg.speed_limit_kmh and st.overspeeding:
            st.overspeeding = False
            ev("overspeed_cleared", "info", f"{pos.speed:.0f} km/h", pos.speed)

        # GPS signal loss / restore.
        if st.positioned is True and not pos.positioned:
            ev("gps_signal_loss", "warning")
        elif st.positioned is False and pos.positioned:
            ev("gps_restored", "info")

        # Harsh acceleration / braking.
        if st.speed is not None and st.at is not None:
            dt = (now - st.at).total_seconds()
            if 0 < dt <= cfg.max_accel_dt_s:
                dv = (pos.speed - st.speed) * (1000.0 / 3600.0)  # m/s
                a = dv / dt
                if a >= cfg.harsh_accel_ms2:
                    ev("harsh_acceleration", "warning", f"{a:.1f} m/s^2", a)
                elif a <= -cfg.harsh_accel_ms2:
                    ev("harsh_braking", "warning", f"{a:.1f} m/s^2", a)

        # Geofences.
        for gf in geofences:
            now_inside = point_in_ring(pos.latitude, pos.longitude, gf.ring)
            was_inside = gf.id in st.inside
            if now_inside and not was_inside:
                st.inside.add(gf.id)
                ev("geofence_enter", "warning", gf.name)
            elif was_inside and not now_inside:
                st.inside.discard(gf.id)
                ev("geofence_exit", "warning", gf.name)

        # Trips.
        finished = self._update_trip(st, pos, now)

        # Update state.
        st.acc, st.positioned, st.speed = pos.acc, pos.positioned, pos.speed
        st.lat, st.lon, st.at = pos.latitude, pos.longitude, now
        st.online = True
        return events, finished

    def _update_trip(self, st: _DevState, pos: Position, now: datetime) -> Optional[Trip]:
        cfg = self.cfg
        moving = pos.speed > 3.0 or pos.acc
        if st.trip is None:
            if moving:
                st.trip = _TripAcc(started_at=now, path=[(pos.latitude, pos.longitude)],
                                   max_speed=pos.speed, last_move_at=now, last_at=now)
            return None

        trip = st.trip
        if st.lat is not None and st.lon is not None:
            trip.distance_m += haversine_m(st.lat, st.lon, pos.latitude, pos.longitude)
        trip.path.append((pos.latitude, pos.longitude))
        trip.max_speed = max(trip.max_speed, pos.speed)
        trip.last_at = now
        if moving:
            trip.last_move_at = now
            return None

        # Idle long enough, or ignition off -> close the trip.
        idle = (now - (trip.last_move_at or now)).total_seconds()
        if idle >= cfg.trip_idle_gap_s or (st.acc is True and not pos.acc):
            return self._finish_trip(st, pos)
        return None

    def _finish_trip(self, st: _DevState, pos: Position) -> Optional[Trip]:
        trip = st.trip
        st.trip = None
        if trip is None or trip.distance_m < self.cfg.min_trip_distance_m:
            return None
        return Trip(id=0, device_id=pos.device_id, reporting_id=pos.reporting_id,
                    started_at=trip.started_at, ended_at=trip.last_at,
                    distance_km=round(trip.distance_m / 1000.0, 3),
                    max_speed=round(trip.max_speed, 1), path=trip.path)

    def sweep_offline(self, devices, now: Optional[datetime] = None) -> list[Event]:
        """Emit device_offline/device_online based on each device's last_seen.

        `devices` is an iterable with .id, .reporting_id and .last_seen.
        """
        now = now or datetime.now(timezone.utc)
        out: list[Event] = []
        for d in devices:
            st = self._st(d.id)
            last = _aware(getattr(d, "last_seen", None))
            online_now = last is not None and (now - last).total_seconds() <= self.cfg.offline_threshold_s
            if st.online is True and not online_now:
                out.append(Event(device_id=d.id, reporting_id=d.reporting_id,
                                 type="device_offline", severity="warning", at=now))
            elif st.online is not True and online_now:
                out.append(Event(device_id=d.id, reporting_id=d.reporting_id,
                                 type="device_online", severity="info", at=now))
            st.online = online_now
        return out
