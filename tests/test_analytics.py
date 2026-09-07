from app.analytics.contracts import ContractValidationError, parse_metrics
from app.analytics.engine import run_query
from app.analytics.warehouse import Warehouse


def test_unknown_metric_is_rejected() -> None:
    try:
        parse_metrics(["not_a_metric"])
    except ContractValidationError as exc:
        assert "unknown metric" in str(exc)
    else:
        raise AssertionError("expected ContractValidationError")


def test_query_returns_contract_payload() -> None:
    result = run_query(
        Warehouse(),
        metrics=["orders", "gross_revenue", "average_order_value"],
        start_date="2026-08-04",
        end_date="2026-08-31",
    )
    assert result["ok"] is True
    assert result["contract_version"] == "v1"
    assert result["metrics"]["orders"] > 0
    assert result["metrics"]["average_order_value"] > 0


def test_inverted_range_is_a_contract_violation() -> None:
    result = run_query(
        Warehouse(),
        metrics=["orders"],
        start_date="2026-08-31",
        end_date="2026-08-01",
    )
    assert result["ok"] is False
    assert result["error"] == "contract_violation"


def test_ltv_ignores_incomplete_horizons() -> None:
    warehouse = Warehouse()
    result = run_query(
        warehouse,
        metrics=["ltv_36_month"],
        start_date="2026-08-01",
        end_date="2026-08-31",
    )
    assert result["ok"] is True
    assert result["metrics"]["ltv_36_month"] is None

    twelve = run_query(
        warehouse,
        metrics=["ltv_12_month"],
        start_date="2026-08-01",
        end_date="2026-08-31",
    )
    assert twelve["metrics"]["ltv_12_month"] == 214.5
