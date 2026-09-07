"""Synthetic Northstar Outfitters catalog.

Every number in this module is invented. There is no live store, no real
customer, and no employer dataset behind it.
"""

from __future__ import annotations

from datetime import date, timedelta

TODAY = date(2026, 9, 1)

PRODUCTS = (
    {"sku": "FLASK-32", "name": "Trail Flask 32oz", "category": "hydration", "price": 34.00},
    {"sku": "JACKET-ALP", "name": "Alpine Shell Jacket", "category": "apparel", "price": 189.00},
    {"sku": "PACK-40", "name": "Summit Pack 40L", "category": "packs", "price": 149.00},
    {"sku": "LAMP-200", "name": "Ridge Headlamp", "category": "lighting", "price": 42.00},
)

WAREHOUSES = ("east", "west")

# Daily commercial facts for the last 28 complete days ending yesterday.
def _day(offset: int) -> str:
    return (TODAY - timedelta(days=offset)).isoformat()


DAILY_COMMERCE: list[dict[str, object]] = []
for day in range(1, 29):
    stamp = _day(day)
    # A gentle weekly shape so charts and period comparisons are not flat.
    weekend = date.fromisoformat(stamp).weekday() >= 5
    base_orders = 42 if not weekend else 28
    DAILY_COMMERCE.append(
        {
            "day": stamp,
            "orders": base_orders + (day % 5),
            "gross_revenue": round((base_orders + (day % 5)) * 96.4, 2),
            "net_revenue": round((base_orders + (day % 5)) * 88.1, 2),
            "new_customers": 11 + (day % 4),
            "refunds": 2 if day % 7 == 0 else 1,
        }
    )

# First-order month -> later spend. Incomplete horizons stay incomplete.
COHORTS = (
    {
        "cohort_month": "2024-01",
        "customers": 180,
        "ltv_12_month": 214.50,
        "ltv_24_month": 286.10,
        "ltv_36_month": None,
        "horizon_complete_months": 20,
    },
    {
        "cohort_month": "2025-01",
        "customers": 240,
        "ltv_12_month": 198.20,
        "ltv_24_month": None,
        "ltv_36_month": None,
        "horizon_complete_months": 8,
    },
    {
        "cohort_month": "2026-01",
        "customers": 310,
        "ltv_12_month": None,
        "ltv_24_month": None,
        "ltv_36_month": None,
        "horizon_complete_months": 8,
    },
)

WEB_DAILY = [
    {
        "day": row["day"],
        "sessions": int(row["orders"]) * 18 + 120,  # type: ignore[arg-type]
        "purchases": row["orders"],
        "revenue": row["gross_revenue"],
    }
    for row in DAILY_COMMERCE
]

ADS_CAMPAIGNS = (
    {
        "account": "brand",
        "campaign": "evergreen-search",
        "spend": 1840.00,
        "clicks": 2210,
        "conversions": 96,
        "revenue": 9120.00,
    },
    {
        "account": "prospecting",
        "campaign": "lookalike-summer",
        "spend": 2630.00,
        "clicks": 4480,
        "conversions": 74,
        "revenue": 7010.00,
    },
)

INVENTORY = (
    {"sku": "FLASK-32", "warehouse": "east", "on_hand": 420, "available": 390, "days_cover": 18},
    {"sku": "FLASK-32", "warehouse": "west", "on_hand": 210, "available": 180, "days_cover": 9},
    {"sku": "JACKET-ALP", "warehouse": "east", "on_hand": 80, "available": 64, "days_cover": 6},
    {"sku": "JACKET-ALP", "warehouse": "west", "on_hand": 40, "available": 22, "days_cover": 3},
    {"sku": "PACK-40", "warehouse": "east", "on_hand": 150, "available": 140, "days_cover": 12},
    {"sku": "PACK-40", "warehouse": "west", "on_hand": 95, "available": 90, "days_cover": 11},
    {"sku": "LAMP-200", "warehouse": "east", "on_hand": 600, "available": 580, "days_cover": 40},
    {"sku": "LAMP-200", "warehouse": "west", "on_hand": 540, "available": 520, "days_cover": 38},
)

SUPPORT_SUMMARY = {
    "open_tickets": 17,
    "first_response_hours": 3.4,
    "resolution_hours": 18.2,
    "csat": 0.91,
    "contact_rate": 0.042,
}

WORK_ITEMS = (
    {"id": "TASK-104", "title": "Reorder Alpine Shell — west warehouse", "assignee": "Reese Operator", "status": "open"},
    {"id": "TASK-118", "title": "Review lookalike-summer CPA", "assignee": "Reese Operator", "status": "open"},
    {"id": "TASK-121", "title": "Publish fall pack landing page", "assignee": "Avery Viewer", "status": "done"},
)
