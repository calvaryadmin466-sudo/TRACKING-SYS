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


async def test_provision_device(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.post("/api/devices", headers=auth(token),
                          json={"device_id": "013800138000", "plate": "T-786EUH",
                                "ip_address": "10.0.0.42", "model": "XV-900-8"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True
    dev = body["device"]
    assert dev["reporting_id"] == "013800138000"
    assert dev["plate"] == "T-786EUH"
    assert dev["ip_address"] == "10.0.0.42"
    assert dev["model"] == "XV-900-8"
    assert dev["simulated"] is False
    lst = (await client.get("/api/devices", headers=auth(token))).json()
    assert any(d["reporting_id"] == "013800138000" for d in lst["devices"])


async def test_reprovision_updates_not_duplicates(ctx):
    client, _ = ctx
    token = await login(client)
    await client.post("/api/devices", headers=auth(token), json={"device_id": "555", "plate": "OLD"})
    r = await client.post("/api/devices", headers=auth(token),
                          json={"device_id": "555", "plate": "NEW", "ip_address": "1.2.3.4"})
    assert r.status_code == 201
    assert r.json()["created"] is False
    assert r.json()["device"]["plate"] == "NEW"
    assert r.json()["device"]["ip_address"] == "1.2.3.4"
    lst = (await client.get("/api/devices", headers=auth(token))).json()
    assert sum(1 for d in lst["devices"] if d["reporting_id"] == "555") == 1


async def test_provision_blank_device_id_rejected(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.post("/api/devices", headers=auth(token), json={"device_id": "   "})
    assert r.status_code == 400


async def test_patch_device_plate_and_ip(ctx):
    client, _ = ctx
    token = await login(client)
    pr = await client.post("/api/devices", headers=auth(token), json={"device_id": "777"})
    did = pr.json()["device"]["id"]
    r = await client.patch(f"/api/devices/{did}", headers=auth(token),
                           json={"ip_address": "192.168.1.9", "plate": "P9"})
    assert r.status_code == 200
    assert r.json()["ip_address"] == "192.168.1.9"
    assert r.json()["plate"] == "P9"


async def test_readonly_cannot_provision(ctx):
    client, app = ctx
    from app.security import hash_password
    from app.store.base import User
    store = app.state.store
    org = await store.create_organization("ProvOrg", "provorg")
    rid = await store.role_id_by_name("readonly")
    await store.create_user(User(id=0, role_id=rid, role_name="readonly", email="ro-prov@test.local",
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))
    token = await login(client, "ro-prov@test.local", "pwpwpwpw")
    r = await client.post("/api/devices", headers=auth(token), json={"device_id": "999"})
    assert r.status_code == 403
