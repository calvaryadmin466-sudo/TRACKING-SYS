"""Labelled simulated device feed, used ONLY in in-memory dev mode so the
dashboard and live WebSocket can be exercised without a database or hardware.

Every device created here is flagged simulated=True and uses a 'SIM-' reporting
id prefix. This never runs in production (Postgres) mode. It is the API-side
equivalent of the Go `cmd/simulator`, which exercises the real ingestion path.
"""
from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timezone
from typing import Optional

from .store.base import Position
from .store.memory import MemoryStore


async def run_demo_feed(store: MemoryStore, org_id: Optional[int], *,
                        count: int = 8, interval_s: float = 2.0) -> None:
    # Spread simulated vehicles around Kolkata as a recognisable demo area.
    base_lat, base_lon = 22.5726, 88.3639
    vehicles = []
    for i in range(count):
        rid = f"SIM-{100001 + i}"
        did = await store.inject_device(
            rid, serial=f"SIMSN{i:03d}", model="XV-900-8-SIM",
            plate=f"WB-{i:02d}-SIM-{1000 + i}", simulated=True, organization_id=org_id)
        vehicles.append({
            "id": did, "rid": rid,
            "lat": base_lat + random.uniform(-0.05, 0.05),
            "lon": base_lon + random.uniform(-0.05, 0.05),
            "hdg": random.uniform(0, 360),
            "acc": True,
        })

    while True:
        now = datetime.now(timezone.utc)
        for v in vehicles:
            # Random-walk heading and step; occasionally stop (ignition behaviour).
            v["hdg"] = (v["hdg"] + random.uniform(-25, 25)) % 360
            moving = random.random() > 0.2
            if not moving:
                speed = 0.0
                # When stopped, often switch ignition off (ends a trip, emits events).
                v["acc"] = random.random() < 0.4
            elif random.random() < 0.15:
                speed = random.uniform(85, 110)   # occasional overspeed burst
                v["acc"] = True
            else:
                speed = random.uniform(20, 70)
                v["acc"] = True
            step = (speed / 3600.0) * interval_s / 111.0  # ~deg per tick
            v["lat"] += step * math.cos(math.radians(v["hdg"]))
            v["lon"] += step * math.sin(math.radians(v["hdg"]))
            await store.add_position(Position(
                device_id=v["id"], reporting_id=v["rid"],
                latitude=round(v["lat"], 6), longitude=round(v["lon"], 6),
                speed=round(speed, 1), heading=int(v["hdg"]), altitude=12,
                acc=v["acc"], positioned=True, valid=True, satellites=11,
                simulated=True, device_time=now, server_time=now,
            ))
        await asyncio.sleep(interval_s)
