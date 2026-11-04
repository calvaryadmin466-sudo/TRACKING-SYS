"""Background runner that drives the event/trip engine over the store.

It polls for new positions (works for both the in-memory store fed by the demo
feed and the PostgreSQL store fed by the Go ingestion server), processes them
through the engine, and persists the resulting events and completed trips. It
also runs a periodic offline/online sweep.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .config import Settings
from .engine import EngineConfig, EventEngine
from .store.base import Store

log = logging.getLogger("engine")


async def run_engine(store: Store, settings: Settings) -> None:
    engine = EventEngine(EngineConfig(
        speed_limit_kmh=settings.speed_limit_kmh,
        harsh_accel_ms2=settings.harsh_accel_ms2,
        trip_idle_gap_s=settings.trip_idle_gap_s,
        min_trip_distance_m=settings.min_trip_distance_m,
        offline_threshold_s=settings.online_threshold_s,
    ))
    # Only process positions that arrive after startup.
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    poll = max(1, settings.engine_poll_s)
    log.info("event engine started (speed_limit=%s km/h, poll=%ss)",
             settings.speed_limit_kmh, poll)

    while True:
        await asyncio.sleep(poll)
        try:
            devices = await store.list_devices(None)
            dev_org = {d.id: d.organization_id for d in devices}
            geofences = await store.list_geofences(None)

            positions = await store.positions_since(since, None)
            for p in positions:
                org = dev_org.get(p.device_id)
                applicable = [g for g in geofences
                              if g.organization_id is None or g.organization_id == org]
                events, trip = engine.process_position(p, applicable)
                for e in events:
                    await store.save_event(e)
                if trip:
                    trip_id = await store.save_trip(trip)
                    log.info("trip stored id=%s device=%s %.2f km",
                             trip_id, trip.device_id, trip.distance_km)
                if p.server_time and p.server_time > since:
                    since = p.server_time

            for e in engine.sweep_offline(devices):
                await store.save_event(e)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the loop alive on transient errors
            log.exception("engine tick failed")
