"""Administration: organizations, users and roles. All permission checks are
enforced here (backend), not merely by hiding frontend controls."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import current_principal, get_store, require_user_admin
from ..rbac import Principal
from ..security import hash_password
from ..serialize import audit_to_dict, user_to_dict
from ..store.base import AuditEntry, Store, User

router = APIRouter(prefix="/api", tags=["admin"])

# Roles a company admin may assign (never super_admin or another company_admin).
COMPANY_ASSIGNABLE = {"fleet_manager", "dispatcher", "operator", "readonly"}


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = ""
    role: str
    organization_id: Optional[int] = None


class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=80)


@router.get("/roles")
async def list_roles(_: Principal = Depends(current_principal), store: Store = Depends(get_store)):
    return {"roles": [{"id": r.id, "name": r.name} for r in await store.list_roles()]}


@router.get("/organizations")
async def list_orgs(principal: Principal = Depends(require_user_admin), store: Store = Depends(get_store)):
    orgs = await store.list_organizations()
    if not principal.is_super_admin:
        orgs = [o for o in orgs if o.id == principal.organization_id]
    return {"organizations": [{"id": o.id, "name": o.name} for o in orgs]}


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgIn, principal: Principal = Depends(current_principal),
                     store: Store = Depends(get_store)):
    if not principal.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only a super admin can create organizations")
    oid = await store.create_organization(body.name, body.slug)
    await store.save_audit(AuditEntry(action="create_org", entity="organization",
                                      entity_id=str(oid), user_id=principal.user_id, detail=body.name))
    return {"id": oid, "name": body.name}


@router.get("/users")
async def list_users(principal: Principal = Depends(require_user_admin), store: Store = Depends(get_store)):
    users = await store.list_users(principal.org_scope())
    return {"users": [user_to_dict(u) for u in users]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserIn, principal: Principal = Depends(require_user_admin),
                      store: Store = Depends(get_store)):
    role_id = await store.role_id_by_name(body.role)
    if role_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown role")

    if principal.is_super_admin:
        org_id = body.organization_id
    else:
        # Company admins create only within their own org, and only lower roles.
        org_id = principal.organization_id
        if body.role not in COMPANY_ASSIGNABLE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"cannot assign role '{body.role}'")

    if await store.get_user_by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with that email already exists")

    uid = await store.create_user(User(
        id=0, role_id=role_id, role_name=body.role, email=body.email,
        password_hash=hash_password(body.password), full_name=body.full_name,
        is_active=True, organization_id=org_id))
    await store.save_audit(AuditEntry(action="create_user", entity="user",
                                      entity_id=str(uid), user_id=principal.user_id, detail=body.email))
    return {"id": uid, "email": body.email, "role": body.role, "organization_id": org_id}


@router.get("/audit-logs")
async def audit_logs(limit: int = 200, principal: Principal = Depends(require_user_admin),
                     store: Store = Depends(get_store)):
    entries = await store.list_audit(principal.org_scope(), limit)
    return {"count": len(entries), "entries": [audit_to_dict(a) for a in entries]}
