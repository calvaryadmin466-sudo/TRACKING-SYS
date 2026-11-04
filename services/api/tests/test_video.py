from conftest import auth, login

from app.control_client import ControlError
from app.security import hash_password
from app.store.base import User


class FakeControl:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def stream_start(self, rid, channel, data_type=1, stream_type=0):
        self.calls.append(("start", rid, channel))
        if self.fail:
            raise ControlError("device not connected")
        return {"ok": True, "video_host": "203.0.113.9", "video_tcp_port": 7078}

    async def stream_stop(self, rid, channel):
        self.calls.append(("stop", rid, channel))
        return {"ok": True}

    async def playback(self, rid, channel, start_time, end_time):
        return {"ok": True, "video_host": "203.0.113.9", "video_tcp_port": 7078}

    async def query_video_resources(self, rid, channel=0, start_time="", end_time="",
                                    alarm_type=0, media_type=0, stream_type=0, storage_type=0):
        self.calls.append(("query", rid, channel, start_time, end_time))
        if self.fail:
            raise ControlError("device not connected")
        return {"ok": True, "reporting_id": rid, "resources": [
            {"channel": channel or 1, "start_time": start_time, "end_time": end_time, "file_size": 10485760}
        ]}

    async def streams(self):
        return [{"sim": "100000000001", "channel": 1, "packets": 42, "video_frames": 40, "key_frames": 3}]


async def test_cameras_default_eight_channels(ctx):
    client, app = ctx
    dev = await app.state.store.inject_device("DEV-V")
    token = await login(client)
    r = await client.get(f"/api/devices/{dev}/cameras", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()["channels"]) == 8


async def test_start_live_dispatches_command(ctx):
    client, app = ctx
    app.state.control = FakeControl()
    dev = await app.state.store.inject_device("DEV-V")
    token = await login(client)
    r = await client.post(f"/api/devices/{dev}/video/live", headers=auth(token),
                          json={"channel": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["status"] == "active"
    assert body["session"]["video_host"] == "203.0.113.9"
    assert ("start", "DEV-V", 1) in app.state.control.calls


async def test_start_live_failure_records_failed_session(ctx):
    client, app = ctx
    app.state.control = FakeControl(fail=True)
    dev = await app.state.store.inject_device("DEV-V")
    token = await login(client)
    r = await client.post(f"/api/devices/{dev}/video/live", headers=auth(token),
                          json={"channel": 2})
    assert r.status_code == 502
    sessions = (await client.get("/api/video/sessions", headers=auth(token))).json()["sessions"]
    assert any(s["status"] == "failed" for s in sessions)


async def test_video_streams_proxies_gateway(ctx):
    client, app = ctx
    app.state.control = FakeControl()
    token = await login(client)
    r = await client.get("/api/video/streams", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["streams"][0]["packets"] == 42


async def test_readonly_cannot_start_video(ctx):
    client, app = ctx
    app.state.control = FakeControl()
    store = app.state.store
    org = await store.create_organization("A", "a")
    rid = await store.role_id_by_name("readonly")
    await store.create_user(User(id=0, role_id=rid, role_name="readonly", email="ro@test.local",
                                 password_hash=hash_password("pwpwpwpw"), is_active=True,
                                 organization_id=org))
    dev = await store.inject_device("DEV-V", organization_id=org)
    token = await login(client, "ro@test.local", "pwpwpwpw")
    r = await client.post(f"/api/devices/{dev}/video/live", headers=auth(token), json={"channel": 1})
    assert r.status_code == 403


async def test_query_video_dispatches_command(ctx):
    client, app = ctx
    app.state.control = FakeControl()
    dev = await app.state.store.inject_device("DEV-V-Q1")
    token = await login(client)
    payload = {
        "channel": 1,
        "start_time": "261104000000",
        "end_time": "261104235959",
        "alarm_type": 0,
        "media_type": 0,
        "stream_type": 0,
        "storage_type": 1,
    }
    r = await client.post(f"/api/devices/{dev}/video/query", headers=auth(token), json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispatched"] is True
    assert body["reporting_id"] == "DEV-V-Q1"
    assert len(body["resources"]) == 1
    assert ("query", "DEV-V-Q1", 1, "261104000000", "261104235959") in app.state.control.calls


async def test_query_video_failure(ctx):
    client, app = ctx
    app.state.control = FakeControl(fail=True)
    dev = await app.state.store.inject_device("DEV-V-Q2")
    token = await login(client)
    payload = {
        "channel": 0,
        "start_time": "261104000000",
        "end_time": "261104235959",
    }
    r = await client.post(f"/api/devices/{dev}/video/query", headers=auth(token), json=payload)
    assert r.status_code == 502
    assert "not connected" in r.text


async def test_query_video_validation(ctx):
    client, app = ctx
    dev = await app.state.store.inject_device("DEV-V-Q3")
    token = await login(client)
    # start_time too short
    r = await client.post(f"/api/devices/{dev}/video/query", headers=auth(token), json={
        "start_time": "123", "end_time": "261104235959"
    })
    assert r.status_code == 422

