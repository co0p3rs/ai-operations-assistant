import pytest

from app.access import Permission, Role, UserAccess
from app.providers.registry import build_registry


def _access(*permissions: Permission) -> UserAccess:
    return UserAccess(
        user_id="U1",
        email="user@northstar.example",
        role=Role.USER,
        explicit_permissions=frozenset(permissions),
    )


@pytest.mark.asyncio
async def test_denied_tool_does_not_run() -> None:
    registry = build_registry()
    result = await registry.execute(
        "ads_performance",
        {},
        _access(Permission.COMMERCE_READ),
    )
    assert result == {"ok": False, "error": "permission_denied", "source": "ads"}


@pytest.mark.asyncio
async def test_allowed_tool_returns_synthetic_data() -> None:
    registry = build_registry()
    result = await registry.execute(
        "inventory_on_hand",
        {"sku": "JACKET-ALP"},
        _access(Permission.INVENTORY_READ),
    )
    assert result["ok"] is True
    assert result["low_cover"]


def test_allowed_tools_match_permissions() -> None:
    registry = build_registry()
    names = {tool["name"] for tool in registry.allowed_tools(_access(Permission.SUPPORT_READ))}
    assert names == {"support_summary"}
