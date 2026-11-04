"""Tests for maintenance endpoints: CRUD, due_state computation, role gating."""
from datetime import datetime, timedelta, timezone

from conftest import auth, login

from app.security import hash_password
from app.store.base import User


async def _mkuser(store, email, role, org):
    rid = await store.role_id_by_name(role)
    await store.create_user(User(id=0, role_id=rid, role_name=role, email=email,
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))


async def test_create_and_list_maintenance(ctx):
    """Manage-role user can create; list returns due_state."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("A", "a")
    dev = await store.inject_device("DEV-M1", organization_id=org)
    await _mkuser(store, "mgr@test.local", "fleet_manager", org)
    token = await login(client, "mgr@test.local", "pwpwpwpw")

    # Due in the past → overdue
    past = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    r = await client.post("/api/maintenance", headers=auth(token),
                          json={"device_id": dev, "title": "Oil change", "kind": "service",
                                "due_date": past})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert r.json()["title"] == "Oil change"

    # List and check due_state
    lst = await client.get("/api/maintenance", headers=auth(token))
    assert lst.status_code == 200
    items = lst.json()["items"]
    match = [i for i in items if i["id"] == mid]
    assert len(match) == 1
    assert match[0]["due_state"] == "overdue"


async def test_due_soon_within_seven_days(ctx):
    """An item due within 7 days should have due_state = due_soon."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("B", "b")
    dev = await store.inject_device("DEV-M2", organization_id=org)
    await _mkuser(store, "mgr2@test.local", "fleet_manager", org)
    token = await login(client, "mgr2@test.local", "pwpwpwpw")

    soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = await client.post("/api/maintenance", headers=auth(token),
                          json={"device_id": dev, "title": "Tyre check", "due_date": soon})
    assert r.status_code == 201

    lst = await client.get("/api/maintenance", headers=auth(token))
    item = [i for i in lst.json()["items"] if i["title"] == "Tyre check"][0]
    assert item["due_state"] == "due_soon"


async def test_complete_and_delete(ctx):
    """Complete sets status to done; delete removes the item."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("C", "c")
    dev = await store.inject_device("DEV-M3", organization_id=org)
    await _mkuser(store, "mgr3@test.local", "fleet_manager", org)
    token = await login(client, "mgr3@test.local", "pwpwpwpw")

    r = await client.post("/api/maintenance", headers=auth(token),
                          json={"device_id": dev, "title": "Brake pads"})
    assert r.status_code == 201
    mid = r.json()["id"]

    # Complete
    cr = await client.post(f"/api/maintenance/{mid}/complete", headers=auth(token))
    assert cr.status_code == 200
    assert cr.json()["status"] == "done"

    # Verify due_state is "done" in list
    lst = await client.get("/api/maintenance", headers=auth(token))
    match = [i for i in lst.json()["items"] if i["id"] == mid]
    assert match[0]["due_state"] == "done"

    # Delete
    dr = await client.delete(f"/api/maintenance/{mid}", headers=auth(token))
    assert dr.status_code == 204

    lst2 = await client.get("/api/maintenance", headers=auth(token))
    assert all(i["id"] != mid for i in lst2.json()["items"])


async def test_readonly_cannot_create_maintenance(ctx):
    """A readonly user must not be able to create maintenance items."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("D", "d")
    dev = await store.inject_device("DEV-M4", organization_id=org)
    await _mkuser(store, "ro@test.local", "readonly", org)
    token = await login(client, "ro@test.local", "pwpwpwpw")

    r = await client.post("/api/maintenance", headers=auth(token),
                          json={"device_id": dev, "title": "Should fail"})
    assert r.status_code == 403
