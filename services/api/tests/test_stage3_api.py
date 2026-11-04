from datetime import datetime, timezone

from conftest import auth, login

from app.store.base import Event, Trip


async def test_geofence_crud(ctx):
    client, _ = ctx
    token = await login(client)
    ring = [[22.55, 88.35], [22.55, 88.42], [22.62, 88.42], [22.62, 88.35]]
    r = await client.post("/api/geofences", headers=auth(token),
                          json={"name": "Zone A", "ring": ring})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    assert len(r.json()["ring"]) >= 3

    lst = await client.get("/api/geofences", headers=auth(token))
    assert any(g["id"] == gid for g in lst.json()["geofences"])

    d = await client.delete(f"/api/geofences/{gid}", headers=auth(token))
    assert d.status_code == 204
    lst2 = await client.get("/api/geofences", headers=auth(token))
    assert all(g["id"] != gid for g in lst2.json()["geofences"])


async def test_geofence_requires_three_points(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.post("/api/geofences", headers=auth(token),
                          json={"name": "bad", "ring": [[1, 1], [2, 2]]})
    assert r.status_code == 422  # pydantic min_length


async def test_events_list_and_filter(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-E")
    now = datetime.now(timezone.utc)
    await store.save_event(Event(device_id=dev, reporting_id="DEV-E", type="overspeed",
                                 severity="alarm", detail="101 km/h", value=101, at=now))
    await store.save_event(Event(device_id=dev, reporting_id="DEV-E", type="ignition_on",
                                 severity="info", at=now))
    token = await login(client)

    allr = await client.get("/api/events", headers=auth(token))
    assert allr.json()["count"] == 2

    filtered = await client.get("/api/events", headers=auth(token), params={"types": "overspeed"})
    body = filtered.json()
    assert body["count"] == 1
    assert body["events"][0]["type"] == "overspeed"
    assert body["events"][0]["severity"] == "alarm"


async def test_trips_list_and_detail(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-T")
    now = datetime.now(timezone.utc)
    tid = await store.save_trip(Trip(id=0, device_id=dev, reporting_id="DEV-T",
                                     started_at=now, ended_at=now, distance_km=3.2,
                                     max_speed=58.0, path=[(22.5, 88.3), (22.51, 88.31)]))
    token = await login(client)

    lst = await client.get(f"/api/devices/{dev}/trips", headers=auth(token))
    assert lst.json()["count"] == 1
    assert lst.json()["trips"][0]["distance_km"] == 3.2

    detail = await client.get(f"/api/trips/{tid}", headers=auth(token))
    assert detail.status_code == 200
    assert len(detail.json()["path"]) == 2
