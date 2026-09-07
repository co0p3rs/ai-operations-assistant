import pytest

from app.config import Settings
from app.llm.service import create_assistant_reply
from app.llm.types import LLMError, ToolBudgetExceededError
from app.routing import Intent


@pytest.mark.asyncio
async def test_uses_demo_model_when_no_keys() -> None:
    async def execute(name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "orders": 10, "gross_revenue": 100.0, "days": 7}

    reply = await create_assistant_reply(
        Settings(),
        question="What was revenue last week?",
        intent=Intent.COMMERCE,
        instructions="test",
        tools=[{"type": "function", "name": "commerce_order_totals"}],
        execute=execute,
    )
    assert reply.provider == "demo"
    assert "10 orders" in reply.text
    assert "commerce_order_totals" in reply.successful_tools


@pytest.mark.asyncio
async def test_tool_budget_is_not_a_fallback_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        anthropic_api_key="sk-ant-test",  # type: ignore[arg-type]
        openai_api_key="sk-test",  # type: ignore[arg-type]
        llm_fallback_enabled=True,
    )

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise ToolBudgetExceededError("budget")

    monkeypatch.setattr("app.llm.service._run_provider", boom)
    with pytest.raises(ToolBudgetExceededError):
        await create_assistant_reply(
            settings,
            question="q",
            intent=Intent.COMMERCE,
            instructions="test",
            tools=[],
            execute=lambda *_a, **_k: None,  # type: ignore[arg-type,return-value]
        )


@pytest.mark.asyncio
async def test_fallback_runs_after_provider_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        anthropic_api_key="sk-ant-test",  # type: ignore[arg-type]
        openai_api_key="sk-test",  # type: ignore[arg-type]
        llm_fallback_enabled=True,
    )
    calls: list[str] = []

    async def run_provider(provider: str, *_args: object, **_kwargs: object):
        calls.append(provider)
        if provider == "anthropic":
            raise LLMError("anthropic is temporarily unreachable")
        from app.llm.types import AssistantReply

        return AssistantReply(text="from openai", provider="openai")

    switches: list[str] = []

    async def on_switch(next_provider: str, reason: str) -> None:
        switches.append(next_provider)

    monkeypatch.setattr("app.llm.service._run_provider", run_provider)
    reply = await create_assistant_reply(
        settings,
        question="q",
        intent=Intent.COMMERCE,
        instructions="test",
        tools=[],
        execute=lambda *_a, **_k: None,  # type: ignore[arg-type,return-value]
        on_provider_switch=on_switch,
    )
    assert reply.text == "from openai"
    assert reply.fallback_used is True
    assert calls == ["anthropic", "openai"]
    assert switches == ["openai"]
