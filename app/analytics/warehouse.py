"""In-process commerce warehouse seeded with synthetic facts.

The production system mirrors a live store into PostgreSQL so cohort LTV
is computed locally instead of paging an API during a conversation. This
module keeps that shape with a static seed so the public repo never needs
a live store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.data import COHORTS, DAILY_COMMERCE, INVENTORY, WEB_DAILY


@dataclass
class Warehouse:
    daily_commerce: list[dict[str, object]] = field(
        default_factory=lambda: list(DAILY_COMMERCE)
    )
    cohorts: list[dict[str, object]] = field(default_factory=lambda: list(COHORTS))
    web_daily: list[dict[str, object]] = field(default_factory=lambda: list(WEB_DAILY))
    inventory: list[dict[str, object]] = field(default_factory=lambda: list(INVENTORY))

    def freshness_days(self) -> int:
        if not self.daily_commerce:
            return 0
        return len(self.daily_commerce)
