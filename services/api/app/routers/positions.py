"""Historical position / trip-playback data."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import current_principal, get_store
from ..geo_playback import build_speed_segments, detect_stops, speed_tier
from ..rbac import Principal
from ..serialize import position_to_dict
from ..store.base import Store

router = APIRouter(prefix="/api/devices", tags=["history"])


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid timestamp: {ts}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/{device_id}/history")
async def history(device_id: int,
                  frm: Optional[str] = Query(default=None, alias="from"),
                  to: Optional[str] = Query(default=None),
                  limit: int = Query(default=5000, ge=1, le=50000),
                  principal: Principal = Depends(current_principal),
                  store: Store = Depends(get_store)):
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    positions = await store.list_positions(device_id, _parse(frm), _parse(to), limit)
    return {
        "device_id": device_id,
        "reporting_id": d.reporting_id,
        "count": len(positions),
        "positions": [position_to_dict(p) for p in positions],
    }


@router.get("/{device_id}/playback")
async def playback(device_id: int,
                   frm: Optional[str] = Query(default=None, alias="from"),
                   to: Optional[str] = Query(default=None),
                   min_stop_s: int = Query(default=300, ge=10, le=86400),
                   limit: int = Query(default=10000, ge=1, le=50000),
                   principal: Principal = Depends(current_principal),
                   store: Store = Depends(get_store)):
    """High-resolution track playback with speed-color segmentation and parking stop detection."""
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    positions = await store.list_positions(device_id, _parse(frm), _parse(to), limit)
    pos_dicts = [position_to_dict(p) for p in positions if p.valid]

    segments = build_speed_segments(pos_dicts)
    stops = detect_stops(pos_dicts, min_stop_s=min_stop_s)

    speeds = [p["speed"] for p in pos_dicts]
    tier_counts = {"L": 0, "M": 0, "H": 0, "S": 0}
    for sp in speeds:
        tier_counts[speed_tier(sp)] += 1

    summary = {
        "total_points": len(pos_dicts),
        "max_speed_kmh": round(max(speeds, default=0.0), 1),
        "avg_speed_kmh": round(sum(speeds) / len(speeds), 1) if speeds else 0.0,
        "tier_counts": tier_counts,
        "stop_count": len(stops),
    }

    return {
        "device_id": device_id,
        "reporting_id": d.reporting_id,
        "summary": summary,
        "segments": segments,
        "stops": stops,
        "positions": pos_dicts,
    }
