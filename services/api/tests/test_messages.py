"""Tests for JT/T 808 0x8300 text message distribution endpoints."""
from __future__ import annotations

import pytest

from conftest import auth, login

from app.control_client import ControlClient, ControlError
from app.security import hash_password
from app.store.base import User


async def test_send_message_success(ctx, monkeypatch):
    client, app = ctx
    store = app.state.store
    dev_id = await store.inject_device("DEV-MSG-1")
    token = await login(client)

    sent_calls = []

    async def fake_send(self, reporting_id: str, flag: int, text: str):
        sent_calls.append((reporting_id, flag, text))
        return {"ok": True, "reporting_id": reporting_id}

    monkeypatch.setattr(ControlClient, "send_text_message", fake_send)

    r = await client.post(
        f"/api/devices/{dev_id}/messages",
        headers=auth(token),
        json={"text": "Please return to base", "flag": 12},
    )
    assert r.status_code == 201
    body = r.json()
    assert "message" in body
    msg = body["message"]
    assert msg["text"] == "Please return to base"
    assert msg["flag"] == 12
    assert msg["status"] == "sent"
    assert msg["device_id"] == dev_id
    assert msg["reporting_id"] == "DEV-MSG-1"

    assert len(sent_calls) == 1
    assert sent_calls[0] == ("DEV-MSG-1", 12, "Please return to base")


async def test_send_message_control_error(ctx, monkeypatch):
    client, app = ctx
    store = app.state.store
    dev_id = await store.inject_device("DEV-MSG-2")
    token = await login(client)

    async def fake_fail(self, reporting_id: str, flag: int, text: str):
        raise ControlError("device DEV-MSG-2 not connected")

    monkeypatch.setattr(ControlClient, "send_text_message", fake_fail)

    r = await client.post(
        f"/api/devices/{dev_id}/messages",
        headers=auth(token),
        json={"text": "Check your status", "flag": 4},
    )
    assert r.status_code == 502
    assert "not connected" in r.text

    # The failed attempt should be recorded in store
    history = await store.list_device_messages(org_id=None, device_id=dev_id)
    assert len(history) == 1
    assert history[0].status == "failed"
    assert "not connected" in history[0].detail


async def test_send_message_validation(ctx):
    client, app = ctx
    store = app.state.store
    dev_id = await store.inject_device("DEV-MSG-3")
    token = await login(client)

    # Empty text
    r = await client.post(f"/api/devices/{dev_id}/messages", headers=auth(token), json={"text": "", "flag": 12})
    assert r.status_code == 422

    # Over 240 chars
    long_text = "a" * 241
    r2 = await client.post(f"/api/devices/{dev_id}/messages", headers=auth(token), json={"text": long_text, "flag": 12})
    assert r2.status_code == 422

    # Invalid flag
    r3 = await client.post(f"/api/devices/{dev_id}/messages", headers=auth(token), json={"text": "hello", "flag": 999})
    assert r3.status_code == 422


async def test_send_message_org_isolation(ctx):
    client, app = ctx
    store = app.state.store

    org_a = await store.create_organization("Org A", "org-a")
    org_b = await store.create_organization("Org B", "org-b")

    rid = await store.role_id_by_name("dispatcher")
    await store.create_user(User(
        id=0, role_id=rid, role_name="dispatcher", email="disp_b@test.local",
        password_hash=hash_password("pwB12345"), is_active=True,
        organization_id=org_b,
    ))

    dev_a = await store.inject_device("DEV-IN-A", organization_id=org_a)

    token_b = await login(client, "disp_b@test.local", "pwB12345")
    r = await client.post(
        f"/api/devices/{dev_a}/messages",
        headers=auth(token_b),
        json={"text": "cross-org message", "flag": 12},
    )
    assert r.status_code == 403


async def test_send_message_missing_device(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.post("/api/devices/99999/messages", headers=auth(token), json={"text": "hello", "flag": 12})
    assert r.status_code == 404


async def test_readonly_user_forbidden(ctx):
    client, app = ctx
    store = app.state.store
    org_id = await store.create_organization("Org R", "org-r")
    rid = await store.role_id_by_name("readonly")
    await store.create_user(User(
        id=0, role_id=rid, role_name="readonly", email="ro@test.local",
        password_hash=hash_password("ro123456"), is_active=True,
        organization_id=org_id,
    ))
    dev = await store.inject_device("DEV-RO", organization_id=org_id)

    token = await login(client, "ro@test.local", "ro123456")
    r = await client.post(f"/api/devices/{dev}/messages", headers=auth(token), json={"text": "hello", "flag": 12})
    assert r.status_code == 403


async def test_list_device_messages(ctx, monkeypatch):
    client, app = ctx
    store = app.state.store
    dev_id = await store.inject_device("DEV-MSG-LIST")
    token = await login(client)

    async def fake_send(self, reporting_id: str, flag: int, text: str):
        return {"ok": True}

    monkeypatch.setattr(ControlClient, "send_text_message", fake_send)

    await client.post(f"/api/devices/{dev_id}/messages", headers=auth(token), json={"text": "Message 1", "flag": 4})
    await client.post(f"/api/devices/{dev_id}/messages", headers=auth(token), json={"text": "Message 2", "flag": 8})

    r = await client.get(f"/api/devices/{dev_id}/messages", headers=auth(token))
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["text"] == "Message 2"
    assert msgs[1]["text"] == "Message 1"

    r_all = await client.get("/api/messages", headers=auth(token))
    assert r_all.status_code == 200
    assert len(r_all.json()["messages"]) >= 2
