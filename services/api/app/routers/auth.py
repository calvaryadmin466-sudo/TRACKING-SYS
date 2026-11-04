"""Authentication endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import Settings
from ..deps import current_principal, get_settings, get_store
from ..hardening import client_ip
from ..rbac import Principal
from ..schemas import LoginRequest
from ..security import create_access_token, verify_password
from ..store.base import AuditEntry, Store

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, request: Request, store: Store = Depends(get_store),
                settings: Settings = Depends(get_settings)):
    # Per-IP brute-force protection.
    request.app.state.login_limiter.check(client_ip(request))
    user = await store.get_user_by_email(body.email)
    # Constant-ish behaviour: do not reveal whether the email exists.
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    await store.update_user_last_login(user.id, datetime.now(timezone.utc))
    await store.save_audit(AuditEntry(action="login", entity="user",
                                      entity_id=str(user.id), user_id=user.id))
    token = create_access_token(user, settings.jwt_secret, settings.jwt_expire_minutes)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role_name,
            "organization_id": user.organization_id,
            "full_name": user.full_name,
        },
    }


@router.get("/me")
async def me(principal: Principal = Depends(current_principal)):
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "role": principal.role,
        "organization_id": principal.organization_id,
        "is_super_admin": principal.is_super_admin,
    }
