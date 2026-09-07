import pytest

from app.assistant import answer_event
from app.config import Settings
from app.providers.registry import build_registry
from app.store import STORE
from app.training import BUFFER


@pytest.mark.asyncio
async def test_viewer_can_read_commerce() -> None:
    claim = STORE.claim("evt-ans-1")
    result = await answer_event(
        event_id="evt-ans-1",
        claim_token=claim.claim_token,
        email="viewer@northstar.example",
        user_id="U_VIEWER",
        text="What was revenue last week?",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result["ok"] is True
    assert "orders" in result["answer"]
    assert STORE.get_trace(claim.request_id) is not None
    assert BUFFER.all()


@pytest.mark.asyncio
async def test_viewer_cannot_read_inventory() -> None:
    claim = STORE.claim("evt-ans-2")
    result = await answer_event(
        event_id="evt-ans-2",
        claim_token=claim.claim_token,
        email="viewer@northstar.example",
        user_id="U_VIEWER",
        text="What is inventory cover for the Alpine jacket?",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result["ok"] is True
    assert "permission" in result["answer"].lower()


@pytest.mark.asyncio
async def test_outside_domain_is_denied() -> None:
    claim = STORE.claim("evt-ans-3")
    result = await answer_event(
        event_id="evt-ans-3",
        claim_token=claim.claim_token,
        email="stranger@example.net",
        user_id="U_X",
        text="What was revenue last week?",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result["ok"] is False
    assert STORE.open_incidents()


@pytest.mark.asyncio
async def test_incomplete_cohort_horizon_is_not_a_number() -> None:
    claim = STORE.claim("evt-ans-4")
    result = await answer_event(
        event_id="evt-ans-4",
        claim_token=claim.claim_token,
        email="owner@northstar.example",
        user_id="U_OWNER",
        text="Show cohort LTV for 2026-01",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert result["ok"] is True
    assert "not yet complete" in result["answer"]
