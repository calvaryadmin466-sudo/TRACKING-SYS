"""Driver management endpoints (organization-scoped)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import current_principal, get_store, require_manage
from ..rbac import Principal
from ..serialize import driver_to_dict
from ..store.base import AuditEntry, Driver, Store

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


class DriverIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    license_number: str = ""
    license_class: str = ""
    license_expiry: Optional[str] = None  # ISO date string e.g. "2026-12-31"
    phone: str = ""
    employee_id: str = ""
    status: str = "active"
    notes: str = ""


class AssignIn(BaseModel):
    vehicle_id: Optional[int] = None


def _parse_date(ts: Optional[str]) -> Optional[date]:
    if not ts:
        return None
    try:
        if "T" in ts:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        return date.fromisoformat(ts)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid date: {ts}")


@router.get("")
async def list_drivers(principal: Principal = Depends(current_principal),
                       store: Store = Depends(get_store)):
    drivers = await store.list_drivers(principal.org_scope())
    return {"drivers": [driver_to_dict(d) for d in drivers]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_driver(body: DriverIn, principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store)):
    org_id = principal.organization_id
    did = await store.create_driver(Driver(
        id=0, organization_id=org_id, name=body.name.strip(),
        license_number=body.license_number.strip(),
        license_class=body.license_class.strip(),
        phone=body.phone.strip(), employee_id=body.employee_id.strip(),
        license_expiry=_parse_date(body.license_expiry),
        status=body.status.strip() or "active",
        notes=body.notes.strip(),
    ))
    await store.save_audit(AuditEntry(action="create_driver", entity="driver",
                                      entity_id=str(did), user_id=principal.user_id,
                                      detail=body.name))
    created = await store.get_driver(did)
    return driver_to_dict(created)


@router.put("/{driver_id}")
async def update_driver(driver_id: int, body: DriverIn,
                        principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store)):
    d = await store.get_driver(driver_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "driver not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "driver belongs to another organization")
    d.name = body.name.strip()
    d.license_number = body.license_number.strip()
    d.license_class = body.license_class.strip()
    d.phone = body.phone.strip()
    d.employee_id = body.employee_id.strip()
    d.license_expiry = _parse_date(body.license_expiry)
    d.status = body.status.strip() or "active"
    d.notes = body.notes.strip()
    await store.update_driver(d)
    await store.save_audit(AuditEntry(action="update_driver", entity="driver",
                                      entity_id=str(driver_id), user_id=principal.user_id,
                                      detail=body.name))
    return driver_to_dict(await store.get_driver(driver_id))


@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver(driver_id: int, principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store)):
    d = await store.get_driver(driver_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "driver not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "driver belongs to another organization")
    await store.delete_driver(driver_id)
    await store.save_audit(AuditEntry(action="delete_driver", entity="driver",
                                      entity_id=str(driver_id), user_id=principal.user_id))


@router.post("/{driver_id}/assign")
async def assign_driver(driver_id: int, body: AssignIn,
                        principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store)):
    d = await store.get_driver(driver_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "driver not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "driver belongs to another organization")

    if body.vehicle_id is not None:
        target_v = await store.get_vehicle(body.vehicle_id)
        if not target_v:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vehicle not found")
        if not principal.can_access_org(target_v.organization_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "vehicle belongs to another organization")

    # Unassign this driver from any other vehicles in their org
    all_vehicles = await store.list_vehicles(principal.org_scope())
    for v in all_vehicles:
        if v.driver_id == driver_id and (body.vehicle_id is None or v.id != body.vehicle_id):
            v.driver_id = None
            await store.update_vehicle(v)

    # Assign to target vehicle if provided
    if body.vehicle_id is not None:
        target_v = await store.get_vehicle(body.vehicle_id)
        target_v.driver_id = driver_id
        target_v.driver_name = d.name
        await store.update_vehicle(target_v)

    await store.save_audit(AuditEntry(action="assign_driver", entity="driver",
                                      entity_id=str(driver_id), user_id=principal.user_id,
                                      detail=f"vehicle_id={body.vehicle_id}"))
    return driver_to_dict(await store.get_driver(driver_id))
