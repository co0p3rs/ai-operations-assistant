"""Read a ready answer; refresh it in the background.

The first version computed every dashboard number from order-level facts at
request time. A 366-day overview scanned a year of orders on every open,
the assistant and the BI dashboard each did it separately, and the two could
disagree because they aggregated in slightly different places.

The fix is one daily snapshot that both readers share:

* **Reads never aggregate raw facts.** A query sums at most one row per day.
* **Incremental refresh** rewrites only a trailing window (late refunds and
  cancellations settle for a few days), so it is cheap enough to run every
  few minutes.
* **A nightly full rebuild** recomputes everything and reports which days
  drifted outside that window. A non-empty drift list means the window is
  too short or an upstream rewrote history; it is a signal, not noise.
* **A generation counter** changes only when a row actually changed, so the
  dashboard cache (`app/dashboard_cache.py`) is invalidated by data, not by
  the clock.

Derived ratios (AOV, refund rate) are never stored: they are computed from
stored sums at read time, so a snapshot cannot hold an average of averages.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

ADDITIVE_FIELDS = ("orders", "gross_revenue", "net_revenue", "new_customers", "refunds")
INCREMENTAL_DAYS = 3

FactsSource = Callable[[], Iterable[dict[str, object]]]


@dataclass(frozen=True)
class RefreshResult:
    mode: str
    days_written: int
    changed_days: tuple[str, ...]
    # Full rebuild only: days whose stored value had drifted from the facts.
    drift_days: tuple[str, ...] = ()


@dataclass
class SnapshotLayer:
    facts: FactsSource
    rows: dict[str, dict[str, float]] = field(default_factory=dict)
    generation: int = 0

    def rows_between(self, start: date, end: date) -> list[dict[str, object]]:
        first, last = start.isoformat(), end.isoformat()
        return [
            {"day": day, **values}
            for day, values in sorted(self.rows.items())
            if first <= day <= last
        ]

    def refresh(self, *, last_day: date, days: int = INCREMENTAL_DAYS) -> RefreshResult:
        """Rewrite the trailing `days` ending `last_day`; leave older days alone."""
        first = (last_day - timedelta(days=days - 1)).isoformat()
        fresh = {
            day: values
            for day, values in _aggregate(self.facts()).items()
            if first <= day <= last_day.isoformat()
        }
        changed = tuple(sorted(day for day, values in fresh.items() if self.rows.get(day) != values))
        self.rows.update(fresh)
        if changed:
            self.generation += 1
        return RefreshResult("incremental", len(fresh), changed)

    def rebuild(self) -> RefreshResult:
        """Recompute every day and report what had drifted."""
        fresh = _aggregate(self.facts())
        changed = tuple(
            sorted(day for day in fresh.keys() | self.rows.keys() if self.rows.get(day) != fresh.get(day))
        )
        drift = tuple(day for day in changed if day in self.rows)
        self.rows = fresh
        if changed:
            self.generation += 1
        return RefreshResult("full", len(fresh), changed, drift)


def _aggregate(facts: Iterable[dict[str, object]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for fact in facts:
        day = str(fact["day"])
        bucket = out.setdefault(day, {name: 0.0 for name in ADDITIVE_FIELDS})
        for name in ADDITIVE_FIELDS:
            bucket[name] = round(bucket[name] + float(fact.get(name) or 0), 2)
    return out
