"""Bounded analytics vocabulary. No SQL, field names, or free-form filters."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

CONTRACT_VERSION = "v1"
MAX_DATE_RANGE_DAYS = 366
MAX_METRICS = 8


class ContractValidationError(ValueError):
    """Raised when a request is outside the allow-listed vocabulary."""


class Metric(StrEnum):
    GROSS_REVENUE = "gross_revenue"
    NET_REVENUE = "net_revenue"
    ORDERS = "orders"
    REFUNDS = "refunds"
    NEW_CUSTOMERS = "new_customers"
    AVERAGE_ORDER_VALUE = "average_order_value"
    LTV_12_MONTH = "ltv_12_month"
    LTV_24_MONTH = "ltv_24_month"
    LTV_36_MONTH = "ltv_36_month"
    SESSIONS = "sessions"
    CONVERSION_RATE = "conversion_rate"
    AD_SPEND = "ad_spend"
    RETURN_ON_AD_SPEND = "return_on_ad_spend"
    INVENTORY_ON_HAND = "inventory_on_hand"


COMMERCE_METRICS = frozenset(
    {
        Metric.GROSS_REVENUE,
        Metric.NET_REVENUE,
        Metric.ORDERS,
        Metric.REFUNDS,
        Metric.NEW_CUSTOMERS,
        Metric.AVERAGE_ORDER_VALUE,
        Metric.LTV_12_MONTH,
        Metric.LTV_24_MONTH,
        Metric.LTV_36_MONTH,
    }
)


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractValidationError(f"invalid date: {value}") from exc


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise ContractValidationError("end_date is before start_date")
    if (end - start).days > MAX_DATE_RANGE_DAYS:
        raise ContractValidationError("date range exceeds 366 days")


def parse_metrics(values: list[str]) -> list[Metric]:
    if not values:
        raise ContractValidationError("at least one metric is required")
    if len(values) > MAX_METRICS:
        raise ContractValidationError(f"at most {MAX_METRICS} metrics")
    metrics: list[Metric] = []
    for value in values:
        try:
            metrics.append(Metric(value))
        except ValueError as exc:
            raise ContractValidationError(f"unknown metric: {value}") from exc
    return metrics


def utc_today() -> date:
    return datetime.now().date()
