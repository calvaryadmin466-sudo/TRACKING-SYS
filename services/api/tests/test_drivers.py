"""Tests for driver management: CRUD, org isolation, license state, vehicle assignment, scorecard attribution."""
from datetime import date, timedelta

from conftest import auth, login

from app.security import hash_password
from app.store.base import Driver, User, Vehicle


async def _mkuser(store, email, role, org):
    rid = await store.role_id_by_name(role)
    await store.create_user(User(id=0, role_id=rid, role_name=role, email=email,
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))


async def test_driver_crud_and_org_isolation(ctx):
    """Manage-role user can create/update/delete; org-isolation is enforced; readonly cannot mutate."""
    client, app = ctx
    store = app.state.store

    org_a = await store.create_organization("OrgA", "orga")
    org_b = await store.create_organization("OrgB", "orgb")

    await _mkuser(store, "mgr_a@test.local", "fleet_manager", org_a)
    await _mkuser(store, "mgr_b@test.local", "fleet_manager", org_b)
    await _mkuser(store, "ro_a@test.local", "readonly", org_a)

    tok_a = await login(client, "mgr_a@test.local", "pwpwpwpw")
    tok_b = await login(client, "mgr_b@test.local", "pwpwpwpw")
    tok_ro = await login(client, "ro_a@test.local", "pwpwpwpw")

    # 1. Readonly cannot create
    ro_res = await client.post("/api/drivers", headers=auth(tok_ro), json={"name": "No Access"})
    assert ro_res.status_code == 403

    # 2. Manager A creates driver
    r = await client.post("/api/drivers", headers=auth(tok_a), json={
        "name": "Alice Driver",
        "license_number": "DL-12345",
        "license_class": "C",
        "phone": "+1234567890",
        "employee_id": "EMP-001",
        "notes": "Primary tanker driver",
    })
    assert r.status_code == 201, r.text
    dr_id = r.json()["id"]
    assert r.json()["name"] == "Alice Driver"
    assert r.json()["license_number"] == "DL-12345"

    # 3. Manager A lists drivers -> sees Alice
    lst_a = await client.get("/api/drivers", headers=auth(tok_a))
    assert lst_a.status_code == 200
    ids_a = [d["id"] for d in lst_a.json()["drivers"]]
    assert dr_id in ids_a

    # 4. Manager B lists drivers -> does NOT see Alice (org isolation)
    lst_b = await client.get("/api/drivers", headers=auth(tok_b))
    assert lst_b.status_code == 200
    ids_b = [d["id"] for d in lst_b.json()["drivers"]]
    assert dr_id not in ids_b

    # 5. Manager B cannot update or delete Alice
    put_b = await client.put(f"/api/drivers/{dr_id}", headers=auth(tok_b), json={"name": "Hacked"})
    assert put_b.status_code == 403
    del_b = await client.delete(f"/api/drivers/{dr_id}", headers=auth(tok_b))
    assert del_b.status_code == 403

    # 6. Readonly cannot update or delete Alice
    put_ro = await client.put(f"/api/drivers/{dr_id}", headers=auth(tok_ro), json={"name": "Readonly Edit"})
    assert put_ro.status_code == 403
    del_ro = await client.delete(f"/api/drivers/{dr_id}", headers=auth(tok_ro))
    assert del_ro.status_code == 403

    # 7. Manager A updates Alice
    put_a = await client.put(f"/api/drivers/{dr_id}", headers=auth(tok_a), json={
        "name": "Alice Senior Driver",
        "license_number": "DL-12345-REV",
        "license_class": "CE",
        "phone": "+1234567890",
        "employee_id": "EMP-001",
        "status": "active",
        "notes": "Promoted",
    })
    assert put_a.status_code == 200
    assert put_a.json()["name"] == "Alice Senior Driver"
    assert put_a.json()["license_class"] == "CE"

    # 8. Manager A deletes Alice
    del_a = await client.delete(f"/api/drivers/{dr_id}", headers=auth(tok_a))
    assert del_a.status_code == 204

    # Verify deleted
    lst_after = await client.get("/api/drivers", headers=auth(tok_a))
    assert all(d["id"] != dr_id for d in lst_after.json()["drivers"])


async def test_license_state_computation(ctx):
    """Driver serialization correctly flags expired, expiring_soon (within 30 days), and ok."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("OrgLic", "orglic")
    await _mkuser(store, "mgr_lic@test.local", "fleet_manager", org)
    token = await login(client, "mgr_lic@test.local", "pwpwpwpw")

    today = date.today()
    past_date = (today - timedelta(days=5)).isoformat()
    soon_date = (today + timedelta(days=15)).isoformat()
    future_date = (today + timedelta(days=90)).isoformat()

    r_exp = await client.post("/api/drivers", headers=auth(token), json={
        "name": "Expired Driver", "license_expiry": past_date
    })
    assert r_exp.status_code == 201
    assert r_exp.json()["license_state"] == "expired"

    r_soon = await client.post("/api/drivers", headers=auth(token), json={
        "name": "Soon Driver", "license_expiry": soon_date
    })
    assert r_soon.status_code == 201
    assert r_soon.json()["license_state"] == "expiring_soon"

    r_ok = await client.post("/api/drivers", headers=auth(token), json={
        "name": "Valid Driver", "license_expiry": future_date
    })
    assert r_ok.status_code == 201
    assert r_ok.json()["license_state"] == "ok"

    # Check list returns the same computed states
    lst = await client.get("/api/drivers", headers=auth(token))
    dmap = {d["name"]: d["license_state"] for d in lst.json()["drivers"]}
    assert dmap["Expired Driver"] == "expired"
    assert dmap["Soon Driver"] == "expiring_soon"
    assert dmap["Valid Driver"] == "ok"


async def test_assign_driver_to_vehicle(ctx):
    """Assigning a driver to a vehicle reflects in assigned_vehicle and vehicle.driver_id."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("OrgAssign", "orgassign")
    await _mkuser(store, "mgr_as@test.local", "fleet_manager", org)
    token = await login(client, "mgr_as@test.local", "pwpwpwpw")

    # Create driver
    r_dr = await client.post("/api/drivers", headers=auth(token), json={"name": "Bob Driver"})
    dr_id = r_dr.json()["id"]

    # Create vehicle
    v_id = await store.create_vehicle(Vehicle(
        id=0, registration="TRUCK-99", organization_id=org, vehicle_type="Truck"
    ))

    # Assign driver to vehicle
    r_as = await client.post(f"/api/drivers/{dr_id}/assign", headers=auth(token), json={"vehicle_id": v_id})
    assert r_as.status_code == 200
    assert r_as.json()["assigned_vehicle"] == "TRUCK-99"

    # Verify vehicle record updated with driver_id
    v = await store.get_vehicle(v_id)
    assert v.driver_id == dr_id

    # Verify driver list reflects assigned vehicle
    lst = await client.get("/api/drivers", headers=auth(token))
    dr_record = next(d for d in lst.json()["drivers"] if d["id"] == dr_id)
    assert dr_record["assigned_vehicle"] == "TRUCK-99"

    # Unassign
    r_un = await client.post(f"/api/drivers/{dr_id}/assign", headers=auth(token), json={"vehicle_id": None})
    assert r_un.status_code == 200
    assert r_un.json()["assigned_vehicle"] == ""

    v_after = await store.get_vehicle(v_id)
    assert v_after.driver_id is None


async def test_driver_scores_shows_driver_name(ctx):
    """Scorecard endpoint /api/reports/driver-scores attributes the assigned driver's name."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("OrgSC", "orgsc")
    await _mkuser(store, "mgr_sc@test.local", "fleet_manager", org)
    token = await login(client, "mgr_sc@test.local", "pwpwpwpw")

    # Driver
    dr = Driver(id=0, organization_id=org, name="Carlos Sainz", license_number="CS-55")
    dr_id = await store.create_driver(dr)

    # Vehicle
    v_id = await store.create_vehicle(Vehicle(
        id=0, registration="RACE-55", organization_id=org, driver_id=dr_id, driver_name="Carlos Sainz"
    ))

    # Device assigned to vehicle
    dev_id = await store.inject_device("DEV-55", organization_id=org)
    # Assign vehicle to device via patch
    patch_res = await client.patch(f"/api/devices/{dev_id}", headers=auth(token), json={"vehicle_id": v_id})
    assert patch_res.status_code == 200

    # Call driver scores
    res = await client.get("/api/reports/driver-scores", headers=auth(token))
    assert res.status_code == 200
    drivers = res.json()["drivers"]
    row = next(r for r in drivers if r["device_id"] == dev_id)
    assert row["driver_name"] == "Carlos Sainz"
