"""Live position WebSocket.

Clients connect to /api/ws/live?token=<jwt>. On connect the server sends a full
snapshot of the caller's (organization-scoped) devices, then pushes incremental
position updates on a short poll interval. Polling the store keeps this uniform
across the in-memory and PostgreSQL backends and works cross-process (the Go
ingestion writes to the DB, the API reads it) without extra infrastructure.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .deps import principal_from_token_string
from .serialize import device_to_dict, live_to_dict

router = APIRouter()


@router.websocket("/api/ws/live")
async def ws_live(ws: WebSocket):
    settings = ws.app.state.settings
    store = ws.app.state.store

    token = ws.query_params.get("token", "")
    principal = principal_from_token_string(token, settings)
    if not principal:
        await ws.close(code=4401)  # unauthorized
        return
    await ws.accept()

    org = principal.org_scope()
    try:
        # Initial snapshot.
        devices = await store.list_devices(org)
        await ws.send_json({
            "type": "snapshot",
            "devices": [device_to_dict(d, settings) for d in devices],
        })

        # Start just before now so an update that lands during the snapshot is caught.
        since = datetime.now(timezone.utc) - timedelta(seconds=settings.stale_threshold_s)
        while True:
            await asyncio.sleep(max(1, settings.live_poll_s))
            updates = await store.latest_positions(org, since)
            if updates:
                since = max((u.server_time for u in updates if u.server_time), default=since)
                await ws.send_json({
                    "type": "update",
                    "positions": [live_to_dict(u) for u in updates],
                })
    except WebSocketDisconnect:
        return
    except Exception:
        # Never let a single client's error take down the server.
        try:
            await ws.close()
        except Exception:
            pass
