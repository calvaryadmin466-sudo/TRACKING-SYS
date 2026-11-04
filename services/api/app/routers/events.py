"""Event / alert feed endpoints, with acknowledgement and resolution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import current_principal, get_store, require_operator
from ..rbac import Principal
from ..serialize import event_to_dict
from ..store.base import AuditEntry, Store

router = APIRouter(prefix="/api/events", tags=["events"])


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    if not since:
        return None
    try:
        dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid 'since' timestamp")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("")
async def list_events(device_id: Optional[int] = Query(default=None),
                      types: Optional[str] = Query(default=None, description="comma-separated"),
                      severity: Optional[str] = Query(default=None, description="info|warning|alarm"),
                      acknowledged: Optional[bool] = Query(default=None),
                      since: Optional[str] = Query(default=None),
                      limit: int = Query(default=200, ge=1, le=2000),
                      principal: Principal = Depends(current_principal),
                      store: Store = Depends(get_store)):
    type_list = types.split(",") if types else None
    evts = await store.list_events(principal.org_scope(), device_id, _parse_since(since), type_list, limit)
    if severity:
        evts = [e for e in evts if e.severity == severity]
    if acknowledged is not None:
        evts = [e for e in evts if e.acknowledged == acknowledged]
    open_alarms = sum(1 for e in evts if e.severity != "info" and not e.acknowledged)
    return {"count": len(evts), "open_alarms": open_alarms,
            "events": [event_to_dict(e) for e in evts]}


async def _event_or_403(store: Store, principal: Principal, eid: int):
    e = await store.get_event(eid)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    dev = await store.get_device(e.device_id)
    if dev and not principal.can_access_org(dev.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "event belongs to another organization")
    return e


@router.post("/{eid}/ack")
async def acknowledge(eid: int, principal: Principal = Depends(require_operator),
                      store: Store = Depends(get_store)):
    await _event_or_403(store, principal, eid)
    await store.ack_event(eid, principal.user_id)
    await store.save_audit(AuditEntry(action="ack_event", entity="event",
                                      entity_id=str(eid), user_id=principal.user_id))
    return event_to_dict(await store.get_event(eid))


@router.post("/{eid}/resolve")
async def resolve(eid: int, principal: Principal = Depends(require_operator),
                  store: Store = Depends(get_store)):
    await _event_or_403(store, principal, eid)
    await store.resolve_event(eid)
    await store.save_audit(AuditEntry(action="resolve_event", entity="event",
                                      entity_id=str(eid), user_id=principal.user_id))
    return event_to_dict(await store.get_event(eid))
