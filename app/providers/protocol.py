"""Provider identifiers and the permission each one requires."""

from enum import StrEnum
from typing import Any, Protocol

from app.access import Permission


class DataSource(StrEnum):
    COMMERCE = "commerce"
    WEB_ANALYTICS = "web_analytics"
    ADS = "ads"
    INVENTORY = "inventory"
    SUPPORT = "support"
    WORK = "work"


SOURCE_DISPLAY = {
    DataSource.COMMERCE: "Commerce",
    DataSource.WEB_ANALYTICS: "WebAnalytics",
    DataSource.ADS: "Ads",
    DataSource.INVENTORY: "Inventory",
    DataSource.SUPPORT: "Support",
    DataSource.WORK: "Work",
}

SOURCE_PERMISSION = {
    DataSource.COMMERCE: Permission.COMMERCE_READ,
    DataSource.WEB_ANALYTICS: Permission.WEB_ANALYTICS_READ,
    DataSource.ADS: Permission.ADS_READ,
    DataSource.INVENTORY: Permission.INVENTORY_READ,
    DataSource.SUPPORT: Permission.SUPPORT_READ,
    DataSource.WORK: Permission.WORK_READ,
}


class Provider(Protocol):
    name: DataSource

    def tools(self) -> list[dict[str, Any]]: ...

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
