"""Claude Messages API tool loop: bounded rounds, cached history, room to think.

Two cost decisions live here, both measured on a production deployment of
this design before they were written down:

* Every tool round resends the whole conversation: system prompt, every tool
  definition, and every tool result gathered so far. Without caching, round
  six pays full price for rounds one to five again. Three cache breakpoints
  (tools, system, newest message) make each round read everything before it
  at a tenth of the input price. The model sees exactly the same messages.
  On a five-round answer that cut the bill roughly threefold.

* Models that think before answering count the thinking against
  `max_tokens`. At a tight answer budget a multi-source question spent the
  whole budget thinking, returned no text, and the orchestrator redid the
  answer from scratch on the fallback provider: billed twice, twice as slow,
  answered by the weaker model. Headroom costs nothing unless it is used,
  because only produced tokens are billed; the answer's length is still set
  by the instructions.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import httpx

from app.llm.transport import post_json
from app.llm.types import AssistantReply, LLMError, ToolBudgetExceededError

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MAX_TOOL_ROUNDS = 8
ANSWER_TOKENS = 1_200
THINKING_HEADROOM_MULTIPLIER = 4
TOOL_RESULT_CHAR_LIMIT = 80_000
_CACHE = {"type": "ephemeral"}
SPENT_BUDGET_INSTRUCTION = (
    "\n\nYour tool budget for this question is spent. Answer from the tool "
    "results you already have, report every figure you established, and say "
    "plainly which part of the question remains uncovered."
)


def max_tokens_for(answer_tokens: int) -> int:
    return answer_tokens * THINKING_HEADROOM_MULTIPLIER


def anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("parameters", {"type": "object"}),
        }
        for tool in tools
    ]


def with_history_breakpoint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark the newest message as the end of the cached prefix.

    Only the copy sent to the API carries the marker. Anthropic allows four
    breakpoints per request; tools and system use two, so a marker left on
    every earlier message would break the request by round three.
    """
    if not messages:
        return messages
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, str):
        blocks: list[Any] = [{"type": "text", "text": content}]
    elif isinstance(content, list) and content:
        blocks = list(content)
    else:
        return messages
    if not isinstance(blocks[-1], dict):
        return messages
    blocks[-1] = {**blocks[-1], "cache_control": _CACHE}
    return [*messages[:-1], {**last, "content": blocks}]


def bounded(text: str) -> str:
    """Cap a tool result, and say so: a silently sliced result reads as complete."""
    if len(text) <= TOOL_RESULT_CHAR_LIMIT:
        return text
    return text[:TOOL_RESULT_CHAR_LIMIT] + (
        '\n{"truncated":true,"detail":"Incomplete result. Do not total these '
        'rows as if they were the whole set."}'
    )


async def run_claude(
    *,
    api_key: str,
    model: str,
    question: str,
    instructions: str,
    tools: list[dict[str, Any]],
    execute: ToolExecutor,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
    answer_tokens: int = ANSWER_TOKENS,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> AssistantReply:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    claude_tools = anthropic_tools(tools)
    if claude_tools:
        claude_tools[-1] = {**claude_tools[-1], "cache_control": _CACHE}
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    successful: set[str] = set()
    results: list[dict[str, Any]] = []

    async def call(system: str, with_tools: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens_for(answer_tokens),
            "system": [{"type": "text", "text": system, "cache_control": _CACHE}],
            "messages": with_history_breakpoint(messages),
        }
        if claude_tools:
            # The history holds tool_use blocks, so the final answer keeps the
            # (cached) tool list and forbids calling it instead of dropping it.
            body["tools"] = claude_tools
            if not with_tools:
                body["tool_choice"] = {"type": "none"}
        return await post_json(
            url=ANTHROPIC_URL,
            headers=headers,
            request_body=body,
            timeout=timeout,
            transport=transport,
            provider="anthropic",
        )

    for _round in range(max_rounds):
        payload = await call(instructions, with_tools=True)
        content = payload.get("content")
        if not isinstance(content, list):
            raise LLMError("anthropic returned an invalid response")
        calls = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not calls:
            text = _text(content)
            if not text:
                # Usually stop_reason max_tokens: the budget went to thinking.
                raise LLMError(f"anthropic returned no text ({payload.get('stop_reason')})")
            return AssistantReply(
                text=text,
                provider="anthropic",
                successful_tools=successful,
                tool_results=results,
            )
        messages.append({"role": "assistant", "content": content})
        tool_blocks = []
        for block in calls:
            name = str(block.get("name"))
            result = await execute(name, block.get("input") or {})
            if result.get("ok"):
                successful.add(name)
            results.append({"tool": name, "result": result})
            tool_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": bounded(json.dumps(result, default=str)),
                }
            )
        messages.append({"role": "user", "content": tool_blocks})

    # Out of rounds: keep what was established instead of failing the turn.
    payload = await call(instructions + SPENT_BUDGET_INSTRUCTION, with_tools=False)
    text = _text(payload.get("content") or [])
    if not text:
        raise ToolBudgetExceededError("anthropic exceeded the tool-call round limit")
    return AssistantReply(
        text=text, provider="anthropic", successful_tools=successful, tool_results=results
    )


def _text(content: list[Any]) -> str:
    return "".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
