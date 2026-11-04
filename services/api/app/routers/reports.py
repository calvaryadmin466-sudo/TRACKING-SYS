"""Reports & analytics, aggregated from real stored trips/events/positions.
Metrics that the data model cannot support are returned as null and labelled
unavailable by the frontend — never invented.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..config import Settings
from ..deps import current_principal, get_settings, get_store
from ..rbac import Principal
from ..store.base import Store


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid timestamp: {ts}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age_s(dt, now):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds()


router = APIRouter(prefix="/api/reports", tags=["reports"])


async def _build(store: Store, settings: Settings, principal: Principal,
                 frm: Optional[datetime], to: Optional[datetime]):
    now = datetime.now(timezone.utc)
    devices = await store.list_devices(principal.org_scope())
    rows = []
    for d in devices:
        trips = await store.list_trips(d.id, 1000)
        trips = [t for t in trips if _in_range(t.started_at, frm, to)]
        distance = round(sum(t.distance_km for t in trips), 2)
        max_speed = round(max([t.max_speed for t in trips], default=0.0), 1)
        events = await store.list_events(principal.org_scope(), d.id, frm, None, 5000)
        if to:
            events = [e for e in events if e.at and e.at <= to]
        overspeed = sum(1 for e in events if e.type == "overspeed")
        harsh = sum(1 for e in events if e.type.startswith("harsh_"))
        online = _age_s(d.last_seen, now)
        rows.append({
            "device_id": d.id,
            "reporting_id": d.reporting_id,
            "vehicle": d.vehicle_registration or d.plate or "",
            "simulated": d.simulated,
            "trips": len(trips),
            "distance_km": distance,
            "max_speed_kmh": max_speed,
            "overspeed_events": overspeed,
            "harsh_events": harsh,
            "online": online is not None and online <= settings.online_threshold_s,
            # Idle time requires per-second ignition/speed sampling we do not persist.
            "idle_minutes": None,
        })
    totals = {
        "devices": len(rows),
        "online": sum(1 for r in rows if r["online"]),
        "total_distance_km": round(sum(r["distance_km"] for r in rows), 2),
        "total_trips": sum(r["trips"] for r in rows),
        "total_overspeed_events": sum(r["overspeed_events"] for r in rows),
        "availability_pct": round(100.0 * sum(1 for r in rows if r["online"]) / len(rows), 1) if rows else 0.0,
        "idle_minutes": None,  # unavailable with current data model
    }
    return totals, rows


def _in_range(dt, frm, to):
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if frm and dt < frm:
        return False
    if to and dt > to:
        return False
    return True


@router.get("/fleet")
async def fleet_report(frm: Optional[str] = Query(default=None, alias="from"),
                       to: Optional[str] = Query(default=None),
                       principal: Principal = Depends(current_principal),
                       store: Store = Depends(get_store), settings: Settings = Depends(get_settings)):
    totals, rows = await _build(store, settings, principal, _parse(frm), _parse(to))
    return {"totals": totals, "rows": rows,
            "unavailable_metrics": ["idle_minutes"]}


@router.get("/fleet.csv")
async def fleet_report_csv(frm: Optional[str] = Query(default=None, alias="from"),
                           to: Optional[str] = Query(default=None),
                           principal: Principal = Depends(current_principal),
                           store: Store = Depends(get_store), settings: Settings = Depends(get_settings)):
    _, rows = await _build(store, settings, principal, _parse(frm), _parse(to))
    buf = io.StringIO()
    cols = ["device_id", "reporting_id", "vehicle", "simulated", "trips", "distance_km",
            "max_speed_kmh", "overspeed_events", "harsh_events", "online"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fleet_report.csv"})
