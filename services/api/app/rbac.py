"""Role-based access control and company (organization) data isolation.

Roles (highest to lowest privilege):
  super_admin    - platform-wide; sees and manages every organization
  company_admin  - manages their own organization (devices, vehicles, users)
  fleet_manager  - manages devices/vehicles within their organization
  dispatcher     - operational; may update vehicle assignments
  operator       - monitoring; read-only live + history
  readonly       - read-only
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ROLES = ["super_admin", "company_admin", "fleet_manager", "dispatcher", "operator", "readonly"]

# Roles permitted to create/modify devices and vehicles.
MANAGE_ROLES = {"super_admin", "company_admin", "fleet_manager"}
# Roles permitted to manage users.
USER_ADMIN_ROLES = {"super_admin", "company_admin"}


@dataclass
class Principal:
    """The authenticated caller, derived from a verified JWT."""
    user_id: int
    email: str
    role: str
    organization_id: Optional[int]

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    def org_scope(self) -> Optional[int]:
        """Organization filter to apply to queries.

        Super admins get None (all organizations); everyone else is restricted to
        their own organization id.
        """
        return None if self.is_super_admin else self.organization_id

    def can_manage(self) -> bool:
        return self.role in MANAGE_ROLES

    def can_access_org(self, org_id: Optional[int]) -> bool:
        """True if this principal may act on a resource in the given organization."""
        if self.is_super_admin:
            return True
        if org_id is None:
            return False
        return org_id == self.organization_id
