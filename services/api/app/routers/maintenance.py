"""Maintenance / service reminders. Due status is computed from real data: the
due date vs now, and the due odometer vs the device's latest reported odometer."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..deps import current_principal, get_store, require_manage
from ..rbac import Principal
from ..serialize import maintenance_to_dict
from ..store.base import AuditEntry, MaintenanceItem, Store

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

DUE_SOON_DAYS = 7
DUE_SOON_KM = 500


class MaintenanceIn(BaseModel):
    device_id: int
    title: str = Field(min_length=1, max_length=160)
    kind: str = "service"
    due_date: Optional[str] = None            # ISO date/datetime
    due_odometer_km: Optional[float] = None
    notes: str = ""


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid date: {ts}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _due_status(item: dict, odometer: Optional[float], now: datetime) -> dict:
    """Augment a serialized item with computed due state."""
    if item["status"] == "done":
        item["due_state"] = "done"
        return item
    state = "ok"
    days_left = None
    if item["due_date"]:
        due = datetime.fromisoformat(item["due_date"])
        days_left = (due - now).total_seconds() / 86400
        if days_left < 0:
            state = "overdue"
        elif days_left <= DUE_SOON_DAYS:
            state = "due_soon"
    km_left = None
    if item["due_odometer_km"] is not None and odometer is not None:
        km_left = item["due_odometer_km"] - odometer
        if km_left <= 0:
            state = "overdue"
        elif km_left <= DUE_SOON_KM and state == "ok":
            state = "due_soon"
    item["due_state"] = state
    item["days_left"] = None if days_left is None else round(days_left, 1)
    item["km_left"] = None if km_left is None else round(km_left, 1)
    return item


async def _odometer(store: Store, device_id: int) -> Optional[float]:
    d = await store.get_device(device_id)
    return d.mileage_km if d else None


@router.get("")
async def list_items(device_id: Optional[int] = Query(default=None),
                     principal: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    items = await store.list_maintenance(principal.org_scope(), device_id)
    now = datetime.now(timezone.utc)
    odo_cache: dict[int, Optional[float]] = {}
    out = []
    for m in items:
        if m.device_id not in odo_cache:
            odo_cache[m.device_id] = await _odometer(store, m.device_id)
        out.append(_due_status(maintenance_to_dict(m), odo_cache[m.device_id], now))
    summary = {
        "total": len(out),
        "overdue": sum(1 for x in out if x.get("due_state") == "overdue"),
        "due_soon": sum(1 for x in out if x.get("due_state") == "due_soon"),
        "open": sum(1 for x in out if x["status"] == "open"),
    }
    return {"summary": summary, "items": out}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(body: MaintenanceIn, principal: Principal = Depends(require_manage),
                      store: Store = Depends(get_store)):
    d = await store.get_device(body.device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    mid = await store.create_maintenance(MaintenanceItem(
        id=0, device_id=body.device_id, title=body.title, kind=body.kind,
        organization_id=d.organization_id, due_date=_parse(body.due_date),
        due_odometer_km=body.due_odometer_km, odometer_at_create=d.mileage_km or 0.0, notes=body.notes))
    await store.save_audit(AuditEntry(action="create_maintenance", entity="maintenance",
                                      entity_id=str(mid), user_id=principal.user_id, detail=body.title))
    return maintenance_to_dict(await store.get_maintenance(mid))


@router.post("/{mid}/complete")
async def complete_item(mid: int, principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store)):
    m = await store.get_maintenance(mid)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    if not principal.can_access_org(m.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "belongs to another organization")
    m.status = "done"
    m.completed_at = datetime.now(timezone.utc)
    await store.update_maintenance(m)
    await store.save_audit(AuditEntry(action="complete_maintenance", entity="maintenance",
                                      entity_id=str(mid), user_id=principal.user_id))
    return maintenance_to_dict(await store.get_maintenance(mid))


@router.delete("/{mid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(mid: int, principal: Principal = Depends(require_manage),
                      store: Store = Depends(get_store)):
    m = await store.get_maintenance(mid)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    if not principal.can_access_org(m.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "belongs to another organization")
    await store.delete_maintenance(mid)
