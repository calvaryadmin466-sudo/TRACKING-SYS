from conftest import auth, login

from app.security import hash_password
from app.store.base import User


async def _mkuser(store, email, role, org):
    rid = await store.role_id_by_name(role)
    await store.create_user(User(id=0, role_id=rid, role_name=role, email=email,
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))


async def test_company_admin_only_sees_own_org(ctx):
    client, app = ctx
    store = app.state.store
    org_a = await store.create_organization("A", "a")
    org_b = await store.create_organization("B", "b")
    await _mkuser(store, "b@test.local", "company_admin", org_b)
    await store.inject_device("DEV-A", organization_id=org_a)
    await store.inject_device("DEV-B", organization_id=org_b)

    token = await login(client, "b@test.local", "pwpwpwpw")
    r = await client.get("/api/devices", headers=auth(token))
    assert r.status_code == 200
    ids = {d["reporting_id"] for d in r.json()["devices"]}
    assert ids == {"DEV-B"}  # must NOT see org A's device


async def test_super_admin_sees_all_orgs(ctx):
    client, app = ctx
    store = app.state.store
    org_a = await store.create_organization("A", "a")
    org_b = await store.create_organization("B", "b")
    await store.inject_device("DEV-A", organization_id=org_a)
    await store.inject_device("DEV-B", organization_id=org_b)

    token = await login(client)  # seeded super admin
    r = await client.get("/api/devices", headers=auth(token))
    ids = {d["reporting_id"] for d in r.json()["devices"]}
    assert {"DEV-A", "DEV-B"} <= ids


async def test_cross_org_device_access_forbidden(ctx):
    client, app = ctx
    store = app.state.store
    org_a = await store.create_organization("A", "a")
    org_b = await store.create_organization("B", "b")
    await _mkuser(store, "b@test.local", "company_admin", org_b)
    dev_a = await store.inject_device("DEV-A", organization_id=org_a)

    token = await login(client, "b@test.local", "pwpwpwpw")
    r = await client.get(f"/api/devices/{dev_a}", headers=auth(token))
    assert r.status_code == 403


async def test_readonly_cannot_modify(ctx):
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("A", "a")
    await _mkuser(store, "ro@test.local", "readonly", org)
    dev = await store.inject_device("DEV-A", organization_id=org)

    token = await login(client, "ro@test.local", "pwpwpwpw")
    r = await client.patch(f"/api/devices/{dev}", headers=auth(token), json={"active": False})
    assert r.status_code == 403
