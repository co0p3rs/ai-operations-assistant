from __future__ import annotations

from typing import Any

from app.providers.data import WEB_DAILY
from app.providers.protocol import DataSource


class WebAnalyticsProvider:
    name = DataSource.WEB_ANALYTICS

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "web_analytics_overview",
                "description": "Sessions, purchases and conversion for a date range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "required": ["start_date", "end_date"],
                },
            }
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool != "web_analytics_overview":
            return {"ok": False, "error": f"unknown tool {tool}"}
        start = str(arguments.get("start_date") or "")
        end = str(arguments.get("end_date") or "")
        rows = [row for row in WEB_DAILY if start <= str(row["day"]) <= end]
        sessions = sum(int(row["sessions"]) for row in rows)
        purchases = sum(int(row["purchases"]) for row in rows)
        return {
            "ok": True,
            "sessions": sessions,
            "purchases": purchases,
            "revenue": round(sum(float(row["revenue"]) for row in rows), 2),
            "conversion_rate": round(purchases / sessions, 4) if sessions else 0.0,
            "days": len(rows),
        }
