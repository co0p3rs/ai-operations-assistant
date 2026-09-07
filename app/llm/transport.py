"""One retry policy for every model HTTP call.

Retry 429, 5xx, and a dropped connection. Do not retry a 4xx. Attempts are
also bounded by wall clock: four slow timeouts would be minutes of silence
before the other provider is even tried.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.http_retry import backoff_delay, is_retryable_status
from app.llm.types import LLMError

logger = logging.getLogger(__name__)

RETRY_MAX_ATTEMPTS = 4
RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 20.0
RETRY_TIME_BUDGET_SECONDS = 75.0


def retry_delay_seconds(attempt: int, retry_after: str | None = None) -> float:
    return backoff_delay(
        attempt,
        retry_after,
        base_seconds=RETRY_BASE_DELAY_SECONDS,
        maximum_seconds=RETRY_MAX_DELAY_SECONDS,
    )


def safe_provider_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code") or error.get("type")
    if not isinstance(code, str):
        return None
    clean = "".join(
        character for character in code if character.isalnum() or character in "._-"
    )
    return clean[:80] or None


async def post_json(
    *,
    url: str,
    headers: dict[str, str],
    request_body: dict[str, Any],
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
    provider: str,
) -> dict[str, Any]:
    started_at = time.monotonic()
    last_error: Exception | None = None
    last_cause: BaseException | None = None

    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        retry_after: str | None = None
        response: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.post(url, headers=headers, json=request_body)
        except httpx.TransportError as exc:
            last_error = LLMError(f"{provider} is temporarily unreachable")
            last_cause = exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{provider} is temporarily unreachable") from exc

        if response is not None:
            if not response.is_error:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise LLMError(f"{provider} returned invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise LLMError(f"{provider} returned an invalid response")
                return payload

            detail = f"{provider} request failed (HTTP {response.status_code})"
            code = safe_provider_code(response)
            if code:
                detail = f"{detail}, {code}"
            if not is_retryable_status(response.status_code):
                raise LLMError(detail)
            last_error = LLMError(detail)
            retry_after = response.headers.get("retry-after")

        if attempt == RETRY_MAX_ATTEMPTS:
            break

        delay = retry_delay_seconds(attempt, retry_after)
        elapsed = time.monotonic() - started_at
        if elapsed + delay >= RETRY_TIME_BUDGET_SECONDS:
            logger.warning("%s retry budget spent after %.0fs", provider, elapsed)
            break
        await asyncio.sleep(delay)

    failure = last_error or LLMError(f"{provider} did not return a usable response")
    raise failure from last_cause
