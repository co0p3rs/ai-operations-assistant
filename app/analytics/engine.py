"""Allow-listed compiler from a metric contract to warehouse reads.

The engine never accepts SQL. It maps each metric to a known aggregation
so a confused model cannot invent a join.
"""

from __future__ import annotations

from typing import Any

from app.analytics.contracts import (
    COMMERCE_METRICS,
    CONTRACT_VERSION,
    ContractValidationError,
    Metric,
    parse_iso_date,
    parse_metrics,
    validate_range,
)
from app.analytics.warehouse import Warehouse
from app.providers.data import ADS_CAMPAIGNS


def run_query(
    warehouse: Warehouse,
    *,
    metrics: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    try:
        parsed = parse_metrics(metrics)
        start = parse_iso_date(start_date)
        end = parse_iso_date(end_date)
        validate_range(start, end)
    except ContractValidationError as exc:
        return {"ok": False, "error": "contract_violation", "detail": str(exc)}

    commerce_rows = [
        row
        for row in warehouse.daily_commerce
        if start.isoformat() <= str(row["day"]) <= end.isoformat()
    ]
    web_rows = [
        row
        for row in warehouse.web_daily
        if start.isoformat() <= str(row["day"]) <= end.isoformat()
    ]

    values: dict[str, Any] = {}
    for metric in parsed:
        values[metric.value] = _value(metric, commerce_rows, web_rows, warehouse)

    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": len(commerce_rows),
        "metrics": values,
    }


def _value(
    metric: Metric,
    commerce_rows: list[dict[str, object]],
    web_rows: list[dict[str, object]],
    warehouse: Warehouse,
) -> Any:
    if metric in COMMERCE_METRICS and metric not in {
        Metric.AVERAGE_ORDER_VALUE,
        Metric.LTV_12_MONTH,
        Metric.LTV_24_MONTH,
        Metric.LTV_36_MONTH,
    }:
        return _sum(commerce_rows, metric.value)

    if metric is Metric.AVERAGE_ORDER_VALUE:
        orders = _sum(commerce_rows, "orders")
        revenue = _sum(commerce_rows, "gross_revenue")
        return round(revenue / orders, 2) if orders else 0.0

    if metric is Metric.SESSIONS:
        return _sum(web_rows, "sessions")
    if metric is Metric.CONVERSION_RATE:
        sessions = _sum(web_rows, "sessions")
        purchases = _sum(web_rows, "purchases")
        return round(purchases / sessions, 4) if sessions else 0.0

    if metric is Metric.AD_SPEND:
        return round(sum(float(row["spend"]) for row in ADS_CAMPAIGNS), 2)
    if metric is Metric.RETURN_ON_AD_SPEND:
        spend = sum(float(row["spend"]) for row in ADS_CAMPAIGNS)
        revenue = sum(float(row["revenue"]) for row in ADS_CAMPAIGNS)
        return round(revenue / spend, 2) if spend else 0.0

    if metric is Metric.INVENTORY_ON_HAND:
        return sum(int(row["on_hand"]) for row in warehouse.inventory)

    if metric is Metric.LTV_12_MONTH:
        return _complete_ltv(warehouse, "ltv_12_month", 12)
    if metric is Metric.LTV_24_MONTH:
        return _complete_ltv(warehouse, "ltv_24_month", 24)
    if metric is Metric.LTV_36_MONTH:
        return _complete_ltv(warehouse, "ltv_36_month", 36)
    return None


def _sum(rows: list[dict[str, object]], field: str) -> float:
    return round(sum(float(row[field]) for row in rows), 2)


def _complete_ltv(warehouse: Warehouse, field: str, months: int) -> float | None:
    """Average only cohorts whose horizon is actually complete.

    A 12-month LTV from an eight-month-old cohort is not LTV. Returning
    null is louder and more honest than a number that looks finished.
    """
    ready = [
        float(row[field])
        for row in warehouse.cohorts
        if row[field] is not None and int(row["horizon_complete_months"]) >= months
    ]
    if not ready:
        return None
    return round(sum(ready) / len(ready), 2)
