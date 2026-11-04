import pytest

from conftest import login

from app.config import DEFAULT_JWT_SECRET


async def test_security_headers_present(ctx):
    client, _ = ctx
    r = await client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in r.headers.get("Content-Security-Policy", "")
    # CSP must still allow the dashboard's real deps.
    csp = r.headers["Content-Security-Policy"]
    assert "cdnjs.cloudflare.com" in csp
    assert "tile.openstreetmap.org" in csp


async def test_login_rate_limited(ctx):
    client, app = ctx
    limit = app.state.settings.login_max_attempts
    last = None
    for _ in range(limit + 2):
        last = await client.post("/api/auth/login",
                                 json={"email": "admin@test.local", "password": "wrong"})
    assert last.status_code == 429
    assert "Retry-After" in last.headers


async def test_successful_login_still_works_within_limit(ctx):
    client, _ = ctx
    token = await login(client)
    assert token


def test_production_refuses_default_secret(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DEMO_FEED", "false")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", DEFAULT_JWT_SECRET)
    from app.main import create_app
    with pytest.raises(RuntimeError):
        create_app()
