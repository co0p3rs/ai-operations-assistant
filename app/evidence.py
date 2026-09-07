"""Fail-closed checks: the assistant cannot claim a source it never called."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.providers.protocol import DataSource, SOURCE_DISPLAY


@dataclass(frozen=True)
class EvidenceIssue:
    source: str
    reason: str


_SOURCE_TO_PREFIXES: dict[str, tuple[str, ...]] = {
    SOURCE_DISPLAY[DataSource.COMMERCE]: ("commerce_", "analytics_query"),
    SOURCE_DISPLAY[DataSource.WEB_ANALYTICS]: ("web_analytics_",),
    SOURCE_DISPLAY[DataSource.ADS]: ("ads_",),
    SOURCE_DISPLAY[DataSource.INVENTORY]: ("inventory_",),
    SOURCE_DISPLAY[DataSource.SUPPORT]: ("support_",),
    SOURCE_DISPLAY[DataSource.WORK]: ("work_",),
}

_EVIDENCE_VERBS = (
    r"check(?:ed|ing)?|search(?:ed|ing)?|review(?:ed|ing)?|"
    r"look(?:ed|ing)?\s+(?:at|through)|according\s+to|"
    r"(?:data|tickets|results)\s+(?:show|indicate|suggest)"
)


def evidence_issues(
    text: str,
    *,
    successful_tools: set[str],
) -> list[EvidenceIssue]:
    issues: list[EvidenceIssue] = []
    for source, prefixes in _SOURCE_TO_PREFIXES.items():
        if not re.search(rf"\b{re.escape(source)}\b", text, re.IGNORECASE):
            continue
        has_success = any(
            any(name == prefix or name.startswith(prefix) for prefix in prefixes)
            for name in successful_tools
        )
        claimed_check = re.search(
            rf"(?:{_EVIDENCE_VERBS}).{{0,80}}\b{re.escape(source)}\b|"
            rf"\b{re.escape(source)}\b.{{0,80}}(?:{_EVIDENCE_VERBS})",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if claimed_check and not has_success:
            issues.append(
                EvidenceIssue(
                    source,
                    "source was described as checked without a successful call",
                )
            )
    return issues


def evidence_gap_response(issues: list[EvidenceIssue]) -> str:
    sources = ", ".join(dict.fromkeys(issue.source for issue in issues))
    return (
        "I couldn't verify the requested evidence"
        + (f" from {sources}" if sources else "")
        + ". I won't claim those sources were checked without successful tool results."
    )
