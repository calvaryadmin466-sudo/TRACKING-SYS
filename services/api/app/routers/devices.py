"""Device management endpoints (organization-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from fastapi import Query

from ..deps import current_principal, get_settings, get_store, require_manage
from ..rbac import Principal
from ..schemas import DeviceUpdate
from ..serialize import device_to_dict, packet_to_dict
from ..store.base import AuditEntry, DevicePatch, Store

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
async def list_devices(principal: Principal = Depends(current_principal),
                       store: Store = Depends(get_store), settings=Depends(get_settings)):
    devices = await store.list_devices(principal.org_scope())
    items = [device_to_dict(d, settings) for d in devices]
    summary = {
        "total": len(items),
        "online": sum(1 for d in items if d["online"]),
        "moving": sum(1 for d in items if d["position"] and d["position"]["fresh"] and d["position"]["speed"] > 3),
        "offline": sum(1 for d in items if not d["online"]),
        "no_position": sum(1 for d in items if not d["has_position"]),
    }
    return {"summary": summary, "devices": items}


@router.get("/{device_id}")
async def get_device(device_id: int, principal: Principal = Depends(current_principal),
                     store: Store = Depends(get_store), settings=Depends(get_settings)):
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    return device_to_dict(d, settings)


@router.patch("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdate,
                        principal: Principal = Depends(require_manage),
                        store: Store = Depends(get_store), settings=Depends(get_settings)):
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")

    # If assigning a vehicle, it must be in the caller's organization.
    if body.vehicle_id is not None:
        v = await store.get_vehicle(body.vehicle_id)
        if not v:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "vehicle not found")
        if not principal.can_access_org(v.organization_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "vehicle belongs to another organization")

    await store.update_device(device_id, DevicePatch(
        vehicle_id=body.vehicle_id, active=body.active, plate=body.plate))
    await store.save_audit(AuditEntry(action="update_device", entity="device",
                                      entity_id=str(device_id), user_id=principal.user_id,
                                      detail=body.model_dump_json()))
    updated = await store.get_device(device_id)
    return device_to_dict(updated, settings)


@router.get("/{device_id}/packets")
async def device_packets(device_id: int, limit: int = Query(default=100, ge=1, le=1000),
                         principal: Principal = Depends(require_manage),
                         store: Store = Depends(get_store)):
    """Authorized raw-packet diagnostics for a device (manage roles only).

    Raw packets are captured by the Go ingestion server into PostgreSQL; in the
    in-memory dev store this returns empty.
    """
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    packets = await store.list_raw_packets(d.reporting_id, limit)
    return {"device_id": device_id, "reporting_id": d.reporting_id,
            "count": len(packets), "packets": [packet_to_dict(p) for p in packets]}
