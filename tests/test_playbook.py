import pytest

from app.assistant import answer_event
from app.config import Settings
from app.identity import DEMO_USERS
from app.outbox import OUTBOX, POSTER
from app.playbook import coverage_note, plan_for
from app.providers.protocol import DataSource
from app.providers.registry import build_registry
from app.store import STORE


def test_non_diagnostic_question_has_no_plan() -> None:
    assert plan_for("What was revenue last week?", DEMO_USERS["owner@northstar.example"]) is None


def test_plan_is_ordered_and_permission_scoped() -> None:
    viewer = DEMO_USERS["viewer@northstar.example"]
    plan = plan_for("Why did revenue drop on Tuesday?", viewer)
    assert plan is not None
    assert [s.source for s in plan.allowed] == [DataSource.COMMERCE, DataSource.WEB_ANALYTICS]
    assert DataSource.ADS in {s.source for s in plan.denied}


def test_coverage_note_separates_unchecked_from_forbidden() -> None:
    viewer = DEMO_USERS["viewer@northstar.example"]
    plan = plan_for("Why did orders dip?", viewer)
    note = coverage_note(plan, {"commerce_daily_summary"})
    assert "WebAnalytics (not checked)" in note
    assert "Ads (no access)" in note
    assert "Commerce" not in note


def test_full_coverage_has_no_note() -> None:
    owner = DEMO_USERS["owner@northstar.example"]
    plan = plan_for("why did sales fall", owner)
    tools = {"commerce_x", "ads_x", "web_analytics_x", "inventory_x", "support_x"}
    assert coverage_note(plan, tools) == ""


@pytest.mark.asyncio
async def test_diagnostic_answer_states_gaps_and_is_delivered() -> None:
    claim = STORE.claim("evt-pb-1")
    result = await answer_event(
        event_id="evt-pb-1",
        claim_token=claim.claim_token,
        email="viewer@northstar.example",
        user_id="U_VIEWER",
        text="Why did revenue drop last week?",
        channel="C_OPS",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result["playbook"] is True
    assert "Ads (no access)" in result["answer"]
    assert OUTBOX.get(claim.request_id).channel == "C_OPS"
    assert POSTER.sent[-1]["key"] == claim.request_id


@pytest.mark.asyncio
async def test_fenced_worker_does_not_post() -> None:
    stale = STORE.claim("evt-pb-2", now=0)
    STORE.recover_expired(now=10_000)
    result = await answer_event(
        event_id="evt-pb-2",
        claim_token=stale.claim_token,
        email="viewer@northstar.example",
        user_id="U_VIEWER",
        text="What was revenue last week?",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result == {"ok": False, "error": "claim_lost"}
    assert OUTBOX.get(stale.request_id) is None
