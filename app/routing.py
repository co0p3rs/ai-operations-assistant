"""Deterministic intent router. It advises; it never decides which tools exist.

Keyword routing is the fallback when a cheap classifier times out or is
unconfigured, so it has to stay sensible on its own. But a router that
*gates* tools turns one misclassification into a wrong answer: "how many
units do we have" routed to commerce instead of inventory left the answer
model without the inventory tool, so it either refused or answered from the
wrong source. In production that was the most frequent complaint, and no
amount of extra keywords fixed it for good.

So the answer model always receives every tool the caller is permitted to
use, and the routed intent travels as one line of advice in its instructions
(`advice_for`). Permissions are still enforced in code by the registry; only
the *choice* moved to the stronger model.
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


def advice_for(intent: Intent) -> str:
    """One line of routing advice for the answer model, never a restriction."""
    if intent is Intent.UNKNOWN:
        return ""
    return (
        f"Routing hint: this looks like a {intent.value} question. It is a hint, "
        "not a limit. Use whichever of your tools the question actually needs, "
        "and more than one source when the question spans them."
    )


def route_intent(text: str) -> Intent:
    lowered = text.lower()
    for intent, needles in _RULES:
        if any(needle in lowered for needle in needles):
            return intent
    return Intent.UNKNOWN
