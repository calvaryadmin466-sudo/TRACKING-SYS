"""Health and readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(settings=Depends(get_settings)):
    return {
        "status": "ok",
        "store": "postgres" if settings.use_postgres else "memory",
        "demo_feed": settings.demo_feed,
    }
