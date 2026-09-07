from __future__ import annotations

from typing import Any

from app.providers.data import ADS_CAMPAIGNS
from app.providers.protocol import DataSource


class AdsProvider:
    name = DataSource.ADS

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "ads_performance",
                "description": "Paid-media spend, clicks and attributed revenue.",
                "parameters": {
                    "type": "object",
                    "properties": {"account": {"type": "string"}},
                },
            }
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "ads_performance":
            return {"ok": False, "error": f"unknown tool {tool}"}
        account = str(arguments.get("account") or "")
        rows = [row for row in ADS_CAMPAIGNS if not account or row["account"] == account]
        spend = sum(float(row["spend"]) for row in rows)
        revenue = sum(float(row["revenue"]) for row in rows)
        return {
            "ok": True,
            "campaigns": rows,
            "spend": spend,
            "revenue": revenue,
            "roas": round(revenue / spend, 2) if spend else 0.0,
        }
