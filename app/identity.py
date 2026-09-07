"""Resolve a chat user to a deny-by-default access record.

The demo directory is seeded with fictional Northstar Outfitters employees.
Unknown emails on the company domain become inactive users with no
permissions. Outside the domain is a hard deny.
"""

from __future__ import annotations

from app.access import Permission, Role, UserAccess
from app.config import Settings

DEMO_USERS: dict[str, UserAccess] = {
    "viewer@northstar.example": UserAccess(
        user_id="U_VIEWER",
        email="viewer@northstar.example",
        role=Role.USER,
        explicit_permissions=frozenset(
            {Permission.COMMERCE_READ, Permission.WEB_ANALYTICS_READ}
        ),
        display_name="Avery Viewer",
    ),
    "operator@northstar.example": UserAccess(
        user_id="U_OPERATOR",
        email="operator@northstar.example",
        role=Role.USER,
        explicit_permissions=frozenset(
            {
                Permission.COMMERCE_READ,
                Permission.ADS_READ,
                Permission.INVENTORY_READ,
                Permission.WORK_READ,
            }
        ),
        display_name="Reese Operator",
    ),
    "support@northstar.example": UserAccess(
        user_id="U_SUPPORT",
        email="support@northstar.example",
        role=Role.USER,
        explicit_permissions=frozenset({Permission.SUPPORT_READ}),
        display_name="Sam Support",
    ),
    "admin@northstar.example": UserAccess(
        user_id="U_ADMIN",
        email="admin@northstar.example",
        role=Role.ADMIN,
        explicit_permissions=frozenset({Permission.COMMERCE_READ}),
        display_name="Jordan Admin",
    ),
    "owner@northstar.example": UserAccess(
        user_id="U_OWNER",
        email="owner@northstar.example",
        role=Role.SUPER_ADMIN,
        explicit_permissions=frozenset(),
        display_name="Casey Owner",
    ),
}

# Also key the directory by the stable chat user id so webhooks can send either.
DEMO_USERS_BY_ID = {user.user_id: user for user in DEMO_USERS.values()}


class IdentityError(Exception):
    """Raised when a webhook sender cannot be given any tools."""


def resolve_access(
    *,
    email: str,
    user_id: str,
    settings: Settings,
) -> UserAccess:
    known = DEMO_USERS.get(email.lower()) or DEMO_USERS_BY_ID.get(user_id)
    if known is not None:
        return known

    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if domain != settings.company_email_domain.lower():
        raise IdentityError("sender is outside the company domain")
    return UserAccess(
        user_id=user_id or "U_UNKNOWN",
        email=email,
        role=Role.USER,
        explicit_permissions=frozenset(),
        is_active=True,
        display_name="",
    )
