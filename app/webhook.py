"""Signed chat-platform ingress.

The HTTP handler only verifies, claims, and enqueues. Answering is the
worker's job so a slow model does not hold the webhook open.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from app.assistant import answer_event
from app.config import Settings, get_settings
from app.providers.registry import ProviderRegistry, build_registry
from app.security import verify_signature
from app.store import STORE, ClaimStatus, EventStore

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
REGISTRY = build_registry()


def _settings() -> Settings:
    return get_settings()


def _store() -> EventStore:
    return STORE


def _registry() -> ProviderRegistry:
    return REGISTRY


@router.post("/events")
async def receive_event(
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response,
) -> dict[str, Any]:
    settings = _settings()
    body = await request.body()
    if len(body) > settings.max_request_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body is too large",
        )

    if not verify_signature(
        settings.webhook_signing_secret.get_secret_value(),
        request.headers.get("x-event-timestamp", ""),
        body,
        request.headers.get("x-event-signature", ""),
        max_age_seconds=settings.event_ttl_seconds,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON") from exc

    if not isinstance(event, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid event")

    if event.get("type") == "url_verification":
        return {"challenge": event.get("challenge", "")}

    event_id = str(event.get("event_id") or "")
    if not event_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="event_id is required")

    store = _store()
    claim = store.claim(event_id)
    if claim.status is ClaimStatus.DUPLICATE:
        return {
            "status": "duplicate",
            "request_id": claim.request_id,
        }

    background_tasks.add_task(
        answer_event,
        event_id=event_id,
        claim_token=claim.claim_token,
        email=str(event.get("email") or ""),
        user_id=str(event.get("user_id") or ""),
        text=str(event.get("text") or ""),
        settings=settings,
        registry=_registry(),
        store=store,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "status": "accepted",
        "request_id": claim.request_id,
        "event_id": event_id,
    }
