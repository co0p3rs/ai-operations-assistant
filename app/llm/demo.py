"""Deterministic local model so the demo and tests run without API keys.

It is not a language model. It picks tools from the routed intent, executes
them, and writes a short answer from the payloads. That is enough to exercise
RBAC, evidence checks, and the webhook path on a laptop.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.llm.types import AssistantReply
from app.routing import Intent

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

INTENT_TOOLS: dict[Intent, tuple[str, dict[str, Any]]] = {
    Intent.COMMERCE: (
        "commerce_order_totals",
        {"start_date": "2026-08-04", "end_date": "2026-08-31"},
    ),
    Intent.COHORT: ("commerce_cohort_ltv", {}),
    Intent.WEB: (
        "web_analytics_overview",
        {"start_date": "2026-08-04", "end_date": "2026-08-31"},
    ),
    Intent.ADS: ("ads_performance", {}),
    Intent.INVENTORY: ("inventory_on_hand", {}),
    Intent.SUPPORT: ("support_summary", {}),
    Intent.WORK: ("work_open_tasks", {}),
    Intent.ANALYTICS: (
        "analytics_query",
        {
            "metrics": ["orders", "gross_revenue"],
            "start_date": "2026-08-04",
            "end_date": "2026-08-31",
        },
    ),
}


async def run_demo_model(
    *,
    question: str,
    intent: Intent,
    tools: list[dict[str, Any]],
    execute: ToolExecutor,
) -> AssistantReply:
    allowed = {str(tool["name"]) for tool in tools}
    planned = INTENT_TOOLS.get(intent)
    if planned is None or planned[0] not in allowed:
        return AssistantReply(
            text=(
                "I don't have permission to query the source that question needs. "
                "Ask an administrator if you should have access."
            ),
            provider="demo",
        )

    name, arguments = planned
    result = await execute(name, arguments)
    successful = {name} if result.get("ok") else set()
    return AssistantReply(
        text=_render(intent, result),
        provider="demo",
        successful_tools=successful,
        tool_results=[{"tool": name, "result": result}],
    )


def _render(intent: Intent, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"The {intent.value} source did not return a usable result."
    if intent is Intent.COMMERCE:
        return (
            f"Commerce reports {result.get('orders')} orders and "
            f"${result.get('gross_revenue')} gross revenue over "
            f"{result.get('days')} days."
        )
    if intent is Intent.COHORT:
        rows = result.get("cohorts") or []
        if not rows:
            return "No matching cohorts."
        parts = []
        for row in rows:
            ltv = row.get("ltv_12_month")
            label = f"${ltv}" if ltv is not None else "not yet complete"
            parts.append(f"{row['cohort_month']}: 12-month LTV {label}")
        return "Cohort LTV (null means the horizon is incomplete): " + "; ".join(parts)
    if intent is Intent.WEB:
        return (
            f"WebAnalytics shows {result.get('sessions')} sessions, "
            f"{result.get('purchases')} purchases, conversion "
            f"{result.get('conversion_rate')}."
        )
    if intent is Intent.ADS:
        return (
            f"Ads spend ${result.get('spend')} produced ${result.get('revenue')} "
            f"attributed revenue (ROAS {result.get('roas')})."
        )
    if intent is Intent.INVENTORY:
        low = result.get("low_cover") or []
        if low:
            skus = ", ".join(f"{row['sku']}@{row['warehouse']}" for row in low)
            return f"Inventory is low (<7 days cover) for {skus}."
        return "Inventory cover is healthy across tracked SKUs."
    if intent is Intent.SUPPORT:
        return (
            f"Support has {result.get('open_tickets')} open tickets, "
            f"CSAT {result.get('csat')}, first response "
            f"{result.get('first_response_hours')} hours."
        )
    if intent is Intent.WORK:
        tasks = result.get("tasks") or []
        if not tasks:
            return "No open work items."
        titles = ", ".join(item["title"] for item in tasks)
        return f"Open work items: {titles}."
    if intent is Intent.ANALYTICS:
        metrics = result.get("metrics") or {}
        return f"Warehouse contract {result.get('contract_version')} returned {metrics}."
    return "I need a more specific question about commerce, ads, inventory, support, or work."
