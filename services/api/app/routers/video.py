"""Video monitoring control plane (JT/T 1078).

These endpoints issue real video-control commands to the device via the Go
ingestion server's internal control API and expose genuine media-gateway stream
statistics. No fake video is ever served: live playback in a browser requires the
media pipeline to be completed and validated against a physical XV-900-8.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..control_client import ControlClient, ControlError
from ..deps import current_principal, get_control, get_store, require_video
from ..rbac import Principal
from ..serialize import camera_to_dict, video_session_to_dict
from ..store.base import AuditEntry, Store, VideoSession

router = APIRouter(tags=["video"])

NOTE = ("Command dispatched to the device. Live frames require a connected "
        "XV-900-8 that supports JT/T 1078; received-stream stats appear under "
        "/api/video/streams. Browser playback (transcode/relay) is pending "
        "hardware validation.")


class LiveReq(BaseModel):
    channel: int = Field(ge=1, le=64)
    stream_type: int = Field(default=0, ge=0, le=1)  # 0 main, 1 sub


class PlaybackReq(BaseModel):
    channel: int = Field(ge=1, le=64)
    start_time: str = Field(min_length=12, max_length=12)  # YYMMDDhhmmss
    end_time: str = Field(min_length=12, max_length=12)


class VideoQueryReq(BaseModel):
    channel: int = Field(default=0, ge=0, le=64, description="Logical channel: 0=all, 1..64")
    start_time: str = Field(min_length=12, max_length=12, description="YYMMDDhhmmss BCD start time")
    end_time: str = Field(min_length=12, max_length=12, description="YYMMDDhhmmss BCD end time")
    alarm_type: int = Field(default=0, ge=0, description="Alarm filter mask (0=all)")
    media_type: int = Field(default=0, ge=0, le=3, description="0=audio/video, 1=audio, 2=video, 3=any")
    stream_type: int = Field(default=0, ge=0, le=2, description="0=all, 1=main, 2=sub")
    storage_type: int = Field(default=0, ge=0, le=2, description="0=all, 1=disk, 2=backup/SD")


async def _device_or_403(store: Store, principal: Principal, device_id: int):
    d = await store.get_device(device_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
    if not principal.can_access_org(d.organization_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device belongs to another organization")
    return d


@router.get("/api/devices/{device_id}/cameras")
async def cameras(device_id: int, principal: Principal = Depends(current_principal),
                  store: Store = Depends(get_store)):
    await _device_or_403(store, principal, device_id)
    chans = await store.list_camera_channels(device_id)
    return {"device_id": device_id, "channels": [camera_to_dict(c) for c in chans]}


@router.post("/api/devices/{device_id}/video/live")
async def start_live(device_id: int, body: LiveReq,
                     principal: Principal = Depends(require_video),
                     store: Store = Depends(get_store),
                     control: ControlClient = Depends(get_control)):
    d = await _device_or_403(store, principal, device_id)
    sess = VideoSession(id=0, device_id=device_id, reporting_id=d.reporting_id,
                        channel=body.channel, kind="live", status="requested")
    try:
        resp = await control.stream_start(d.reporting_id, body.channel, data_type=1,
                                          stream_type=body.stream_type)
        sess.status = "active"
        sess.video_host = resp.get("video_host", "")
        sess.video_tcp_port = int(resp.get("video_tcp_port", 0) or 0)
    except ControlError as e:
        sess.status = "failed"
        sess.detail = str(e)
        sid = await store.create_video_session(sess)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail={"session_id": sid, "error": str(e)})
    sid = await store.create_video_session(sess)
    await store.save_audit(AuditEntry(action="video_live", entity="device",
                                      entity_id=str(device_id), user_id=principal.user_id,
                                      detail=f"channel {body.channel}"))
    out = video_session_to_dict(await store.get_video_session(sid))
    return {"session": out, "note": NOTE}


@router.post("/api/devices/{device_id}/video/playback")
async def start_playback(device_id: int, body: PlaybackReq,
                         principal: Principal = Depends(require_video),
                         store: Store = Depends(get_store),
                         control: ControlClient = Depends(get_control)):
    d = await _device_or_403(store, principal, device_id)
    sess = VideoSession(id=0, device_id=device_id, reporting_id=d.reporting_id,
                        channel=body.channel, kind="playback", status="requested")
    try:
        resp = await control.playback(d.reporting_id, body.channel, body.start_time, body.end_time)
        sess.status = "active"
        sess.video_host = resp.get("video_host", "")
        sess.video_tcp_port = int(resp.get("video_tcp_port", 0) or 0)
    except ControlError as e:
        sess.status = "failed"
        sess.detail = str(e)
        sid = await store.create_video_session(sess)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail={"session_id": sid, "error": str(e)})
    sid = await store.create_video_session(sess)
    await store.save_audit(AuditEntry(action="video_playback", entity="device",
                                      entity_id=str(device_id), user_id=principal.user_id,
                                      detail=f"channel {body.channel} {body.start_time}-{body.end_time}"))
    return {"session": video_session_to_dict(await store.get_video_session(sid)), "note": NOTE}


@router.post("/api/devices/{device_id}/video/query")
async def query_video(device_id: int, body: VideoQueryReq,
                      principal: Principal = Depends(require_video),
                      store: Store = Depends(get_store),
                      control: ControlClient = Depends(get_control)):
    """Dispatch a 0x9205 remote AV resource list query to the device."""
    d = await _device_or_403(store, principal, device_id)
    try:
        resp = await control.query_video_resources(
            d.reporting_id,
            channel=body.channel,
            start_time=body.start_time,
            end_time=body.end_time,
            alarm_type=body.alarm_type,
            media_type=body.media_type,
            stream_type=body.stream_type,
            storage_type=body.storage_type,
        )
    except ControlError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Query dispatch failed: {e}")

    await store.save_audit(AuditEntry(
        action="video_query", entity="device", entity_id=str(device_id),
        user_id=principal.user_id,
        detail=f"ch={body.channel} {body.start_time}-{body.end_time} media={body.media_type}",
    ))
    return {
        "device_id": device_id,
        "reporting_id": d.reporting_id,
        "query": body.model_dump(),
        "dispatched": True,
        "note": "0x9205 query dispatched to terminal. Terminal responds asynchronously with 0x1205 resource list.",
        "resources": resp.get("resources", []),
    }


@router.post("/api/video/sessions/{sid}/stop")
async def stop_session(sid: int, principal: Principal = Depends(require_video),
                       store: Store = Depends(get_store),
                       control: ControlClient = Depends(get_control)):
    sess = await store.get_video_session(sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    await _device_or_403(store, principal, sess.device_id)
    try:
        await control.stream_stop(sess.reporting_id, sess.channel)
    except ControlError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e))
    await store.end_video_session(sid, "ended")
    return {"ok": True}


@router.get("/api/video/sessions")
async def list_sessions(device_id: int | None = Query(default=None),
                        principal: Principal = Depends(current_principal),
                        store: Store = Depends(get_store)):
    sessions = await store.list_video_sessions(principal.org_scope(), device_id, 200)
    return {"sessions": [video_session_to_dict(s) for s in sessions]}


@router.get("/api/video/streams")
async def live_streams(principal: Principal = Depends(current_principal),
                       control: ControlClient = Depends(get_control)):
    """Genuine per-(SIM, channel) stream stats from the media gateway."""
    try:
        streams = await control.streams()
    except ControlError as e:
        return {"streams": [], "note": f"media gateway unavailable: {e}"}
    return {"streams": streams}
