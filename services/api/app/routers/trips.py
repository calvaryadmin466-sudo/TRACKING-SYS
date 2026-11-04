"""Trip history and trip-detail (route playback) endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import current_principal, get_store
from ..rbac import Principal
from ..serialize import trip_to_dict
from ..store.base import Store

router = APIRouter(tags=["trips"])


@router.get("/api/devices/{device_id}/trips")
async def device_trips(device_id: int, limit: int = Query(default=100, ge=1, le=1000),
                       principal: Principal = Depends(current_principal),
                       store: Store = Depends(get_store)):
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    trips = await store.list_trips(device_id, limit)
    return {"device_id": device_id, "count": len(trips),
            "trips": [trip_to_dict(t) for t in trips]}


@router.get("/api/trips/{trip_id}")
async def trip_detail(trip_id: int, principal: Principal = Depends(current_principal),
                      store: Store = Depends(get_store)):
    t = await store.get_trip(trip_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trip not found")
    d = await store.get_device(t.device_id)
    if d and not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "trip belongs to another organization")
    return trip_to_dict(t, with_path=True)
