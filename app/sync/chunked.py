"""Pull a grouped report from a paged API without trusting its pagination.

Found the hard way on two separate upstream APIs. Both paged their grouped
reports in metric order (spend, revenue). Hundreds of rows tie on that
metric (single-unit rows with an identical price), and with ties the order between two
page requests is not stable: page 2 repeated some rows of page 1 and some
rows never appeared on any page. Nothing errored. The duplicates collapsed
on the primary key when stored, so the warehouse quietly held a slightly
smaller number than the source, and a page-count cap elsewhere had already
stopped one sync at 20,000 of ~25,800 rows for a year.

Three rules replace "page until a short page":

1. **Never page.** Ask for one date chunk per request, small enough to fit
   on a single page. If the API says a chunk holds more rows than it
   returned, halve the chunk and ask again. A single day that still does not
   fit is an error, not a truncation.
2. **Reconcile.** The stored rows must add up to the API's own total for the
   window. A pull that does not is refused before anything is written.
3. **Replace the window.** Delete the pulled date range, then insert. A merge
   keeps rows the upstream has since re-keyed or removed, and they count twice.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Hashable, Iterable
from datetime import date, timedelta
from typing import Any

Row = dict[str, Any]
# fetch(start, end, page, page_size) -> {"rows": [...], "total": int}
PageFetcher = Callable[[date, date, int, int], Awaitable[dict[str, Any]]]

PAGE_SIZE = 500
CHUNK_DAYS = 7


class IncompleteReportError(RuntimeError):
    """The upstream holds more than was pulled. Never store a partial set."""


async def fetch_unpaged(
    fetch: PageFetcher,
    first: date,
    last: date,
    *,
    page_size: int = PAGE_SIZE,
    chunk_days: int = CHUNK_DAYS,
) -> list[Row]:
    rows: list[Row] = []
    start = first
    while start <= last:
        end = min(last, start + timedelta(days=chunk_days - 1))
        rows.extend(await _span(fetch, start, end, page_size))
        start = end + timedelta(days=1)
    return rows


async def _span(fetch: PageFetcher, start: date, end: date, page_size: int) -> list[Row]:
    body = await fetch(start, end, 1, page_size)
    rows = list(body.get("rows") or [])
    total = body.get("total")
    if not isinstance(total, int) or total <= len(rows):
        return rows
    if start >= end:
        raise IncompleteReportError(f"{start}: {total} rows do not fit one page of {page_size}")
    middle = start + (end - start) // 2
    return await _span(fetch, start, middle, page_size) + await _span(
        fetch, middle + timedelta(days=1), end, page_size
    )


def reconcile(rows: Iterable[Row], expected_total: float, field: str, *, tolerance: float = 1.0) -> None:
    stored = sum(float(row.get(field) or 0) for row in rows)
    if abs(stored - expected_total) > tolerance:
        raise IncompleteReportError(
            f"rows sum {field}={stored:,.2f}, the source reports {expected_total:,.2f}"
        )


def replace_window(
    table: dict[Hashable, Row],
    rows: Iterable[Row],
    *,
    first: date,
    last: date,
    key: Callable[[Row], Hashable],
    day_field: str = "day",
) -> dict[Hashable, Row]:
    """Drop every stored row in [first, last], then write the pulled rows."""
    lo, hi = first.isoformat(), last.isoformat()
    kept = {k: v for k, v in table.items() if not lo <= str(v[day_field]) <= hi}
    for row in rows:
        kept[key(row)] = row
    return kept
