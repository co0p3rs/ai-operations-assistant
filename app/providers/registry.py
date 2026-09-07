"""Assemble only the tools a user may call on sources that exist."""

from __future__ import annotations

from typing import Any

from app.access import UserAccess
from app.providers.ads import AdsProvider
from app.providers.commerce import CommerceProvider
from app.providers.inventory import InventoryProvider
from app.providers.protocol import SOURCE_PERMISSION, DataSource, Provider
from app.providers.support import SupportProvider
from app.providers.web_analytics import WebAnalyticsProvider
from app.providers.work import WorkProvider

TOOL_SOURCE: dict[str, DataSource] = {
    "commerce_order_totals": DataSource.COMMERCE,
    "commerce_product_catalog": DataSource.COMMERCE,
    "commerce_cohort_ltv": DataSource.COMMERCE,
    "analytics_query": DataSource.COMMERCE,
    "web_analytics_overview": DataSource.WEB_ANALYTICS,
    "ads_performance": DataSource.ADS,
    "inventory_on_hand": DataSource.INVENTORY,
    "support_summary": DataSource.SUPPORT,
    "work_open_tasks": DataSource.WORK,
}


class ProviderRegistry:
    def __init__(self, providers: list[Provider]) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._tools: dict[str, Provider] = {}
        for provider in providers:
            for tool in provider.tools():
                self._tools[str(tool["name"])] = provider

    def allowed_tools(self, access: UserAccess) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for provider in self._providers.values():
            if access.has(SOURCE_PERMISSION[provider.name]):
                tools.extend(provider.tools())
        return tools

    async def execute(
        self,
        tool: str,
        arguments: dict[str, Any],
        access: UserAccess,
    ) -> dict[str, Any]:
        source = TOOL_SOURCE.get(tool)
        if source is None:
            return {"ok": False, "error": "unknown_tool"}
        if not access.has(SOURCE_PERMISSION[source]):
            return {"ok": False, "error": "permission_denied", "source": source.value}
        provider = self._tools.get(tool)
        if provider is None:
            return {"ok": False, "error": "unknown_tool"}
        return await provider.execute(tool, arguments)


def build_registry() -> ProviderRegistry:
    return ProviderRegistry(
        [
            CommerceProvider(),
            WebAnalyticsProvider(),
            AdsProvider(),
            InventoryProvider(),
            SupportProvider(),
            WorkProvider(),
        ]
    )
