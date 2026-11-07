"""Device management endpoints (organization-scoped)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from fastapi import Query

from ..deps import current_principal, get_settings, get_store, require_manage
from ..rbac import Principal
from ..schemas import DeviceCreate, DeviceUpdate
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


@router.post("", status_code=status.HTTP_201_CREATED)
async def provision_device(body: DeviceCreate,
                           principal: Principal = Depends(require_manage),
                           store: Store = Depends(get_store), settings=Depends(get_settings)):
    """Register a device up front by its identifiers (admin provisioning).

    The admin supplies the device ID (JT/T 808 reporting ID), the vehicle plate
    and the MDVR decoder's IP. The record is created in the caller's organization
    so the unit is known before it dials in; when it connects the ingestion
    server fills in serial/model/connection details without clearing these.
    """
    reporting_id = body.device_id.strip()
    if not reporting_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "device_id is required")
    # Refuse to touch a reporting ID already owned by another organization (a
    # company admin must not hijack another tenant's device). Unassigned or
    # same-org devices may be claimed/updated.
    existing = await store.get_device_by_reporting_id(reporting_id)
    if existing and existing.organization_id is not None and not principal.can_access_org(existing.organization_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "device ID is already registered to another organization")
    # Keep a provisioned device inside the admin's own organization. A super_admin
    # with no organization provisions an unassigned device (visible platform-wide).
    org_id = principal.organization_id
    dev_id, created = await store.provision_device(
        reporting_id, body.plate.strip(), body.ip_address.strip(), body.model.strip(), org_id,
        sim_number=body.sim_number.strip())
    d = await store.get_device(dev_id)
    await store.save_audit(AuditEntry(
        action="provision_device" if created else "reprovision_device", entity="device",
        entity_id=str(dev_id), user_id=principal.user_id,
        detail=f"reporting_id={reporting_id} plate={body.plate} ip={body.ip_address} sim={body.sim_number}"))
    return {"device": device_to_dict(d, settings), "created": created}


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
        vehicle_id=body.vehicle_id, active=body.active, plate=body.plate,
        ip_address=body.ip_address,
        sim_number=body.sim_number.strip() if body.sim_number is not None else None))
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
