from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.analytics.schema_gate import check_schema
from app.bi_api import WAREHOUSE
from app.config import get_settings
from app.outbox import OUTBOX
from app.store import STORE

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    schema = check_schema(WAREHOUSE)
    return {
        "status": "ok",
        "environment": settings.environment,
        "llm": {
            "demo": not settings.anthropic_configured and not settings.openai_configured,
            "anthropic": settings.anthropic_configured,
            "openai": settings.openai_configured,
            "fallback": settings.llm_fallback_enabled,
        },
        "open_incidents": len(STORE.open_incidents()),
        "outbox": OUTBOX.counts(),
        "warehouse_schema": schema.fingerprint if schema.ok else "drift",
    }
