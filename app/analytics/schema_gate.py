"""Refuse to answer from a warehouse whose shape the compiler does not know.

A sync that renames `net_revenue` to `net_sales`, or a migration that has
not run yet after a deploy, does not always fail loudly. `row.get()` returns
zero, and zero revenue looks like a bad day, not a broken pipeline.

The compiler declares the columns it reads. The gate compares that against
what the warehouse actually holds and fingerprints the result, so drift is
a 503 with the missing columns named, never a plausible wrong number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.analytics.warehouse import Warehouse

REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "daily_commerce": frozenset(
        {"day", "orders", "gross_revenue", "net_revenue", "new_customers", "refunds"}
    ),
    "web_daily": frozenset({"day", "sessions", "purchases"}),
    "cohorts": frozenset(
        {"cohort_month", "horizon_complete_months", "ltv_12_month", "ltv_24_month", "ltv_36_month"}
    ),
    "inventory": frozenset({"on_hand"}),
}


@dataclass(frozen=True)
class SchemaCheck:
    ok: bool
    fingerprint: str
    missing: dict[str, list[str]]


def actual_columns(warehouse: Warehouse) -> dict[str, frozenset[str]]:
    tables = {
        "daily_commerce": warehouse.daily_commerce,
        "web_daily": warehouse.web_daily,
        "cohorts": warehouse.cohorts,
        "inventory": warehouse.inventory,
    }
    # Every row, not the first: a partial backfill can leave old-shaped rows.
    return {
        name: frozenset.intersection(*(frozenset(row) for row in rows)) if rows else frozenset()
        for name, rows in tables.items()
    }


def fingerprint(columns: dict[str, frozenset[str]]) -> str:
    canonical = json.dumps(
        {name: sorted(cols) for name, cols in sorted(columns.items())}, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def check_schema(warehouse: Warehouse) -> SchemaCheck:
    actual = actual_columns(warehouse)
    missing = {
        table: sorted(required - actual.get(table, frozenset()))
        for table, required in REQUIRED_COLUMNS.items()
        if required - actual.get(table, frozenset())
    }
    return SchemaCheck(ok=not missing, fingerprint=fingerprint(actual), missing=missing)
