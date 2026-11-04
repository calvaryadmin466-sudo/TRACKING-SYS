"""Pure unit tests for the event/trip engine (no store, no network)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.engine import EngineConfig, EventEngine
from app.store.base import Geofence, Position

T0 = datetime(2026, 11, 3, 8, 0, 0, tzinfo=timezone.utc)


def pos(device_id=1, lat=22.5, lon=88.3, speed=0.0, acc=True, positioned=True, t=0):
    ts = T0 + timedelta(seconds=t)
    return Position(device_id=device_id, reporting_id="DEV-1", latitude=lat, longitude=lon,
                    speed=speed, acc=acc, positioned=positioned, valid=positioned,
                    device_time=ts, server_time=ts)


def types_of(events):
    return [e.type for e in events]


def test_overspeed_edge_triggered():
    eng = EventEngine(EngineConfig(speed_limit_kmh=80))
    eng.process_position(pos(speed=50, t=0), [])                 # baseline
    ev1, _ = eng.process_position(pos(speed=100, t=10), [])
    ev2, _ = eng.process_position(pos(speed=105, t=20), [])      # still over -> no new alarm
    ev3, _ = eng.process_position(pos(speed=40, t=30), [])       # back under
    assert "overspeed" in types_of(ev1)
    assert "overspeed" not in types_of(ev2)
    assert "overspeed_cleared" in types_of(ev3)


def test_ignition_transitions():
    eng = EventEngine()
    eng.process_position(pos(acc=False, t=0), [])
    on, _ = eng.process_position(pos(acc=True, t=5), [])
    off, _ = eng.process_position(pos(acc=False, t=10), [])
    assert "ignition_on" in types_of(on)
    assert "ignition_off" in types_of(off)


def test_harsh_acceleration():
    eng = EventEngine(EngineConfig(harsh_accel_ms2=3.5))
    eng.process_position(pos(speed=0, t=0), [])
    ev, _ = eng.process_position(pos(speed=40, t=2), [])  # 40km/h in 2s ~= 5.5 m/s^2
    assert "harsh_acceleration" in types_of(ev)


def test_harsh_braking():
    eng = EventEngine(EngineConfig(harsh_accel_ms2=3.5))
    eng.process_position(pos(speed=60, t=0), [])
    ev, _ = eng.process_position(pos(speed=10, t=2), [])
    assert "harsh_braking" in types_of(ev)


def test_gps_loss_and_restore():
    eng = EventEngine()
    eng.process_position(pos(positioned=True, t=0), [])
    loss, _ = eng.process_position(pos(positioned=False, t=5), [])
    restore, _ = eng.process_position(pos(positioned=True, t=10), [])
    assert "gps_signal_loss" in types_of(loss)
    assert "gps_restored" in types_of(restore)


def test_geofence_enter_exit():
    gf = Geofence(id=1, organization_id=None, name="Zone",
                  ring=[(-1, -1), (-1, 1), (1, 1), (1, -1)])
    eng = EventEngine()
    out1, _ = eng.process_position(pos(lat=5, lon=5, t=0), [gf])   # outside
    enter, _ = eng.process_position(pos(lat=0, lon=0, t=5), [gf])  # inside
    stay, _ = eng.process_position(pos(lat=0.1, lon=0.1, t=10), [gf])
    exit_, _ = eng.process_position(pos(lat=5, lon=5, t=15), [gf])
    assert "geofence_enter" not in types_of(out1)
    assert "geofence_enter" in types_of(enter)
    assert "geofence_enter" not in types_of(stay) and "geofence_exit" not in types_of(stay)
    assert "geofence_exit" in types_of(exit_)


def test_trip_detection():
    eng = EventEngine(EngineConfig(min_trip_distance_m=100))
    # Start moving.
    _, t0 = eng.process_position(pos(lat=22.50, lon=88.30, speed=40, acc=True, t=0), [])
    _, t1 = eng.process_position(pos(lat=22.51, lon=88.31, speed=45, acc=True, t=60), [])
    # Ignition off -> trip closes.
    _, trip = eng.process_position(pos(lat=22.51, lon=88.31, speed=0, acc=False, t=120), [])
    assert t0 is None and t1 is None
    assert trip is not None
    assert trip.distance_km > 0.1
    assert len(trip.path) == 3
    assert trip.max_speed == 45


def test_offline_sweep():
    eng = EventEngine(EngineConfig(offline_threshold_s=120))
    now = T0 + timedelta(minutes=10)
    fresh = SimpleNamespace(id=1, reporting_id="DEV-1", last_seen=now - timedelta(seconds=30))
    stale = SimpleNamespace(id=2, reporting_id="DEV-2", last_seen=now - timedelta(minutes=30))
    first = eng.sweep_offline([fresh, stale], now=now)
    # DEV-1 becomes online; DEV-2 starts stale (online was None -> no offline event yet).
    assert any(e.type == "device_online" and e.device_id == 1 for e in first)
    # Now DEV-1 goes stale -> offline event.
    fresh.last_seen = now - timedelta(minutes=30)
    second = eng.sweep_offline([fresh, stale], now=now + timedelta(seconds=1))
    assert any(e.type == "device_offline" and e.device_id == 1 for e in second)
