"""FastAPI dependencies: settings, store and the authenticated principal."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings
from .rbac import Principal
from .security import decode_token
from .store.base import Store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store


def _principal_from_token(token: str, settings: Settings) -> Optional[Principal]:
    payload = decode_token(token, settings.jwt_secret)
    if not payload:
        return None
    try:
        return Principal(
            user_id=int(payload["sub"]),
            email=payload.get("email", ""),
            role=payload.get("role", "readonly"),
            organization_id=payload.get("org"),
        )
    except (KeyError, ValueError, TypeError):
        return None


def current_principal(
    settings: Settings = Depends(get_settings),
    authorization: Optional[str] = Header(default=None),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    p = _principal_from_token(token, settings)
    if not p:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return p


def require_manage(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.can_manage():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role for this action")
    return principal


def require_video(principal: Principal = Depends(current_principal)) -> Principal:
    # Read-only users cannot open video streams (secure video access).
    if principal.role == "readonly":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role for video access")
    return principal


def get_control(request: Request):
    return request.app.state.control


def principal_from_token_string(token: str, settings: Settings) -> Optional[Principal]:
    """Used by the WebSocket endpoint, which receives the token as a query param."""
    return _principal_from_token(token, settings)
