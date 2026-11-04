from datetime import datetime, timezone

from conftest import auth, login

from app.security import hash_password
from app.store.base import Event, Position, Trip, User


async def _mkuser(store, email, role, org):
    rid = await store.role_id_by_name(role)
    await store.create_user(User(id=0, role_id=rid, role_name=role, email=email,
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))


async def test_event_ack_and_resolve(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-EV")
    eid = await store.save_event(Event(device_id=dev, reporting_id="DEV-EV", type="overspeed",
                                       severity="alarm", at=datetime.now(timezone.utc)))
    token = await login(client)

    r = await client.post(f"/api/events/{eid}/ack", headers=auth(token))
    assert r.status_code == 200 and r.json()["acknowledged"] is True
    r2 = await client.post(f"/api/events/{eid}/resolve", headers=auth(token))
    assert r2.status_code == 200 and r2.json()["resolved"] is True


async def test_readonly_cannot_ack(ctx):
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("A", "a")
    await _mkuser(store, "ro@test.local", "readonly", org)
    dev = await store.inject_device("DEV-EV", organization_id=org)
    eid = await store.save_event(Event(device_id=dev, reporting_id="DEV-EV", type="overspeed",
                                       severity="alarm", at=datetime.now(timezone.utc)))
    token = await login(client, "ro@test.local", "pwpwpwpw")
    assert (await client.post(f"/api/events/{eid}/ack", headers=auth(token))).status_code == 403


async def test_roles_and_user_admin(ctx):
    client, app = ctx
    token = await login(client)
    roles = (await client.get("/api/roles", headers=auth(token))).json()["roles"]
    assert any(r["name"] == "dispatcher" for r in roles)

    r = await client.post("/api/users", headers=auth(token),
                          json={"email": "disp@test.local", "password": "secret12345",
                                "role": "dispatcher"})
    assert r.status_code == 201, r.text
    users = (await client.get("/api/users", headers=auth(token))).json()["users"]
    assert any(u["email"] == "disp@test.local" for u in users)


async def test_company_admin_cannot_create_super_admin(ctx):
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("B", "b")
    await _mkuser(store, "ca@test.local", "company_admin", org)
    token = await login(client, "ca@test.local", "pwpwpwpw")
    r = await client.post("/api/users", headers=auth(token),
                          json={"email": "x@test.local", "password": "secret12345",
                                "role": "super_admin"})
    assert r.status_code == 403


async def test_reports_fleet_and_csv(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-R")
    now = datetime.now(timezone.utc)
    await store.save_trip(Trip(id=0, device_id=dev, reporting_id="DEV-R", started_at=now,
                               ended_at=now, distance_km=12.5, max_speed=70, path=[(1, 1), (2, 2)]))
    await store.save_event(Event(device_id=dev, reporting_id="DEV-R", type="overspeed",
                                 severity="alarm", at=now))
    token = await login(client)

    rep = (await client.get("/api/reports/fleet", headers=auth(token))).json()
    assert rep["totals"]["total_distance_km"] >= 12.5
    assert rep["totals"]["total_overspeed_events"] >= 1
    assert "idle_minutes" in rep["unavailable_metrics"]

    csv = await client.get("/api/reports/fleet.csv", headers=auth(token))
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    assert "reporting_id" in csv.text


async def test_device_packets_empty_in_memory(ctx):
    client, app = ctx
    dev = await app.state.store.inject_device("DEV-P")
    token = await login(client)
    r = await client.get(f"/api/devices/{dev}/packets", headers=auth(token))
    assert r.status_code == 200 and r.json()["count"] == 0
