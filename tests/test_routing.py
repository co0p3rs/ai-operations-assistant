from typing import Any

import pytest

import app.assistant as assistant
from app.assistant import answer_event
from app.config import Settings
from app.llm.types import AssistantReply
from app.providers.registry import build_registry
from app.routing import Intent, advice_for, route_intent
from app.store import STORE


def test_keyword_routing() -> None:
    assert route_intent("Show 12-month LTV by cohort") is Intent.COHORT
    assert route_intent("What is inventory days cover in the west warehouse?") is Intent.INVENTORY
    assert route_intent("How is lookalike-summer CPA?") is Intent.ADS
    assert route_intent("What was revenue last week?") is Intent.COMMERCE
    assert route_intent("hello there") is Intent.UNKNOWN


def test_routing_advice_is_a_hint_not_a_limit() -> None:
    assert "commerce" in advice_for(Intent.COMMERCE)
    assert "not a limit" in advice_for(Intent.COMMERCE)
    assert advice_for(Intent.UNKNOWN) == ""


async def test_a_misrouted_question_still_reaches_every_permitted_tool(monkeypatch) -> None:
    # "How many units do we have" reads as commerce to the keyword router, but
    # it is an inventory question. The router may be wrong; the answer model
    # must still be able to call the inventory tool.
    seen: dict[str, Any] = {}

    async def fake_reply(settings, *, instructions, tools, **kwargs) -> AssistantReply:
        seen["instructions"] = instructions
        seen["tools"] = {tool["name"] for tool in tools}
        return AssistantReply(text="Checked.", provider="demo")

    monkeypatch.setattr(assistant, "create_assistant_reply", fake_reply)
    claim = STORE.claim("evt-route-1")
    await answer_event(
        event_id="evt-route-1",
        claim_token=claim.claim_token,
        email="operator@northstar.example",
        user_id="U_OPERATOR",
        text="How many orders worth of jackets do we have on hand?",
        settings=Settings(),
        registry=build_registry(),
        store=STORE,
    )
    assert "Routing hint" in seen["instructions"]
    assert "inventory_on_hand" in seen["tools"]
    assert "commerce_order_totals" in seen["tools"]
    # Permissions still bound the list: the operator has no support grant.
    assert "support_summary" not in seen["tools"]


@pytest.mark.parametrize("intent", list(Intent))
def test_every_intent_has_advice_or_none(intent: Intent) -> None:
    assert isinstance(advice_for(intent), str)
