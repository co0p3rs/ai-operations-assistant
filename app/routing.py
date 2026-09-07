"""Deterministic intent router. An LLM classifier is optional on top.

Keyword routing is the fallback when the cheap classifier times out or is
unconfigured. It has to stay correct on its own.
"""

from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    COMMERCE = "commerce"
    COHORT = "cohort"
    WEB = "web"
    ADS = "ads"
    INVENTORY = "inventory"
    SUPPORT = "support"
    WORK = "work"
    ANALYTICS = "analytics"
    UNKNOWN = "unknown"


_RULES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (Intent.COHORT, ("cohort", "ltv", "lifetime value")),
    (Intent.ADS, ("ads", "roas", "cpa", "campaign spend", "paid media")),
    (Intent.INVENTORY, ("inventory", "stock", "warehouse", "on hand", "days cover")),
    (Intent.SUPPORT, ("support", "ticket", "csat", "first response")),
    (Intent.WORK, ("task", "todo", "assigned", "board")),
    (Intent.WEB, ("session", "conversion", "traffic", "web analytics")),
    (Intent.ANALYTICS, ("warehouse", "contract", "analytics query")),
    (Intent.COMMERCE, ("revenue", "order", "sales", "refund", "customer")),
)


def route_intent(text: str) -> Intent:
    lowered = text.lower()
    for intent, needles in _RULES:
        if any(needle in lowered for needle in needles):
            return intent
    return Intent.UNKNOWN
