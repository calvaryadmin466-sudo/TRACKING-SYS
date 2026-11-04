"""Vehicle management endpoints (organization-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_principal, get_store, require_manage
from ..rbac import Principal
from ..schemas import VehicleIn
from ..serialize import vehicle_to_dict
from ..store.base import AuditEntry, Store, Vehicle

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("")
async def list_vehicles(principal: Principal = Depends(current_principal),
                        store: Store = Depends(get_store)):
    vehicles = await store.list_vehicles(principal.org_scope())
    return {"vehicles": [vehicle_to_dict(v) for v in vehicles]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_vehicle(body: VehicleIn, principal: Principal = Depends(require_manage),
                         store: Store = Depends(get_store)):
    # Non-super-admins can only create within their own organization.
    org_id = principal.organization_id
    if principal.is_super_admin:
        org_id = principal.organization_id  # super admin's vehicles default to its own org (may be None)
    v = Vehicle(id=0, registration=body.registration, vehicle_type=body.vehicle_type,
                driver_name=body.driver_name, fleet_id=body.fleet_id, organization_id=org_id)
    vid = await store.create_vehicle(v)
    await store.save_audit(AuditEntry(action="create_vehicle", entity="vehicle",
                                      entity_id=str(vid), user_id=principal.user_id,
                                      detail=body.model_dump_json()))
    created = await store.get_vehicle(vid)
    return vehicle_to_dict(created)


@router.put("/{vehicle_id}")
async def update_vehicle(vehicle_id: int, body: VehicleIn,
                         principal: Principal = Depends(require_manage),
                         store: Store = Depends(get_store)):
    v = await store.get_vehicle(vehicle_id)
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vehicle not found")
    if not principal.can_access_org(v.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "vehicle belongs to another organization")
    v.registration = body.registration
    v.vehicle_type = body.vehicle_type
    v.driver_name = body.driver_name
    v.fleet_id = body.fleet_id
    await store.update_vehicle(v)
    await store.save_audit(AuditEntry(action="update_vehicle", entity="vehicle",
                                      entity_id=str(vehicle_id), user_id=principal.user_id,
                                      detail=body.model_dump_json()))
    return vehicle_to_dict(await store.get_vehicle(vehicle_id))
