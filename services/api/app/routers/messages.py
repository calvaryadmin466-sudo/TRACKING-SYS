"""Device text message distribution (JT/T 808 0x8300)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..control_client import ControlClient, ControlError
from ..deps import current_principal, get_control, get_store, require_operator
from ..rbac import Principal
from ..serialize import device_message_to_dict
from ..store.base import AuditEntry, DeviceMessage, Store

router = APIRouter(tags=["messages"])


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=240, description="Message text (up to 240 characters)")
    flag: int = Field(default=12, ge=0, le=63, description="JT/T 808 delivery flag bitmask (1=emergency, 4=display, 8=TTS, 16=ad)")


@router.post("/api/devices/{device_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_device_message(device_id: int, body: MessageIn,
                              principal: Principal = Depends(require_operator),
                              store: Store = Depends(get_store),
                              control: ControlClient = Depends(get_control)):
    """Dispatch a text message (0x8300) to a connected vehicle MDVR."""
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")

    # Try dispatching to device via Ingestion Control API
    msg = DeviceMessage(
        id=0,
        organization_id=d.organization_id,
        device_id=device_id,
        user_id=principal.user_id,
        flag=body.flag,
        text=body.text,
        status="sent",
        reporting_id=d.reporting_id,
        user_email=principal.email,
    )

    try:
        await control.send_text_message(d.reporting_id, body.flag, body.text)
        msg.status = "sent"
    except ControlError as e:
        msg.status = "failed"
        msg.detail = str(e)
        mid = await store.save_device_message(msg)
        msg.id = mid
        await store.save_audit(AuditEntry(
            action="send_message_failed", entity="device", entity_id=str(device_id),
            user_id=principal.user_id, detail=f"failed: {e}",
        ))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Device dispatch failed: {e}")

    mid = await store.save_device_message(msg)
    msg.id = mid

    await store.save_audit(AuditEntry(
        action="send_message", entity="device", entity_id=str(device_id),
        user_id=principal.user_id, detail=f"flag={body.flag} chars={len(body.text)}",
    ))

    return {"message": device_message_to_dict(msg)}


@router.get("/api/devices/{device_id}/messages")
async def list_device_messages(device_id: int,
                               limit: int = Query(default=50, ge=1, le=200),
                               principal: Principal = Depends(current_principal),
                               store: Store = Depends(get_store)):
    """List message history for a specific device."""
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")

    messages = await store.list_device_messages(org_id=principal.org_scope(), device_id=device_id, limit=limit)
    return {"device_id": device_id, "messages": [device_message_to_dict(m) for m in messages]}


@router.get("/api/messages")
async def list_messages(limit: int = Query(default=50, ge=1, le=200),
                        principal: Principal = Depends(current_principal),
                        store: Store = Depends(get_store)):
    """List recent dispatched messages across the organization."""
    messages = await store.list_device_messages(org_id=principal.org_scope(), limit=limit)
    return {"messages": [device_message_to_dict(m) for m in messages]}
