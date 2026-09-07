from app.access import (
    Permission,
    Role,
    UserAccess,
    can_assign_role,
    can_manage_target,
)


def _user(**kwargs: object) -> UserAccess:
    values = {
        "user_id": "U1",
        "email": "user@northstar.example",
        "role": Role.USER,
        "explicit_permissions": frozenset(),
        "is_active": True,
    }
    values.update(kwargs)
    return UserAccess(**values)  # type: ignore[arg-type]


def test_users_start_with_no_permissions() -> None:
    assert _user().effective_permissions == frozenset()


def test_admin_does_not_automatically_see_business_data() -> None:
    admin = _user(role=Role.ADMIN)
    assert admin.has(Permission.ADMIN_USERS_MANAGE)
    assert not admin.has(Permission.COMMERCE_READ)


def test_super_admin_has_everything() -> None:
    owner = _user(role=Role.SUPER_ADMIN)
    assert owner.has(Permission.COMMERCE_READ)
    assert owner.has(Permission.ADS_READ)


def test_inactive_users_have_nothing() -> None:
    user = _user(
        explicit_permissions=frozenset({Permission.COMMERCE_READ}),
        is_active=False,
    )
    assert user.effective_permissions == frozenset()


def test_admins_cannot_manage_other_admins() -> None:
    admin = _user(role=Role.ADMIN, user_id="A")
    other_admin = _user(role=Role.ADMIN, user_id="B")
    user = _user()
    assert can_manage_target(admin, user)
    assert not can_manage_target(admin, other_admin)
    assert not can_assign_role(admin, Role.ADMIN)
