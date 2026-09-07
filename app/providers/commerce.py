"""Read-only commerce analytics over the synthetic warehouse."""

from __future__ import annotations

from typing import Any

from app.analytics.engine import run_query
from app.analytics.warehouse import Warehouse
from app.providers.data import COHORTS, DAILY_COMMERCE, PRODUCTS
from app.providers.protocol import DataSource


class CommerceProvider:
    name = DataSource.COMMERCE

    def __init__(self, warehouse: Warehouse | None = None) -> None:
        self.warehouse = warehouse or Warehouse()

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "commerce_order_totals",
                "description": "Orders, revenue and refunds for a date range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "required": ["start_date", "end_date"],
                },
            },
            {
                "type": "function",
                "name": "commerce_product_catalog",
                "description": "List the fictional product catalog.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "type": "function",
                "name": "commerce_cohort_ltv",
                "description": (
                    "Cohort LTV at 12/24/36 months. Incomplete horizons "
                    "return null rather than a partial number."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"cohort_month": {"type": "string"}},
                },
            },
            {
                "type": "function",
                "name": "analytics_query",
                "description": "Run a contract-bounded warehouse query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metrics": {"type": "array", "items": {"type": "string"}},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "required": ["metrics", "start_date", "end_date"],
                },
            },
        ]

    async def execute(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool == "commerce_product_catalog":
            return {"ok": True, "products": list(PRODUCTS)}
        if tool == "commerce_cohort_ltv":
            month = str(arguments.get("cohort_month") or "")
            rows = [row for row in COHORTS if not month or row["cohort_month"] == month]
            return {"ok": True, "cohorts": rows, "note": "null means the horizon is not complete"}
        if tool == "commerce_order_totals":
            start = str(arguments.get("start_date") or "")
            end = str(arguments.get("end_date") or "")
            rows = [row for row in DAILY_COMMERCE if start <= str(row["day"]) <= end]
            return {
                "ok": True,
                "start_date": start,
                "end_date": end,
                "orders": sum(int(row["orders"]) for row in rows),
                "gross_revenue": round(sum(float(row["gross_revenue"]) for row in rows), 2),
                "net_revenue": round(sum(float(row["net_revenue"]) for row in rows), 2),
                "refunds": sum(int(row["refunds"]) for row in rows),
                "days": len(rows),
            }
        if tool == "analytics_query":
            return run_query(
                self.warehouse,
                metrics=list(arguments.get("metrics") or []),
                start_date=str(arguments.get("start_date") or ""),
                end_date=str(arguments.get("end_date") or ""),
            )
        return {"ok": False, "error": f"unknown tool {tool}"}
