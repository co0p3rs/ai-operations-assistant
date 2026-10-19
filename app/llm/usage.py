"""What every model call of one chat turn cost, in tokens and roughly in dollars.

A provider console shows one total per day. It cannot say whether the money
went to a single heavy answer, to the router, or to a test run, and "the bill
went up" is not something anyone can act on. Every model call already passes
through `llm.transport.post_json`, so usage is read there into a meter that
lives for one turn; the turn's trace keeps the sum.

The dollar figure is an estimate from list prices. The console stays the
billing truth; the estimate is for comparing answers with each other.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# USD per million tokens (input, output) by model family. Cache writes bill
# 1.25x input and cache reads 0.1x input on Anthropic; OpenAI reports cached
# input inside input_tokens and bills it at a discount.
_CLAUDE_PRICES: tuple[tuple[str, tuple[float, float]], ...] = (
    ("opus", (5.0, 25.0)),
    ("sonnet", (3.0, 15.0)),
    ("haiku", (1.0, 5.0)),
)
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


@dataclass
class ModelUsage:
    calls: int = 0
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0


@dataclass
class UsageMeter:
    by_model: dict[tuple[str, str], ModelUsage] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.by_model

    def add(self, provider: str, model: str, usage: dict[str, Any]) -> None:
        entry = self.by_model.setdefault((provider, model), ModelUsage())
        entry.calls += 1
        if provider == "anthropic":
            entry.input_tokens += _int(usage.get("input_tokens"))
            entry.cache_write_tokens += _int(usage.get("cache_creation_input_tokens"))
            entry.cache_read_tokens += _int(usage.get("cache_read_input_tokens"))
        else:
            details = usage.get("input_tokens_details")
            cached = _int(details.get("cached_tokens")) if isinstance(details, dict) else 0
            entry.input_tokens += max(0, _int(usage.get("input_tokens")) - cached)
            entry.cache_read_tokens += cached
        entry.output_tokens += _int(usage.get("output_tokens"))

    def estimated_usd(self) -> float | None:
        """Claude calls at list price; None when nothing could be priced."""
        total = 0.0
        priced = False
        for (provider, model), entry in self.by_model.items():
            prices = _claude_prices(model) if provider == "anthropic" else None
            if prices is None:
                continue
            priced = True
            input_price, output_price = prices
            total += (
                entry.input_tokens * input_price
                + entry.cache_write_tokens * input_price * CACHE_WRITE_MULTIPLIER
                + entry.cache_read_tokens * input_price * CACHE_READ_MULTIPLIER
                + entry.output_tokens * output_price
            ) / 1_000_000
        return round(total, 4) if priced else None

    def summary(self) -> dict[str, Any]:
        return {
            "models": [
                {
                    "provider": provider,
                    "model": model,
                    "calls": entry.calls,
                    "input_tokens": entry.input_tokens,
                    "cache_write_tokens": entry.cache_write_tokens,
                    "cache_read_tokens": entry.cache_read_tokens,
                    "output_tokens": entry.output_tokens,
                }
                for (provider, model), entry in self.by_model.items()
            ],
            "estimated_usd": self.estimated_usd(),
        }


_current_meter: ContextVar[UsageMeter | None] = ContextVar("llm_usage_meter", default=None)


def start_usage_meter() -> UsageMeter:
    """Collect every model call made from here on in this task's context."""
    meter = UsageMeter()
    _current_meter.set(meter)
    return meter


def record_usage(provider: str, request_body: dict[str, Any], payload: dict[str, Any]) -> None:
    """Add one response's usage to the running meter. Accounting never raises."""
    meter = _current_meter.get()
    usage = payload.get("usage")
    if meter is None or not isinstance(usage, dict):
        return
    model = payload.get("model") or request_body.get("model") or "unknown"
    try:
        meter.add(provider, str(model)[:80], usage)
    except Exception:  # noqa: BLE001 — a bad usage block must not cost an answer
        logger.exception("could not record model usage")


def _claude_prices(model: str) -> tuple[float, float] | None:
    name = model.casefold()
    for family, prices in _CLAUDE_PRICES:
        if family in name:
            return prices
    return None


def _int(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0
