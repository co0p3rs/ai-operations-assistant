from datetime import datetime

from app.analytics.schema_gate import check_schema
from app.analytics.warehouse import Warehouse
from app.bi_api import WAREHOUSE
from app.housekeeping import run_housekeeping, source_health
from app.outbox import AnswerOutbox, LogPoster
from app.store import EventStore


def test_seeded_warehouse_passes() -> None:
    result = check_schema(Warehouse())
    assert result.ok and result.missing == {}


def test_renamed_column_is_drift() -> None:
    warehouse = Warehouse()
    warehouse.daily_commerce = [
        {**{k: v for k, v in row.items() if k != "net_revenue"}, "net_sales": row["net_revenue"]}
        for row in warehouse.daily_commerce
    ]
    result = check_schema(warehouse)
    assert not result.ok
    assert result.missing == {"daily_commerce": ["net_revenue"]}


def test_partial_backfill_is_drift_even_if_first_row_is_fine() -> None:
    warehouse = Warehouse()
    last = dict(warehouse.daily_commerce[-1])
    del last["refunds"]
    warehouse.daily_commerce = [*warehouse.daily_commerce[:-1], last]
    assert check_schema(warehouse).missing == {"daily_commerce": ["refunds"]}


def test_fingerprint_changes_with_shape() -> None:
    before = check_schema(Warehouse()).fingerprint
    warehouse = Warehouse()
    warehouse.inventory = [{**row, "reserved": 0} for row in warehouse.inventory]
    assert check_schema(warehouse).fingerprint != before


def test_bi_query_refuses_on_drift(client) -> None:
    original = WAREHOUSE.web_daily
    WAREHOUSE.web_daily = [{"day": row["day"]} for row in original]
    try:
        response = client.post(
            "/bi/query",
            headers={"authorization": "Bearer local-bi-token"},
            json={"metrics": ["orders"], "start_date": "2026-08-04", "end_date": "2026-08-31"},
        )
    finally:
        WAREHOUSE.web_daily = original
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "schema_drift"


def test_source_health_flags_late_and_missing_syncs() -> None:
    now = datetime.fromisoformat("2026-09-01T12:00:00+00:00").timestamp()
    rows = {
        r.source: r
        for r in source_health(
            {"commerce": "2026-09-01T09:00:00+00:00", "ads": "2026-08-30T12:00:00+00:00"},
            now=now,
        )
    }
    assert rows["commerce"].stale is False
    assert rows["ads"].stale is True and rows["ads"].lag_hours == 48.0
    assert rows["support"].lag_hours is None and rows["support"].stale is True


def test_housekeeping_digest_names_problems() -> None:
    store = EventStore()
    store.claim("evt-h1", now=0)
    report = run_housekeeping(
        store=store,
        outbox=AnswerOutbox(),
        poster=LogPoster(),
        warehouse=Warehouse(),
        syncs={"commerce": "2026-09-01T11:00:00+00:00"},
        now=datetime.fromisoformat("2026-09-01T12:00:00+00:00").timestamp(),
    )
    digest = report.digest()
    assert report.turns_recovered == 1
    assert "4 source(s) late" in digest
    assert "inventory: never synced" in digest
