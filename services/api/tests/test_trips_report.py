"""Tests for /api/reports/trips endpoint — totals from seeded trips."""
from datetime import datetime, timedelta, timezone

from conftest import auth, login

from app.store.base import Trip


async def test_trips_report_totals(ctx):
    """Trips report returns correct totals from seeded trips."""
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-TR1")
    token = await login(client)

    now = datetime.now(timezone.utc)
    # Seed two trips
    await store.save_trip(Trip(
        id=0, device_id=dev, reporting_id="DEV-TR1",
        started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1),
        distance_km=25.5, max_speed=80.0,
        path=[(22.5, 88.3), (22.6, 88.4)],
    ))
    await store.save_trip(Trip(
        id=0, device_id=dev, reporting_id="DEV-TR1",
        started_at=now - timedelta(hours=4), ended_at=now - timedelta(hours=3),
        distance_km=10.0, max_speed=60.0,
        path=[(22.7, 88.5), (22.8, 88.6)],
    ))

    r = await client.get("/api/reports/trips", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    totals = body["totals"]
    assert totals["trips"] == 2
    assert totals["total_distance_km"] == 35.5
    assert totals["avg_distance_km"] == 17.75
    assert totals["longest_trip_km"] == 25.5
    assert len(body["trips"]) == 2


async def test_trips_report_csv(ctx):
    """Trips CSV endpoint returns downloadable CSV."""
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-TR2")
    token = await login(client)

    now = datetime.now(timezone.utc)
    await store.save_trip(Trip(
        id=0, device_id=dev, reporting_id="DEV-TR2",
        started_at=now, ended_at=now, distance_km=5.0, max_speed=45.0,
    ))

    r = await client.get("/api/reports/trips.csv", headers=auth(token))
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "trip_id" in r.text
    assert "DEV-TR2" in r.text


async def test_trips_report_empty(ctx):
    """Trips report works correctly with no trips seeded."""
    client, _ = ctx
    token = await login(client)

    r = await client.get("/api/reports/trips", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["trips"] == 0
    assert body["totals"]["total_distance_km"] == 0
    assert len(body["trips"]) == 0
