"""Test fixtures: an in-memory app driven over ASGI in a single event loop so the
store and request handlers share the same loop."""
from __future__ import annotations

import httpx
import pytest_asyncio


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")          # in-memory store
    monkeypatch.setenv("DEMO_FEED", "false")        # deterministic tests
    monkeypatch.setenv("ENGINE_ENABLED", "false")   # no background engine in tests
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpass123")

    from app.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def login(client, email="admin@test.local", password="adminpass123") -> str:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": "Bearer " + token}
