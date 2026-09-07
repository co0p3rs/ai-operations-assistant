from __future__ import annotations

from typing import Any

from app.providers.data import INVENTORY
from app.providers.protocol import DataSource


class InventoryProvider:
    name = DataSource.INVENTORY

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "inventory_on_hand",
                "description": "Current on-hand and days-of-cover by SKU and warehouse.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "warehouse": {"type": "string"},
                    },
                },
            }
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "inventory_on_hand":
            return {"ok": False, "error": f"unknown tool {tool}"}
        sku = str(arguments.get("sku") or "")
        warehouse = str(arguments.get("warehouse") or "")
        rows = [
            row
            for row in INVENTORY
            if (not sku or row["sku"] == sku)
            and (not warehouse or row["warehouse"] == warehouse)
        ]
        low = [row for row in rows if int(row["days_cover"]) < 7]
        return {"ok": True, "rows": rows, "low_cover": low}
