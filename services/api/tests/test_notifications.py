"""Tests for notification rules router: CRUD, /test, /log, role gating."""
from __future__ import annotations

from conftest import auth, login

from app.security import hash_password
from app.store.base import User


async def _mkuser(store, email, role, org):
    rid = await store.role_id_by_name(role)
    await store.create_user(User(id=0, role_id=rid, role_name=role, email=email,
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))


async def test_create_rule_and_list(ctx):
    """A manage-role user can create a notification rule."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("NOrg", "norg")
    await _mkuser(store, "nmgr@test.local", "fleet_manager", org)
    token = await login(client, "nmgr@test.local", "pwpwpwpw")

    r = await client.post("/api/notifications/rules", headers=auth(token),
                          json={"name": "Speed alerts", "event_types": ["overspeed"],
                                "min_severity": "warning", "channel": "webhook",
                                "target": "https://example.com/hook"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["name"] == "Speed alerts"

    lst = await client.get("/api/notifications/rules", headers=auth(token))
    assert lst.status_code == 200
    assert any(rule["id"] == rid for rule in lst.json()["rules"])


async def test_rule_test_endpoint(ctx, monkeypatch):
    """POST /rules/{id}/test dispatches and returns status."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("NOrg2", "norg2")
    await _mkuser(store, "nmgr2@test.local", "fleet_manager", org)
    token = await login(client, "nmgr2@test.local", "pwpwpwpw")

    r = await client.post("/api/notifications/rules", headers=auth(token),
                          json={"name": "Test rule", "channel": "webhook",
                                "target": "https://example.com/hook"})
    assert r.status_code == 201
    rid = r.json()["id"]

    # Monkeypatch dispatch in router module to avoid a real HTTP call
    import app.routers.notifications as notif_router
    async def fake_dispatch(rule, payload):
        return "delivered", "monkeypatched"
    monkeypatch.setattr(notif_router, "dispatch", fake_dispatch)

    tr = await client.post(f"/api/notifications/rules/{rid}/test", headers=auth(token))
    assert tr.status_code == 200
    assert tr.json()["status"] == "delivered"
    assert tr.json()["detail"] == "monkeypatched"


async def test_notification_log(ctx, monkeypatch):
    """/log returns entries after a test dispatch."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("NOrg3", "norg3")
    await _mkuser(store, "nmgr3@test.local", "fleet_manager", org)
    token = await login(client, "nmgr3@test.local", "pwpwpwpw")

    r = await client.post("/api/notifications/rules", headers=auth(token),
                          json={"name": "Log test", "channel": "webhook",
                                "target": "https://example.com/hook"})
    rid = r.json()["id"]

    import app.routers.notifications as notif_router
    async def fake_dispatch(rule, payload):
        return "delivered", "ok"
    monkeypatch.setattr(notif_router, "dispatch", fake_dispatch)

    await client.post(f"/api/notifications/rules/{rid}/test", headers=auth(token))

    log = await client.get("/api/notifications/log", headers=auth(token))
    assert log.status_code == 200
    assert log.json()["count"] >= 1
    entry = log.json()["entries"][0]
    assert entry["event_type"] == "test_notification"
    assert entry["status"] == "delivered"


async def test_readonly_cannot_create_rule(ctx):
    """A readonly user must not be able to create rules."""
    client, app = ctx
    store = app.state.store
    org = await store.create_organization("NOrg4", "norg4")
    await _mkuser(store, "nro@test.local", "readonly", org)
    token = await login(client, "nro@test.local", "pwpwpwpw")

    r = await client.post("/api/notifications/rules", headers=auth(token),
                          json={"name": "Should fail", "channel": "webhook",
                                "target": "https://example.com/hook"})
    assert r.status_code == 403
