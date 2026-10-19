"""Claude tool loop: cached history, thinking headroom, and per-turn cost."""

import json
from typing import Any

import httpx
import pytest

from app.llm.claude import THINKING_HEADROOM_MULTIPLIER, run_claude
from app.llm.types import LLMError, ToolBudgetExceededError
from app.llm.usage import UsageMeter, start_usage_meter

TOOLS = [
    {
        "name": "inventory_on_hand",
        "description": "Units on hand by SKU and warehouse.",
        "parameters": {"type": "object", "properties": {}},
    }
]


def _claude(handler) -> dict[str, Any]:
    return {
        "api_key": "test-key",
        "model": "claude-sonnet-test",
        "question": "How many Alpine jackets are on hand?",
        "instructions": "Answer from tools.",
        "tools": TOOLS,
        "timeout": 5,
        "transport": httpx.MockTransport(handler),
    }


async def _execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "on_hand": 412}


def _response(content: list[dict[str, Any]], **usage: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "claude-sonnet-test",
            "stop_reason": "end_turn",
            "content": content,
            "usage": {"input_tokens": 10, "output_tokens": 40, **usage},
        },
    )


def _tool_use(n: int) -> list[dict[str, Any]]:
    return [{"type": "tool_use", "id": f"call_{n}", "name": "inventory_on_hand", "input": {}}]


def _breakpoints(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for message in body["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
        if isinstance(block, dict) and "cache_control" in block
    ]


async def test_each_round_reads_the_earlier_rounds_from_cache() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        n = len(bodies)
        if n < 3:
            return _response(_tool_use(n), cache_read_input_tokens=3_000 * (n - 1))
        return _response([{"type": "text", "text": "412 on hand."}], cache_read_input_tokens=6_000)

    meter = start_usage_meter()
    reply = await run_claude(**_claude(handler), execute=_execute)

    assert reply.text == "412 on hand."
    assert reply.successful_tools == {"inventory_on_hand"}
    for body in bodies:
        # Tools and system are cached, plus exactly one history breakpoint on
        # the newest message: three of the four markers Anthropic allows.
        assert "cache_control" in body["tools"][-1]
        assert "cache_control" in body["system"][0]
        marked = _breakpoints(body)
        assert len(marked) == 1
        assert marked[0] is body["messages"][-1]["content"][-1]
    # The question text itself is unchanged; only its wrapper moved.
    assert bodies[0]["messages"][0]["content"][0]["text"] == "How many Alpine jackets are on hand?"
    usage = meter.summary()["models"][0]
    assert usage["calls"] == 3
    assert usage["cache_read_tokens"] == 9_000


async def test_the_model_gets_room_to_think_beyond_the_answer_budget() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return _response([{"type": "text", "text": "ok"}])

    await run_claude(**_claude(handler), execute=_execute, answer_tokens=1_200)
    assert seen["max_tokens"] == 1_200 * THINKING_HEADROOM_MULTIPLIER


async def test_an_answer_that_ran_out_while_thinking_is_a_provider_error() -> None:
    # No text means the orchestrator may try the fallback provider. That is the
    # expensive path the headroom exists to avoid, so it must stay visible.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"stop_reason": "max_tokens", "content": [{"type": "thinking", "thinking": "…"}]}
        )

    with pytest.raises(LLMError, match="max_tokens"):
        await run_claude(**_claude(handler), execute=_execute)


async def test_a_spent_tool_budget_answers_from_what_it_gathered() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("tool_choice") == {"type": "none"}:
            return _response([{"type": "text", "text": "Partial: 412 in east; west not checked."}])
        return _response(_tool_use(len(bodies)))

    reply = await run_claude(**_claude(handler), execute=_execute, max_rounds=2)
    assert reply.text.startswith("Partial")
    assert "budget for this question is spent" in bodies[-1]["system"][0]["text"]


async def test_a_spent_budget_with_nothing_to_say_is_the_budget_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("tool_choice") == {"type": "none"}:
            return _response([])
        return _response(_tool_use(1))

    with pytest.raises(ToolBudgetExceededError):
        await run_claude(**_claude(handler), execute=_execute, max_rounds=1)


def test_cost_estimate_prices_cache_reads_at_a_tenth() -> None:
    meter = UsageMeter()
    meter.add(
        "anthropic",
        "claude-opus-test",
        {
            "input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "output_tokens": 100_000,
        },
    )
    # 5 fresh + 6.25 cache write + 0.5 cache read + 2.5 output
    assert meter.estimated_usd() == pytest.approx(14.25)


def test_openai_cached_input_is_split_out_and_left_unpriced() -> None:
    meter = UsageMeter()
    meter.add(
        "openai",
        "gpt-test",
        {"input_tokens": 1_000, "input_tokens_details": {"cached_tokens": 400}, "output_tokens": 5},
    )
    model = meter.summary()["models"][0]
    assert (model["input_tokens"], model["cache_read_tokens"]) == (600, 400)
    assert meter.estimated_usd() is None
