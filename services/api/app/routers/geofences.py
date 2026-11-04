"""Geofence management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import current_principal, get_store, require_manage
from ..rbac import Principal
from ..serialize import geofence_to_dict
from ..store.base import AuditEntry, Geofence, Store

router = APIRouter(prefix="/api/geofences", tags=["geofences"])


class GeofenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ring: list[list[float]] = Field(min_length=3)  # [[lat, lon], ...]


@router.get("")
async def list_geofences(principal: Principal = Depends(current_principal),
                         store: Store = Depends(get_store)):
    gfs = await store.list_geofences(principal.org_scope())
    return {"geofences": [geofence_to_dict(g) for g in gfs]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_geofence(body: GeofenceIn, principal: Principal = Depends(require_manage),
                          store: Store = Depends(get_store)):
    ring = [(float(p[0]), float(p[1])) for p in body.ring]
    gid = await store.create_geofence(Geofence(
        id=0, organization_id=principal.organization_id, name=body.name, ring=ring))
    await store.save_audit(AuditEntry(action="create_geofence", entity="geofence",
                                      entity_id=str(gid), user_id=principal.user_id, detail=body.name))
    g = await store.get_geofence(gid)
    return geofence_to_dict(g)


@router.delete("/{gid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(gid: int, principal: Principal = Depends(require_manage),
                          store: Store = Depends(get_store)):
    g = await store.get_geofence(gid)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "geofence not found")
    if not principal.can_access_org(g.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "geofence belongs to another organization")
    await store.delete_geofence(gid)
    await store.save_audit(AuditEntry(action="delete_geofence", entity="geofence",
                                      entity_id=str(gid), user_id=principal.user_id))
