from datetime import datetime, timedelta, timezone

from conftest import auth, login

from app.store.base import Position


async def test_history_returns_sorted_and_filtered(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-H")
    base = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(3):
        t = base + timedelta(minutes=10 * i)
        await store.add_position(Position(device_id=dev, reporting_id="DEV-H",
                                          latitude=22.5 + i * 0.001, longitude=88.3,
                                          speed=10 * i, positioned=True, valid=True,
                                          device_time=t, server_time=t))
    token = await login(client)

    r = await client.get(f"/api/devices/{dev}/history", headers=auth(token))
    body = r.json()
    assert body["count"] == 3
    times = [p["device_time"] for p in body["positions"]]
    assert times == sorted(times)  # ascending

    # Filter from the midpoint onward -> 2 points (params= ensures '+' in the
    # ISO offset is URL-encoded rather than decoded as a space).
    frm = (base + timedelta(minutes=5)).isoformat()
    r2 = await client.get(f"/api/devices/{dev}/history", headers=auth(token),
                          params={"from": frm})
    assert r2.status_code == 200, r2.text
    assert r2.json()["count"] == 2


async def test_history_requires_auth(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-H2")
    assert (await client.get(f"/api/devices/{dev}/history")).status_code == 401
