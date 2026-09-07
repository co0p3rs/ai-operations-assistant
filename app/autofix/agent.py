"""Research a failed turn and describe the smallest justified fix.

The agent never merges, never deploys, and never reads `.env`. In this
public tree it returns a structured proposal. Production wiring opens a
pull request from the same evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.autofix.guardrails import AutofixLimits, GuardrailError, assert_readable
from app.store import Incident


@dataclass(frozen=True)
class FixProposal:
    incident_id: str
    summary: str
    suspected_files: list[str]
    test_to_add: str
    blocked: list[str]


def propose_fix(
    incident: Incident,
    *,
    root: Path,
    limits: AutofixLimits | None = None,
) -> FixProposal:
    limits = limits or AutofixLimits()
    blocked: list[str] = []
    suspected = ["app/assistant.py", "app/providers/registry.py", "app/llm/service.py"]
    readable: list[str] = []
    for path in suspected:
        try:
            assert_readable(root, path)
            readable.append(path)
        except GuardrailError as exc:
            blocked.append(str(exc))
    return FixProposal(
        incident_id=incident.incident_id,
        summary=incident.summary[: limits.max_write_chars],
        suspected_files=readable,
        test_to_add=(
            "Add a regression test that replays the failed event_id with the "
            "same role and asserts the previous failure no longer happens."
        ),
        blocked=blocked,
    )
