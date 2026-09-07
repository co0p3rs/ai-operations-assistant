"""Read-only admin surfaces. Secrets are never rendered."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.access import Role
from app.identity import DEMO_USERS
from app.store import STORE
from app.training import BUFFER

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(email: str) -> None:
    user = DEMO_USERS.get(email.lower())
    if user is None or user.role not in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")


@router.get("/traces")
async def list_traces(email: str) -> dict[str, Any]:
    _require_admin(email)
    traces = [
        {
            "request_id": item.request_id,
            "event_id": item.event_id,
            "user_id": item.user_id,
            "status": item.status,
            "question": item.question,
            "answer": item.answer,
            "sources_used": item.sources_used,
            "provider": item.provider,
            "error": item.error,
        }
        for item in STORE.traces()
    ]
    return {"traces": traces}


@router.get("/incidents")
async def list_incidents(email: str) -> dict[str, Any]:
    _require_admin(email)
    return {
        "incidents": [
            {
                "incident_id": item.incident_id,
                "request_id": item.request_id,
                "summary": item.summary,
                "resolved": item.resolved,
            }
            for item in STORE.open_incidents()
        ]
    }


@router.get("/training")
async def list_training(email: str) -> dict[str, Any]:
    _require_admin(email)
    return {
        "examples": [
            {
                "event_id": item.event_id,
                "question": item.question,
                "answer": item.answer,
                "provider": item.provider,
                "rating": item.rating,
                "approved": item.approved,
            }
            for item in BUFFER.all()
        ]
    }
