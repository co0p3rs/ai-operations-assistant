"""Stop a model from paging a source one day at a time."""

from __future__ import annotations

import json
from typing import Any

DATE_ARGUMENT_KEYS = frozenset(
    {"start_date", "end_date", "date_from", "date_to", "startDate", "endDate"}
)
MAX_SIMILAR_TOOL_CALLS = 3


class ToolCallGuard:
    """Block repeated tool calls that only change dates."""

    def __init__(self, *, max_similar: int = MAX_SIMILAR_TOOL_CALLS) -> None:
        self._max_similar = max_similar
        self._counts: dict[tuple[str, str], int] = {}

    def reset(self) -> None:
        """Forget the counts when a fallback model starts from scratch.

        The second provider has fetched nothing of its own. Carrying the
        first attempt's counters over would block its opening calls.
        """
        self._counts.clear()

    def register(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        stable = {
            key: value
            for key, value in arguments.items()
            if key not in DATE_ARGUMENT_KEYS
        }
        signature = (
            name,
            json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str),
        )
        self._counts[signature] = self._counts.get(signature, 0) + 1
        if self._counts[signature] <= self._max_similar:
            return None
        return {
            "ok": False,
            "tool": name,
            "error": "repeated_date_sliced_tool_calls_blocked",
            "instruction": (
                "Stop looping the same tool once per day. Call one range "
                "endpoint, then aggregate locally from that payload."
            ),
        }
