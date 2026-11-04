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


# Per-event-type demerit weights for the driver scorecard (score starts at 100).
SCORE_WEIGHTS = {
    "overspeed": 4,
    "harsh_braking": 3,
    "harsh_acceleration": 2,
    "idling": 1,
    "gps_signal_loss": 1,
}
ALARM_WEIGHT = 8  # any device-reported alarm_* event


def _grade(score: float) -> str:
    return "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"


@router.get("/driver-scores")
async def driver_scores(frm: Optional[str] = Query(default=None, alias="from"),
                        to: Optional[str] = Query(default=None),
                        principal: Principal = Depends(current_principal),
                        store: Store = Depends(get_store)):
    frm_dt, to_dt = _parse(frm), _parse(to)
    devices = await store.list_devices(principal.org_scope())
    rows = []
    for d in devices:
        events = await store.list_events(principal.org_scope(), d.id, frm_dt, None, 5000)
        if to_dt:
            events = [e for e in events if e.at and e.at <= to_dt]
        counts, demerits = {}, 0
        for e in events:
            if e.type.startswith("alarm_"):
                w = ALARM_WEIGHT
            else:
                w = SCORE_WEIGHTS.get(e.type, 0)
            if w:
                counts[e.type] = counts.get(e.type, 0) + 1
                demerits += w
        score = max(0, 100 - demerits)
        rows.append({
            "device_id": d.id, "reporting_id": d.reporting_id,
            "vehicle": d.vehicle_registration or d.plate or "", "simulated": d.simulated,
            "score": score, "grade": _grade(score), "events": counts,
            "total_incidents": sum(counts.values()),
        })
    rows.sort(key=lambda r: r["score"])
    avg = round(sum(r["score"] for r in rows) / len(rows), 1) if rows else 100.0
    return {"fleet_average": avg, "drivers": rows,
            "weights": {**SCORE_WEIGHTS, "alarm_*": ALARM_WEIGHT}}


async def _collect_trips(store: Store, principal: Principal, frm, to):
    devices = await store.list_devices(principal.org_scope())
    label = {d.id: (d.vehicle_registration or d.plate or d.reporting_id) for d in devices}
    out = []
    for d in devices:
        for t in await store.list_trips(d.id, 1000):
            if not _in_range(t.started_at, frm, to):
                continue
            dur = None
            if t.started_at and t.ended_at:
                dur = round((t.ended_at - t.started_at).total_seconds() / 60.0, 1)
            out.append({
                "trip_id": t.id, "device_id": d.id, "vehicle": label.get(d.id, ""),
                "started_at": _iso_opt(t.started_at), "ended_at": _iso_opt(t.ended_at),
                "distance_km": t.distance_km, "max_speed_kmh": t.max_speed, "duration_min": dur,
            })
    out.sort(key=lambda r: r["started_at"] or "", reverse=True)
    return out


def _iso_opt(dt):
    return dt.isoformat() if dt else None


@router.get("/trips")
async def trips_report(frm: Optional[str] = Query(default=None, alias="from"),
                       to: Optional[str] = Query(default=None),
                       principal: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    trips = await _collect_trips(store, principal, _parse(frm), _parse(to))
    durations = [t["duration_min"] for t in trips if t["duration_min"] is not None]
    totals = {
        "trips": len(trips),
        "total_distance_km": round(sum(t["distance_km"] for t in trips), 2),
        "total_duration_min": round(sum(durations), 1),
        "avg_distance_km": round(sum(t["distance_km"] for t in trips) / len(trips), 2) if trips else 0.0,
        "longest_trip_km": round(max((t["distance_km"] for t in trips), default=0.0), 2),
    }
    return {"totals": totals, "trips": trips}


@router.get("/trips.csv")
async def trips_report_csv(frm: Optional[str] = Query(default=None, alias="from"),
                           to: Optional[str] = Query(default=None),
                           principal: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    trips = await _collect_trips(store, principal, _parse(frm), _parse(to))
    buf = io.StringIO()
    cols = ["trip_id", "device_id", "vehicle", "started_at", "ended_at", "distance_km", "max_speed_kmh", "duration_min"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for t in trips:
        w.writerow(t)
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=trips_report.csv"})


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
