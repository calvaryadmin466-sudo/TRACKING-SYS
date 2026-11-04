"""Notification rules management + delivery log."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import current_principal, get_store, require_manage
from ..notify import dispatch
from ..rbac import Principal
from ..serialize import notification_to_dict, rule_to_dict
from ..store.base import AuditEntry, NotificationLogEntry, NotificationRule, Store

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    event_types: list[str] = Field(default_factory=list)  # empty = any; supports "alarm_*"
    min_severity: str = "warning"
    channel: str = "webhook"
    target: str = ""
    active: bool = True


@router.get("/rules")
async def list_rules(principal: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    return {"rules": [rule_to_dict(r) for r in await store.list_rules(principal.org_scope())]}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleIn, principal: Principal = Depends(require_manage), store: Store = Depends(get_store)):
    rid = await store.create_rule(NotificationRule(
        id=0, name=body.name, organization_id=principal.organization_id,
        event_types=body.event_types, min_severity=body.min_severity,
        channel=body.channel, target=body.target, active=body.active))
    await store.save_audit(AuditEntry(action="create_rule", entity="notification_rule",
                                      entity_id=str(rid), user_id=principal.user_id, detail=body.name))
    return rule_to_dict(await store.get_rule(rid))


async def _rule_or_403(store: Store, principal: Principal, rid: int):
    r = await store.get_rule(rid)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    if not principal.can_access_org(r.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "rule belongs to another organization")
    return r


@router.put("/rules/{rid}")
async def update_rule(rid: int, body: RuleIn, principal: Principal = Depends(require_manage),
                      store: Store = Depends(get_store)):
    r = await _rule_or_403(store, principal, rid)
    r.name, r.event_types, r.min_severity = body.name, body.event_types, body.min_severity
    r.channel, r.target, r.active = body.channel, body.target, body.active
    await store.update_rule(r)
    return rule_to_dict(await store.get_rule(rid))


@router.delete("/rules/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rid: int, principal: Principal = Depends(require_manage), store: Store = Depends(get_store)):
    await _rule_or_403(store, principal, rid)
    await store.delete_rule(rid)


@router.post("/rules/{rid}/test")
async def test_rule(rid: int, principal: Principal = Depends(require_manage), store: Store = Depends(get_store)):
    """Fire a synthetic test payload through the rule's channel to verify delivery."""
    r = await _rule_or_403(store, principal, rid)
    payload = {"event": {"type": "test_notification", "severity": r.min_severity,
                         "detail": "FleetTrack test", "at": datetime.now(timezone.utc).isoformat()},
               "test": True}
    status_, detail = await dispatch(r, payload)
    await store.save_notification(NotificationLogEntry(
        id=None, rule_id=r.id, event_id=None, event_type="test_notification",
        channel=r.channel, target=r.target, status=status_, detail=detail))
    return {"status": status_, "detail": detail}


@router.get("/log")
async def log(limit: int = 100, principal: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    entries = await store.list_notifications(principal.org_scope(), limit)
    return {"count": len(entries), "entries": [notification_to_dict(n) for n in entries]}
