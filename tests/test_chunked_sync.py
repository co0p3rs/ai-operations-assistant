"""Reproduces the pagination bug and proves the chunked pull does not have it."""

import random
from datetime import date, timedelta
from typing import Any

import pytest

from app.sync.chunked import IncompleteReportError, fetch_unpaged, reconcile, replace_window

FIRST = date(2026, 8, 1)
LAST = date(2026, 8, 28)


class TiedSpendApi:
    """A grouped report paged in spend order, like the upstreams that broke.

    Most rows cost exactly the same (one unit at list price). Ties come back in a different
    order on every request, as they do from a database without a unique
    tiebreaker, so consecutive pages overlap and some rows are never served.
    """

    def __init__(self, rows_per_day: int = 30) -> None:
        self.rows = [
            {"day": (FIRST + timedelta(days=d)).isoformat(), "station": f"S{s:02d}", "spend": 93.0 if s % 5 else 450.0}
            for d in range((LAST - FIRST).days + 1)
            for s in range(rows_per_day)
        ]
        self.calls = 0

    def total(self, start: date, end: date) -> float:
        return sum(r["spend"] for r in self._window(start, end))

    def _window(self, start: date, end: date) -> list[dict[str, Any]]:
        return [r for r in self.rows if start.isoformat() <= r["day"] <= end.isoformat()]

    async def __call__(self, start: date, end: date, page: int, page_size: int) -> dict[str, Any]:
        self.calls += 1
        window = self._window(start, end)
        shuffled = window[:]
        random.Random(self.calls).shuffle(shuffled)  # unstable order among ties
        ordered = sorted(shuffled, key=lambda r: -r["spend"])
        offset = (page - 1) * page_size
        return {"rows": ordered[offset : offset + page_size], "total": len(window)}


async def _naive_paging(api: TiedSpendApi, page_size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        body = await api(FIRST, LAST, page, page_size)
        rows.extend(body["rows"])
        if len(body["rows"]) < page_size:
            return rows
        page += 1


def _keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(r["day"], r["station"]) for r in rows}


async def test_paging_by_a_tied_sort_key_silently_loses_rows() -> None:
    api = TiedSpendApi()
    rows = await _naive_paging(api, page_size=100)
    assert len(rows) == len(api.rows)  # the row count looks right...
    assert _keys(rows) != _keys(api.rows)  # ...but some rows are duplicates of others


async def test_unpaged_chunks_return_every_row_exactly_once() -> None:
    api = TiedSpendApi()
    rows = await fetch_unpaged(api, FIRST, LAST, page_size=100, chunk_days=7)
    assert sorted(_keys(rows)) == sorted(_keys(api.rows))
    assert len(rows) == len(api.rows)
    reconcile(rows, api.total(FIRST, LAST), "spend")


async def test_a_chunk_that_overflows_a_page_is_halved_not_paged() -> None:
    api = TiedSpendApi(rows_per_day=30)
    rows = await fetch_unpaged(api, FIRST, LAST, page_size=70, chunk_days=7)
    assert sorted(_keys(rows)) == sorted(_keys(api.rows))


async def test_a_single_day_beyond_one_page_is_refused() -> None:
    api = TiedSpendApi(rows_per_day=30)
    with pytest.raises(IncompleteReportError, match="do not fit"):
        await fetch_unpaged(api, FIRST, FIRST, page_size=10)


async def test_reconcile_refuses_a_pull_that_misses_the_source_total() -> None:
    api = TiedSpendApi()
    rows = await _naive_paging(api, page_size=100)
    # Dedupe the way a primary key would on insert.
    stored = list({(r["day"], r["station"]): r for r in rows}.values())
    with pytest.raises(IncompleteReportError, match="source reports"):
        reconcile(stored, api.total(FIRST, LAST), "spend")


def test_replace_window_drops_rows_the_upstream_no_longer_has() -> None:
    table = {
        ("2026-08-01", "S01"): {"day": "2026-08-01", "station": "S01", "spend": 93.0},
        ("2026-08-02", "S01"): {"day": "2026-08-02", "station": "S01", "spend": 93.0},
        ("2026-07-31", "S01"): {"day": "2026-07-31", "station": "S01", "spend": 50.0},
    }
    # Upstream re-keyed Aug 2 to a different station.
    pulled = [
        {"day": "2026-08-01", "station": "S01", "spend": 93.0},
        {"day": "2026-08-02", "station": "S07", "spend": 93.0},
    ]
    result = replace_window(
        table, pulled, first=date(2026, 8, 1), last=date(2026, 8, 2), key=lambda r: (r["day"], r["station"])
    )
    assert ("2026-08-02", "S01") not in result  # a merge would have kept it and double counted
    assert ("2026-08-02", "S07") in result
    assert ("2026-07-31", "S01") in result  # outside the window: untouched
