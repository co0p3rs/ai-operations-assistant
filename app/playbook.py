"""Cross-source investigation playbook for "why did X move" questions.

"Why did revenue drop on Tuesday?" is not a commerce question. The honest
answer walks the usual suspects in order: confirm the move, then spend,
traffic, stock, and support. A single-source answer to a diagnostic
question reads as a conclusion when it is only a first step.

The playbook does two things. It tells the model which sources to consult,
restricted to what the caller may see. After the turn, it states which
steps were not covered and why, so "no ads problem" is never implied by
"ads were never checked".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.access import UserAccess
from app.providers.protocol import SOURCE_DISPLAY, SOURCE_PERMISSION, DataSource

_DIAGNOSTIC = re.compile(
    r"\b(why|what happened|drop(?:ped)?|dip(?:ped)?|spike[sd]?|fell|decline[sd]?|"
    r"jump(?:ed)?|surge[sd]?|down|up)\b",
    re.IGNORECASE,
)
_KPI = re.compile(r"\b(revenue|sales|orders|conversion|aov|new customers)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Step:
    source: DataSource
    question: str


# Order matters: confirm the movement before explaining it.
REVENUE_PLAYBOOK: tuple[Step, ...] = (
    Step(DataSource.COMMERCE, "Confirm the move: orders, AOV, and refunds vs. the prior period."),
    Step(DataSource.ADS, "Did spend or ROAS change in the same window?"),
    Step(DataSource.WEB_ANALYTICS, "Did sessions or conversion rate change?"),
    Step(DataSource.INVENTORY, "Was a top seller out of stock or low on cover?"),
    Step(DataSource.SUPPORT, "Did tickets spike (shipping, checkout, product issue)?"),
)

_TOOL_PREFIX: dict[DataSource, tuple[str, ...]] = {
    DataSource.COMMERCE: ("commerce_", "analytics_query"),
    DataSource.ADS: ("ads_",),
    DataSource.WEB_ANALYTICS: ("web_analytics_",),
    DataSource.INVENTORY: ("inventory_",),
    DataSource.SUPPORT: ("support_",),
    DataSource.WORK: ("work_",),
}


@dataclass(frozen=True)
class Plan:
    allowed: tuple[Step, ...]
    denied: tuple[Step, ...]

    def instructions(self) -> str:
        lines = [
            "This is a diagnostic question. Work through these checks in order "
            "and say what each one found:"
        ]
        lines += [f"{i}. {SOURCE_DISPLAY[s.source]}: {s.question}" for i, s in enumerate(self.allowed, 1)]
        return "\n".join(lines)


def plan_for(text: str, access: UserAccess) -> Plan | None:
    if not (_DIAGNOSTIC.search(text) and _KPI.search(text)):
        return None
    allowed = tuple(s for s in REVENUE_PLAYBOOK if access.has(SOURCE_PERMISSION[s.source]))
    denied = tuple(s for s in REVENUE_PLAYBOOK if s not in allowed)
    return Plan(allowed=allowed, denied=denied)


def coverage_note(plan: Plan, successful_tools: set[str]) -> str:
    """Name every playbook step the answer could not stand on."""
    missing: list[str] = []
    for step in plan.allowed:
        prefixes = _TOOL_PREFIX[step.source]
        if not any(tool.startswith(prefixes) for tool in successful_tools):
            missing.append(f"{SOURCE_DISPLAY[step.source]} (not checked)")
    missing += [f"{SOURCE_DISPLAY[step.source]} (no access)" for step in plan.denied]
    if not missing:
        return ""
    return "Not covered in this answer: " + ", ".join(missing) + "."
