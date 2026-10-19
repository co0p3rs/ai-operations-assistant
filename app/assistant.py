"""One chat turn: identity, RBAC, tools, model, evidence, trace."""

from __future__ import annotations

import logging
from typing import Any

from app.access import UserAccess
from app.config import Settings
from app.evidence import evidence_gap_response, evidence_issues
from app.identity import IdentityError, resolve_access
from app.llm.service import create_assistant_reply
from app.llm.usage import start_usage_meter
from app.outbox import OUTBOX, POSTER, AnswerOutbox, ChatPoster
from app.playbook import coverage_note, plan_for
from app.providers.registry import ProviderRegistry
from app.redaction import redact_text
from app.routing import Intent, advice_for, route_intent
from app.store import EventStore
from app.tool_guard import ToolCallGuard
from app.training import capture_example

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "You are an internal operations assistant for Northstar Outfitters, a "
    "fictional DTC brand. Answer only from successful tool results. Never "
    "claim you checked a source you did not call. Never invent credentials, "
    "customers, or orders. If a source is outside the caller's permissions, "
    "say so. Keep answers short."
)


async def answer_event(
    *,
    event_id: str,
    claim_token: str,
    email: str,
    user_id: str,
    text: str,
    settings: Settings,
    registry: ProviderRegistry,
    store: EventStore,
    channel: str = "",
    outbox: AnswerOutbox = OUTBOX,
    poster: ChatPoster = POSTER,
) -> dict[str, Any]:
    try:
        access = resolve_access(email=email, user_id=user_id, settings=settings)
    except IdentityError as exc:
        incident = store.fail(
            event_id=event_id,
            claim_token=claim_token,
            user_id=user_id,
            question=text,
            error=str(exc),
        )
        return {"ok": False, "error": str(exc), "incident_id": getattr(incident, "incident_id", "")}

    meter = start_usage_meter()
    intent = route_intent(text)
    plan = plan_for(text, access)
    advice = advice_for(intent)
    instructions = (
        INSTRUCTIONS
        + ("\n\n" + advice if advice else "")
        + ("\n\n" + plan.instructions() if plan else "")
    )
    # Every permitted tool, every turn: the router advises, the model chooses.
    tools = registry.allowed_tools(access)
    guard = ToolCallGuard()

    async def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        blocked = guard.register(name, arguments)
        if blocked is not None:
            return blocked
        return await registry.execute(name, arguments, access)

    async def on_switch(next_provider: str, reason: str) -> None:
        guard.reset()
        logger.info("provider_switch next=%s reason=%s", next_provider, reason)

    try:
        reply = await create_assistant_reply(
            settings,
            question=text,
            intent=intent,
            instructions=instructions,
            tools=tools,
            execute=execute,
            on_provider_switch=on_switch,
        )
    except Exception as exc:  # noqa: BLE001 — turn failures become incidents
        incident = store.fail(
            event_id=event_id,
            claim_token=claim_token,
            user_id=access.user_id,
            question=text,
            error=str(exc),
        )
        return {"ok": False, "error": str(exc), "incident_id": getattr(incident, "incident_id", "")}

    issues = evidence_issues(reply.text, successful_tools=reply.successful_tools)
    answer = evidence_gap_response(issues) if issues else reply.text
    note = coverage_note(plan, reply.successful_tools) if plan else ""
    if note:
        answer = f"{answer}\n\n{note}"
    safe_answer = redact_text(answer)

    trace = store.complete(
        event_id=event_id,
        claim_token=claim_token,
        user_id=access.user_id,
        question=redact_text(text),
        answer=safe_answer,
        sources_used=sorted(reply.successful_tools),
        provider=reply.provider,
        usage=None if meter.empty else meter.summary(),
    )
    if trace is None:
        # Another worker owns this event now (our lease expired). Its answer wins.
        return {"ok": False, "error": "claim_lost"}
    # Persist before posting: a chat outage must not lose a finished answer.
    outbox.enqueue(request_id=trace.request_id, channel=channel or user_id, text=safe_answer)
    outbox.deliver_pending(poster)
    capture_example(
        event_id=event_id,
        question=text,
        answer=safe_answer,
        tools=reply.tool_results,
        provider=reply.provider,
    )
    return {
        "ok": True,
        "answer": safe_answer,
        "provider": reply.provider,
        "intent": intent.value,
        "fallback_used": reply.fallback_used,
        "playbook": bool(plan),
        "permissions": sorted(perm.value for perm in access.effective_permissions),
    }


def access_summary(access: UserAccess) -> dict[str, Any]:
    return {
        "user_id": access.user_id,
        "email": access.email,
        "role": access.role.value,
        "permissions": sorted(perm.value for perm in access.effective_permissions),
    }
