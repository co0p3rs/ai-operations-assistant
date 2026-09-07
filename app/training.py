"""Capture redacted question/answer pairs for later fine-tuning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.redaction import redact_json, redact_text


@dataclass
class TrainingExample:
    event_id: str
    question: str
    answer: str
    provider: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    rating: str | None = None
    approved: bool = False


class TrainingBuffer:
    def __init__(self) -> None:
        self._examples: list[TrainingExample] = []

    def add(self, example: TrainingExample) -> None:
        self._examples.append(example)

    def export_jsonl(self) -> list[dict[str, Any]]:
        return [
            {
                "messages": [
                    {"role": "user", "content": item.question},
                    {"role": "assistant", "content": item.answer},
                ],
                "provider": item.provider,
                "tools": item.tools,
                "approved": item.approved,
            }
            for item in self._examples
            if item.approved
        ]

    def all(self) -> list[TrainingExample]:
        return list(self._examples)

    def rate(self, event_id: str, rating: str) -> bool:
        for item in self._examples:
            if item.event_id == event_id:
                item.rating = rating
                return True
        return False

    def approve(self, event_id: str) -> bool:
        for item in self._examples:
            if item.event_id == event_id:
                item.approved = True
                return True
        return False

    def reset(self) -> None:
        self._examples.clear()


BUFFER = TrainingBuffer()


def capture_example(
    *,
    event_id: str,
    question: str,
    answer: str,
    tools: list[dict[str, Any]],
    provider: str,
) -> TrainingExample:
    example = TrainingExample(
        event_id=event_id,
        question=redact_text(question),
        answer=redact_text(answer),
        provider=provider,
        tools=redact_json(tools),
    )
    BUFFER.add(example)
    return example
