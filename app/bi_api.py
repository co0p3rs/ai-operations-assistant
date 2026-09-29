"""Isolated, token-gated, rate-limited warehouse reads.

This process is allowed to see contract results. It is not given model
keys or chat-platform secrets. Row and date caps stay in code so a leaked
token cannot dump the warehouse.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.analytics.engine import run_query
from app.analytics.schema_gate import check_schema
from app.analytics.warehouse import Warehouse
from app.config import get_settings

router = APIRouter(prefix="/bi", tags=["bi"])
WAREHOUSE = Warehouse()
_HITS: dict[str, list[float]] = defaultdict(list)


class QueryBody(BaseModel):
    metrics: list[str] = Field(min_length=1)
    start_date: str
    end_date: str


def _authorize(authorization: str | None) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.bi_api_token.get_secret_value()}"
    if not authorization or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _rate_limit(token: str) -> None:
    settings = get_settings()
    now = time.time()
    window = [stamp for stamp in _HITS[token] if now - stamp < 60]
    if len(window) >= settings.bi_rate_limit_per_minute:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited")
    window.append(now)
    _HITS[token] = window


@router.post("/query")
async def bi_query(
    body: QueryBody,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    _rate_limit(authorization or "")
    schema = check_schema(WAREHOUSE)
    if not schema.ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "schema_drift", "missing": schema.missing},
        )
    result = run_query(
        WAREHOUSE,
        metrics=body.metrics,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    if result.get("ok") and int(result.get("days") or 0) > get_settings().bi_query_max_days:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="range too large")
    return result


def reset_rate_limit() -> None:
    _HITS.clear()
