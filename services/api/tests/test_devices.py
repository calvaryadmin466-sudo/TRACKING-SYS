from datetime import datetime, timedelta, timezone

from conftest import auth, login

from app.store.base import Position


def _now():
    return datetime.now(timezone.utc)


async def test_list_summary_and_status(ctx):
    client, app = ctx
    store = app.state.store
    # One fresh/online moving device.
    d1 = await store.inject_device("DEV-FRESH")
    await store.add_position(Position(device_id=d1, reporting_id="DEV-FRESH",
                                      latitude=22.57, longitude=88.36, speed=40,
                                      acc=True, positioned=True, valid=True,
                                      device_time=_now(), server_time=_now()))
    # One stale/offline device (old position).
    d2 = await store.inject_device("DEV-STALE")
    old = _now() - timedelta(hours=2)
    await store.add_position(Position(device_id=d2, reporting_id="DEV-STALE",
                                      latitude=22.50, longitude=88.30, speed=0,
                                      acc=False, positioned=True, valid=True,
                                      device_time=old, server_time=old))

    token = await login(client)
    r = await client.get("/api/devices", headers=auth(token))
    body = r.json()
    assert body["summary"]["total"] == 2
    assert body["summary"]["online"] == 1
    assert body["summary"]["moving"] == 1
    assert body["summary"]["offline"] == 1

    by_id = {d["reporting_id"]: d for d in body["devices"]}
    assert by_id["DEV-FRESH"]["online"] is True
    assert by_id["DEV-FRESH"]["position"]["fresh"] is True
    assert by_id["DEV-STALE"]["online"] is False
    assert by_id["DEV-STALE"]["position"]["fresh"] is False


async def test_assign_vehicle_to_device(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-X")
    token = await login(client)

    v = (await client.post("/api/vehicles", headers=auth(token),
                           json={"registration": "WB-01-AB-1234"})).json()
    r = await client.patch(f"/api/devices/{dev}", headers=auth(token),
                           json={"vehicle_id": v["id"]})
    assert r.status_code == 200
    assert r.json()["vehicle_id"] == v["id"]
    assert r.json()["vehicle_registration"] == "WB-01-AB-1234"


async def test_get_missing_device_404(ctx):
    client, _ = ctx
    token = await login(client)
    assert (await client.get("/api/devices/999999", headers=auth(token))).status_code == 404
