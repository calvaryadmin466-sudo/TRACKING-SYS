"""Tests for speed-graded track playback: geo_playback utilities + API endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth, login

from app.geo_playback import build_speed_segments, detect_stops, speed_tier
from app.store.base import Position


# ---------------------------------------------------------------------------
# speed_tier() unit tests
# ---------------------------------------------------------------------------

def test_speed_tier_boundaries():
    # Exact boundary values
    assert speed_tier(0.0) == "L"
    assert speed_tier(40.0) == "L"
    assert speed_tier(40.1) == "M"
    assert speed_tier(80.0) == "M"
    assert speed_tier(80.1) == "H"
    assert speed_tier(120.0) == "H"
    assert speed_tier(120.1) == "S"
    assert speed_tier(200.0) == "S"


def test_speed_tier_negative_treated_as_low():
    # Negative (invalid) speed is still classified L
    assert speed_tier(-1.0) == "L"


# ---------------------------------------------------------------------------
# detect_stops() unit tests
# ---------------------------------------------------------------------------

def _make_points(entries: list[tuple[float, float, float, datetime]]) -> list[dict]:
    """Build point dicts from (lat, lon, speed_kmh, dt) tuples."""
    return [
        {"latitude": lat, "longitude": lon, "speed": spd, "device_time": dt.isoformat()}
        for lat, lon, spd, dt in entries
    ]


def test_detect_stops_empty():
    assert detect_stops([]) == []


def test_detect_stops_no_stop_when_too_short():
    """Points stopped for only 100 s should NOT produce a stop (min=300)."""
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    pts = _make_points([
        (22.5, 88.3, 0.0, base),
        (22.5, 88.3, 0.5, base + timedelta(seconds=50)),
        (22.5, 88.3, 0.0, base + timedelta(seconds=100)),
        (22.5, 88.3, 20.0, base + timedelta(seconds=101)),  # moving again
    ])
    assert detect_stops(pts, min_stop_s=300) == []


def test_detect_stops_basic_detection():
    """Stopped for 400 s → one stop detected."""
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    pts = _make_points([
        (22.5, 88.3, 30.0, base),
        (22.5, 88.3, 0.0,  base + timedelta(seconds=10)),   # stop starts
        (22.5, 88.3, 0.5,  base + timedelta(seconds=200)),
        (22.5, 88.3, 1.0,  base + timedelta(seconds=410)),  # stop ends (400 s)
        (22.5, 88.3, 25.0, base + timedelta(seconds=411)),  # moving
    ])
    stops = detect_stops(pts, min_stop_s=300)
    assert len(stops) == 1
    s = stops[0]
    assert s["duration_s"] >= 300
    assert "latitude" in s
    assert "longitude" in s
    assert "started_at" in s
    assert "ended_at" in s


def test_detect_stops_trailing_stop():
    """A stop at the very end of the trip (no movement afterward) is still detected."""
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    pts = _make_points([
        (22.5, 88.3, 30.0, base),
        (22.5, 88.3, 0.0,  base + timedelta(seconds=10)),
        (22.5, 88.3, 0.0,  base + timedelta(seconds=200)),
        (22.5, 88.3, 0.0,  base + timedelta(seconds=400)),  # trailing stop, 390 s
    ])
    stops = detect_stops(pts, min_stop_s=300)
    assert len(stops) == 1
    assert stops[0]["duration_s"] == 390


def test_detect_stops_speed_threshold():
    """Points at exactly max_speed_kmh (3.0) are considered stopped."""
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    pts = _make_points([
        (22.5, 88.3, 3.0, base),
        (22.5, 88.3, 2.9, base + timedelta(seconds=200)),
        (22.5, 88.3, 3.0, base + timedelta(seconds=400)),  # 400 s at ≤3 km/h
        (22.5, 88.3, 20.0, base + timedelta(seconds=401)),
    ])
    stops = detect_stops(pts, min_stop_s=300, max_speed_kmh=3.0)
    assert len(stops) == 1


def test_detect_stops_multiple():
    """Two distinct stops in a trip."""
    base = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    pts = _make_points([
        (22.5, 88.3, 50.0, base),
        # stop 1: ~350 s
        (22.5, 88.3, 0.0,  base + timedelta(seconds=10)),
        (22.5, 88.3, 0.0,  base + timedelta(seconds=360)),
        (22.5, 88.3, 50.0, base + timedelta(seconds=361)),
        # driving
        (22.6, 88.4, 60.0, base + timedelta(seconds=600)),
        # stop 2: ~400 s
        (22.6, 88.4, 0.0,  base + timedelta(seconds=610)),
        (22.6, 88.4, 0.0,  base + timedelta(seconds=1010)),
        (22.6, 88.4, 50.0, base + timedelta(seconds=1011)),
    ])
    stops = detect_stops(pts, min_stop_s=300)
    assert len(stops) == 2


# ---------------------------------------------------------------------------
# build_speed_segments() unit tests
# ---------------------------------------------------------------------------

def _seg_points(speed_sequence: list[float], base_lat: float = 22.5) -> list[dict]:
    return [
        {"latitude": base_lat + i * 0.001, "longitude": 88.3 + i * 0.001, "speed": s}
        for i, s in enumerate(speed_sequence)
    ]


def test_build_segments_empty_or_single():
    assert build_speed_segments([]) == []
    assert build_speed_segments([{"latitude": 22.5, "longitude": 88.3, "speed": 10.0}]) == []


def test_build_segments_same_tier_merges():
    pts = _seg_points([10.0, 15.0, 20.0, 5.0])  # all L
    segs = build_speed_segments(pts)
    assert len(segs) == 1
    assert segs[0]["tier"] == "L"
    assert len(segs[0]["path"]) == 4


def test_build_segments_tier_change():
    pts = _seg_points([10.0, 10.0, 60.0, 60.0])  # L → M transition
    segs = build_speed_segments(pts)
    assert len(segs) == 2
    assert segs[0]["tier"] == "L"
    assert segs[1]["tier"] == "M"


def test_build_segments_colors_match_tiers():
    pts = _seg_points([10.0, 90.0, 130.0])
    segs = build_speed_segments(pts)
    for seg in segs:
        from app.geo_playback import speed_color
        assert seg["color"] == speed_color(seg["tier"])


def test_build_segments_path_continuity():
    """Adjacent segments share a connecting point for smooth polylines."""
    pts = _seg_points([10.0, 10.0, 60.0, 60.0])
    segs = build_speed_segments(pts)
    # First seg ends where second begins
    assert segs[0]["path"][-1] == segs[1]["path"][0]


# ---------------------------------------------------------------------------
# API endpoint tests: GET /api/devices/{id}/playback
# ---------------------------------------------------------------------------

async def test_playback_returns_segments_stops_summary(ctx):
    """Playback endpoint returns well-structured JSON with all required keys."""
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-PB1")
    token = await login(client)

    base = datetime.now(timezone.utc) - timedelta(hours=1)
    # Seed a mix of speeds to produce at least one segment
    for i in range(5):
        t = base + timedelta(minutes=i * 5)
        spd = [10.0, 15.0, 55.0, 55.0, 10.0][i]
        await store.add_position(Position(
            device_id=dev, reporting_id="DEV-PB1",
            latitude=22.5 + i * 0.01, longitude=88.3 + i * 0.01,
            speed=spd, heading=0, acc=1,
            positioned=True, valid=True,
            device_time=t, server_time=t,
        ))

    r = await client.get(f"/api/devices/{dev}/playback", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert "segments" in body
    assert "stops" in body
    assert "summary" in body
    assert "positions" in body
    summary = body["summary"]
    assert "total_points" in summary
    assert "max_speed_kmh" in summary
    assert "avg_speed_kmh" in summary
    assert "tier_counts" in summary
    assert "stop_count" in summary
    # At least some segments produced from 5 valid points
    assert summary["total_points"] == 5


async def test_playback_404_for_missing_device(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.get("/api/devices/99999/playback", headers=auth(token))
    assert r.status_code == 404


async def test_playback_403_for_wrong_org(ctx):
    """A user from org B cannot access a device from org A."""
    client, app = ctx
    store = app.state.store

    from app.security import hash_password
    from app.store.base import User
    org_a = await store.create_organization("Org A", "org-a")
    org_b = await store.create_organization("Org B", "org-b")
    rid = await store.role_id_by_name("readonly")
    await store.create_user(User(
        id=0, role_id=rid, role_name="readonly", email="readonly_b@test.local",
        password_hash=hash_password("passB123"), is_active=True,
        organization_id=org_b,
    ))

    dev_a = await store.inject_device("DEV-PB-ORG", organization_id=org_a)

    token_b = await login(client, "readonly_b@test.local", "passB123")
    r = await client.get(f"/api/devices/{dev_a}/playback", headers=auth(token_b))
    assert r.status_code == 403


async def test_playback_min_stop_s_param(ctx):
    """The min_stop_s query param filters out short stops."""
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-PB2")
    token = await login(client)

    base = datetime.now(timezone.utc) - timedelta(hours=2)
    # First set: 5-min stop (300 s), then driving
    for i, (spd, offset_s) in enumerate([
        (30.0,  0),
        (0.0,  10),   # stop begins
        (0.0, 310),   # stop ends (300 s)
        (40.0, 311),  # driving
    ]):
        t = base + timedelta(seconds=offset_s)
        await store.add_position(Position(
            device_id=dev, reporting_id="DEV-PB2",
            latitude=22.5, longitude=88.3,
            speed=spd, heading=0, acc=1,
            positioned=True, valid=True,
            device_time=t, server_time=t,
        ))

    # With min_stop_s=600 the 300-s stop should be filtered out
    r = await client.get(f"/api/devices/{dev}/playback?min_stop_s=600", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["stop_count"] == 0
    assert len(body["stops"]) == 0

    # With min_stop_s=300 the stop should appear
    r2 = await client.get(f"/api/devices/{dev}/playback?min_stop_s=300", headers=auth(token))
    body2 = r2.json()
    assert body2["summary"]["stop_count"] >= 1


async def test_playback_requires_auth(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-PB3")
    r = await client.get(f"/api/devices/{dev}/playback")
    assert r.status_code == 401
