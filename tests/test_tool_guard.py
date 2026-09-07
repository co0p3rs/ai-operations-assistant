from app.tool_guard import ToolCallGuard


def test_blocks_day_sliced_repeats() -> None:
    guard = ToolCallGuard(max_similar=2)
    assert guard.register("commerce_order_totals", {"start_date": "2026-08-01"}) is None
    assert guard.register("commerce_order_totals", {"start_date": "2026-08-02"}) is None
    blocked = guard.register("commerce_order_totals", {"start_date": "2026-08-03"})
    assert blocked is not None
    assert blocked["error"] == "repeated_date_sliced_tool_calls_blocked"


def test_reset_clears_counts_for_fallback() -> None:
    guard = ToolCallGuard(max_similar=1)
    guard.register("ads_performance", {})
    assert guard.register("ads_performance", {}) is not None
    guard.reset()
    assert guard.register("ads_performance", {}) is None
