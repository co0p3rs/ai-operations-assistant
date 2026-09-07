"""One chat turn: identity, RBAC, tools, model, evidence, trace."""

from __future__ import annotations

import logging
from typing import Any

from app.access import UserAccess
from app.config import Settings
from app.evidence import evidence_gap_response, evidence_issues
from app.identity import IdentityError, resolve_access
from app.llm.service import create_assistant_reply
from app.providers.registry import ProviderRegistry
from app.redaction import redact_text
from app.routing import Intent, route_intent
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

    intent = route_intent(text)
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
            instructions=INSTRUCTIONS,
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
    safe_answer = redact_text(answer)

    store.complete(
        event_id=event_id,
        claim_token=claim_token,
        user_id=access.user_id,
        question=redact_text(text),
        answer=safe_answer,
        sources_used=sorted(reply.successful_tools),
        provider=reply.provider,
    )
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
        "permissions": sorted(perm.value for perm in access.effective_permissions),
    }


def access_summary(access: UserAccess) -> dict[str, Any]:
    return {
        "user_id": access.user_id,
        "email": access.email,
        "role": access.role.value,
        "permissions": sorted(perm.value for perm in access.effective_permissions),
    }
