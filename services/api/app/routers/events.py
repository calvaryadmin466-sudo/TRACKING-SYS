"""Event / alert feed endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import current_principal, get_store
from ..rbac import Principal
from ..serialize import event_to_dict
from ..store.base import Store

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def list_events(device_id: Optional[int] = Query(default=None),
                      types: Optional[str] = Query(default=None, description="comma-separated"),
                      since: Optional[str] = Query(default=None),
                      limit: int = Query(default=100, ge=1, le=1000),
                      principal: Principal = Depends(current_principal),
                      store: Store = Depends(get_store)):
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid 'since' timestamp")
    type_list = [t for t in types.split(",")] if types else None
    evts = await store.list_events(principal.org_scope(), device_id, since_dt, type_list, limit)
    return {"count": len(evts), "events": [event_to_dict(e) for e in evts]}
