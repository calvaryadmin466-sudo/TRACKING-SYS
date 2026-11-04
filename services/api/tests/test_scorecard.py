from datetime import datetime, timezone

from conftest import auth, login

from app.store.base import Event


async def test_driver_scorecard(ctx):
    client, app = ctx
    store = app.state.store
    dev = await store.inject_device("DEV-SC")
    now = datetime.now(timezone.utc)
    for t, sev in [("overspeed", "alarm"), ("overspeed", "alarm"),
                   ("harsh_braking", "warning"), ("alarm_emergency_sos", "alarm")]:
        await store.save_event(Event(device_id=dev, reporting_id="DEV-SC", type=t, severity=sev, at=now))
    token = await login(client)

    data = (await client.get("/api/reports/driver-scores", headers=auth(token))).json()
    row = next(r for r in data["drivers"] if r["reporting_id"] == "DEV-SC")
    # 100 - (overspeed 4*2 + harsh_braking 3 + alarm 8) = 81
    assert row["score"] == 81
    assert row["grade"] == "B"
    assert row["events"]["overspeed"] == 2
    assert "fleet_average" in data


async def test_scorecard_perfect_when_no_incidents(ctx):
    client, app = ctx
    await app.state.store.inject_device("DEV-CLEAN")
    token = await login(client)
    data = (await client.get("/api/reports/driver-scores", headers=auth(token))).json()
    row = next(r for r in data["drivers"] if r["reporting_id"] == "DEV-CLEAN")
    assert row["score"] == 100 and row["grade"] == "A"
