"""Client for the Go ingestion server's internal control API.

The Go ingestion server owns the device TCP sockets, so video-control commands
(0x9101/0x9102/0x9201) are issued by asking it over this internal HTTP API. If the
ingestion server is unreachable, calls raise ControlError and the API surfaces a
clear message rather than pretending a stream started.
"""
from __future__ import annotations

from typing import Optional

import httpx

from .config import Settings


class ControlError(Exception):
    pass


class ControlClient:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.control_url
        self._headers = {}
        if settings.control_token:
            self._headers["Authorization"] = "Bearer " + settings.control_token

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.post(self._base + path, json=payload, headers=self._headers)
        except httpx.HTTPError as e:
            raise ControlError(f"ingestion control API unreachable: {e}") from e
        if r.status_code >= 400:
            raise ControlError(r.json().get("error", r.text) if r.content else r.reason_phrase)
        return r.json()

    async def _get(self, path: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(self._base + path, headers=self._headers)
        except httpx.HTTPError as e:
            raise ControlError(f"ingestion control API unreachable: {e}") from e
        if r.status_code >= 400:
            raise ControlError(r.text)
        return r.json()

    async def stream_start(self, reporting_id: str, channel: int,
                           data_type: int = 1, stream_type: int = 0) -> dict:
        return await self._post(f"/internal/devices/{reporting_id}/stream/start",
                                {"channel": channel, "data_type": data_type, "stream_type": stream_type})

    async def stream_stop(self, reporting_id: str, channel: int) -> dict:
        return await self._post(f"/internal/devices/{reporting_id}/stream/stop", {"channel": channel})

    async def playback(self, reporting_id: str, channel: int, start_time: str, end_time: str) -> dict:
        return await self._post(f"/internal/devices/{reporting_id}/playback",
                                {"channel": channel, "start_time": start_time, "end_time": end_time})

    async def streams(self) -> list[dict]:
        data = await self._get("/internal/video/streams")
        return data.get("streams") or []

    async def device_status(self, reporting_id: str) -> dict:
        return await self._get(f"/internal/devices/{reporting_id}/status")
