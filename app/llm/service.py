"""Primary model, then fallback. Tool-budget failures do not switch providers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import Settings
from app.llm.claude import run_claude
from app.llm.demo import run_demo_model
from app.llm.transport import post_json
from app.llm.types import AssistantReply, LLMError, ToolBudgetExceededError
from app.routing import Intent

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
SwitchHandler = Callable[[str, str], Awaitable[None]]

OPENAI_URL = "https://api.openai.com/v1/responses"


async def create_assistant_reply(
    settings: Settings,
    *,
    question: str,
    intent: Intent,
    instructions: str,
    tools: list[dict[str, Any]],
    execute: ToolExecutor,
    on_provider_switch: SwitchHandler | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AssistantReply:
    """Answer with the demo model, or Claude then OpenAI when keys exist.

    Each provider retries its own transient failures first. Reaching the
    fallback means the first provider is genuinely unavailable. A
    `ToolBudgetExceededError` is our own limit, not a provider outage, so
    it is not a fallback trigger: the second model would re-run the same
    business calls, bill them twice, and fail on the same cap.
    """
    if not settings.anthropic_configured and not settings.openai_configured:
        return await run_demo_model(
            question=question, intent=intent, tools=tools, execute=execute
        )

    primary = settings.llm_primary
    fallback = settings.llm_fallback if settings.llm_fallback_enabled else ""

    try:
        return await _run_provider(
            primary,
            settings,
            question=question,
            instructions=instructions,
            tools=tools,
            execute=execute,
            transport=transport,
        )
    except ToolBudgetExceededError:
        raise
    except LLMError as exc:
        if not fallback or not _configured(settings, fallback):
            raise
        if on_provider_switch is not None:
            await on_provider_switch(fallback, str(exc))
        reply = await _run_provider(
            fallback,
            settings,
            question=question,
            instructions=instructions,
            tools=tools,
            execute=execute,
            transport=transport,
        )
        reply.fallback_used = True
        return reply


def _configured(settings: Settings, provider: str) -> bool:
    if provider == "anthropic":
        return settings.anthropic_configured
    if provider == "openai":
        return settings.openai_configured
    return False


async def _run_provider(
    provider: str,
    settings: Settings,
    *,
    question: str,
    instructions: str,
    tools: list[dict[str, Any]],
    execute: ToolExecutor,
    transport: httpx.AsyncBaseTransport | None,
) -> AssistantReply:
    if provider == "anthropic":
        return await run_claude(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.anthropic_model,
            question=question,
            instructions=instructions,
            tools=tools,
            execute=execute,
            timeout=settings.llm_timeout_seconds,
            transport=transport,
        )
    if provider == "openai":
        payload = await post_json(
            url=OPENAI_URL,
            headers={
                "authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
                "content-type": "application/json",
            },
            request_body={
                "model": settings.openai_model,
                "instructions": instructions,
                "input": question,
                "tools": tools,
            },
            timeout=settings.llm_timeout_seconds,
            transport=transport,
            provider="openai",
        )
        return _from_openai(payload)
    raise LLMError(f"unknown provider {provider}")


def _from_openai(payload: dict[str, Any]) -> AssistantReply:
    output = payload.get("output") or []
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                texts.append(str(part.get("text", "")))
    return AssistantReply(text="".join(texts) or "No model text.", provider="openai")
