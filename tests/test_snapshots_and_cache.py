"""Snapshot layer and the stale-while-revalidate dashboard cache."""

import asyncio
from datetime import date

from app.analytics.engine import run_query
from app.analytics.snapshots import SnapshotLayer
from app.analytics.warehouse import Warehouse
from app.bi_api import CACHE, WAREHOUSE, WAREHOUSE_SOURCE, sync_snapshot
from app.dashboard_cache import DashboardCache


def _facts() -> list[dict[str, object]]:
    return [
        {"day": f"2026-08-{d:02d}", "orders": 10, "gross_revenue": 1000.0, "net_revenue": 900.0,
         "new_customers": 3, "refunds": 0}
        for d in range(1, 11)
    ]


def test_reads_sum_the_snapshot_not_the_raw_facts() -> None:
    warehouse = Warehouse()
    raw = [r for r in warehouse.daily_commerce if "2026-08-10" <= str(r["day"]) <= "2026-08-20"]
    result = run_query(warehouse, metrics=["orders", "gross_revenue"], start_date="2026-08-10", end_date="2026-08-20")
    assert result["metrics"]["orders"] == sum(float(r["orders"]) for r in raw)
    # Change the facts without refreshing: readers keep the snapshot's answer.
    warehouse.daily_commerce[0] = {**warehouse.daily_commerce[0], "orders": 9_999}
    again = run_query(warehouse, metrics=["orders"], start_date="2026-08-10", end_date="2026-08-20")
    assert again["metrics"]["orders"] == result["metrics"]["orders"]


def test_incremental_refresh_rewrites_only_the_trailing_window() -> None:
    facts = _facts()
    layer = SnapshotLayer(facts=lambda: facts)
    layer.rebuild()
    generation = layer.generation

    facts[9] = {**facts[9], "refunds": 2}  # a late refund inside the window (Aug 10)
    facts[0] = {**facts[0], "orders": 99}  # history rewritten outside it (Aug 1)
    result = layer.refresh(last_day=date(2026, 8, 10), days=3)

    assert result.changed_days == ("2026-08-10",)
    assert layer.rows["2026-08-10"]["refunds"] == 2
    assert layer.rows["2026-08-01"]["orders"] == 10  # not yet: outside the window
    assert layer.generation == generation + 1


def test_full_rebuild_reports_drift_the_window_could_not_see() -> None:
    facts = _facts()
    layer = SnapshotLayer(facts=lambda: facts)
    layer.rebuild()
    facts[0] = {**facts[0], "orders": 99}
    result = layer.rebuild()
    assert result.drift_days == ("2026-08-01",)
    assert layer.rows["2026-08-01"]["orders"] == 99


def test_an_unchanged_refresh_does_not_invalidate_anything() -> None:
    layer = SnapshotLayer(facts=_facts)
    layer.rebuild()
    generation = layer.generation
    assert layer.refresh(last_day=date(2026, 8, 10)).changed_days == ()
    assert layer.generation == generation


async def test_cache_is_valid_until_its_data_changes() -> None:
    cache = DashboardCache()
    builds = 0

    async def producer() -> dict[str, int]:
        nonlocal builds
        builds += 1
        return {"value": builds}

    first, info = await cache.get("overview", {"days": 30}, ("commerce",), producer)
    assert (first, info.hit) == ({"value": 1}, False)
    second, info = await cache.get("overview", {"days": 30}, ("commerce",), producer)
    assert (second, info.hit) == ({"value": 1}, True)
    cache.bump("ads")  # a source this response does not read
    _same, info = await cache.get("overview", {"days": 30}, ("commerce",), producer)
    assert info.hit
    cache.bump("commerce")
    third, info = await cache.get("overview", {"days": 30}, ("commerce",), producer)
    assert (third, info.hit) == ({"value": 2}, False)


async def test_one_builder_per_shape_and_everyone_else_gets_the_last_answer() -> None:
    cache = DashboardCache()
    release = asyncio.Event()
    builds = 0

    async def slow() -> dict[str, int]:
        nonlocal builds
        builds += 1
        await release.wait()
        return {"value": builds}

    async def fast() -> dict[str, int]:
        return {"value": 0}

    await cache.get("overview", {}, ("commerce",), fast)  # last good answer
    cache.bump("commerce")
    builder = asyncio.create_task(cache.get("overview", {}, ("commerce",), slow))
    await asyncio.sleep(0)
    # A viewer arriving mid-rebuild is served the previous answer at once.
    viewer, info = await cache.get("overview", {}, ("commerce",), slow)
    assert viewer == {"value": 0}
    assert info.stale
    release.set()
    built, info = await builder
    assert built == {"value": 1}
    assert builds == 1
    fresh, info = await cache.get("overview", {}, ("commerce",), slow)
    assert (fresh, info.hit, info.stale) == ({"value": 1}, True, False)


async def test_warm_builds_only_shapes_that_are_not_ready() -> None:
    cache = DashboardCache()

    async def producer() -> dict[str, int]:
        return {"ok": 1}

    shapes = [("overview", {"days": d}, ("commerce",), producer) for d in (7, 30)]
    assert await cache.warm(shapes) == 2
    assert await cache.warm(shapes) == 0


def test_bi_query_reports_cache_hits_and_a_changed_snapshot_invalidates_it(client) -> None:
    body = {"metrics": ["orders"], "start_date": "2026-08-10", "end_date": "2026-08-20"}
    headers = {"authorization": "Bearer local-bi-token"}
    first = client.post("/bi/query", json=body, headers=headers).json()
    second = client.post("/bi/query", json=body, headers=headers).json()
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True

    generation = CACHE.generations.get(WAREHOUSE_SOURCE, 0)
    original = list(WAREHOUSE.daily_commerce)
    try:
        latest = max(WAREHOUSE.snapshot.rows)
        WAREHOUSE.daily_commerce[:] = [
            {**row, "orders": float(row["orders"]) + 1} if row["day"] == latest else row
            for row in WAREHOUSE.daily_commerce
        ]
        assert sync_snapshot().changed_days == (latest,)
        assert CACHE.generations[WAREHOUSE_SOURCE] == generation + 1
        third = client.post("/bi/query", json=body, headers=headers).json()
        assert third["cache"]["hit"] is False
    finally:
        WAREHOUSE.daily_commerce[:] = original
        sync_snapshot(full=True)


def test_nightly_digest_names_snapshot_drift(client) -> None:
    original = list(WAREHOUSE.daily_commerce)
    try:
        oldest = min(WAREHOUSE.snapshot.rows)
        WAREHOUSE.daily_commerce[:] = [
            {**row, "refunds": float(row["refunds"]) + 1} if row["day"] == oldest else row
            for row in WAREHOUSE.daily_commerce
        ]
        report = client.post("/admin/housekeeping", params={"email": "admin@northstar.example"}).json()
        assert "snapshot drift on 1 day(s)" in report["digest"]
    finally:
        WAREHOUSE.daily_commerce[:] = original
        sync_snapshot(full=True)
