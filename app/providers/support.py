from __future__ import annotations

from typing import Any

from app.providers.data import SUPPORT_SUMMARY
from app.providers.protocol import DataSource


class SupportProvider:
    name = DataSource.SUPPORT

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "support_summary",
                "description": "Aggregate support health. No ticket or customer detail.",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "support_summary":
            return {"ok": False, "error": f"unknown tool {tool}"}
        return {"ok": True, **SUPPORT_SUMMARY}
