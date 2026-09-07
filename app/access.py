"""Deny-by-default role-based access control.

A role is not a bag of integrations. Users start with nothing. Admins can
manage other users but do not automatically see business data. Super-admins
see everything. Extra sources are explicit grants.
"""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class Permission(StrEnum):
    ADMIN_USERS_MANAGE = "admin.users.manage"
    COMMERCE_READ = "commerce.read"
    WEB_ANALYTICS_READ = "web_analytics.read"
    ADS_READ = "ads.read"
    INVENTORY_READ = "inventory.read"
    SUPPORT_READ = "support.read"
    WORK_READ = "work.read"


ALL_PERMISSIONS = frozenset(Permission)
ASSIGNABLE_PERMISSIONS = ALL_PERMISSIONS - {Permission.ADMIN_USERS_MANAGE}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.USER: frozenset(),
    Role.ADMIN: frozenset({Permission.ADMIN_USERS_MANAGE}),
    Role.SUPER_ADMIN: ALL_PERMISSIONS,
}


@dataclass(frozen=True)
class UserAccess:
    user_id: str
    email: str
    role: Role
    explicit_permissions: frozenset[Permission]
    is_active: bool = True
    display_name: str = ""

    @property
    def effective_permissions(self) -> frozenset[Permission]:
        if not self.is_active:
            return frozenset()
        return ROLE_PERMISSIONS[self.role] | self.explicit_permissions

    def has(self, permission: Permission) -> bool:
        return permission in self.effective_permissions


def can_manage_users(access: UserAccess) -> bool:
    return access.has(Permission.ADMIN_USERS_MANAGE)


def can_manage_target(actor: UserAccess, target: UserAccess) -> bool:
    """Admins manage users. Only super-admins manage other admins."""
    if not actor.is_active:
        return False
    if actor.role is Role.SUPER_ADMIN:
        return True
    return actor.role is Role.ADMIN and target.role is Role.USER


def can_assign_role(actor: UserAccess, role: Role) -> bool:
    if not actor.is_active:
        return False
    if actor.role is Role.SUPER_ADMIN:
        return True
    return actor.role is Role.ADMIN and role is Role.USER
