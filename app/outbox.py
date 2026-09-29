"""Durable final-answer delivery.

Computing an answer and posting it are two different failures. If the chat
API is down for a minute, the answer (and every paid tool call behind it)
must not be lost, and a retry must not post it twice.

The turn writes the answer here first. Delivery is a separate step that can
run again after a restart: it posts with the request id as idempotency key,
retries only transient failures with exponential backoff, and parks a
message in `dead` when the platform rejects it outright.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

MAX_DELIVERY_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 300.0


class DeliveryState(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD = "dead"


class TransientDeliveryError(Exception):
    """Rate limit, 5xx, dropped connection: worth another attempt."""


class PermanentDeliveryError(Exception):
    """Channel archived, bot removed, payload rejected: retrying cannot help."""


class ChatPoster(Protocol):
    def post(self, *, channel: str, text: str, idempotency_key: str) -> None: ...


@dataclass
class OutboxMessage:
    request_id: str
    channel: str
    text: str
    state: DeliveryState = DeliveryState.PENDING
    attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: str = ""
    created_at: float = field(default_factory=time.time)
    delivered_at: float | None = None


@dataclass(frozen=True)
class DeliveryReport:
    delivered: int = 0
    retried: int = 0
    dead: int = 0


class AnswerOutbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: dict[str, OutboxMessage] = {}

    def enqueue(self, *, request_id: str, channel: str, text: str) -> OutboxMessage:
        """Idempotent by request_id. A recovered turn cannot queue a second copy."""
        with self._lock:
            existing = self._messages.get(request_id)
            if existing is not None:
                return existing
            message = OutboxMessage(request_id=request_id, channel=channel, text=text)
            self._messages[request_id] = message
            return message

    def deliver_pending(self, poster: ChatPoster, *, now: float | None = None) -> DeliveryReport:
        moment = time.time() if now is None else now
        delivered = retried = dead = 0
        for message in self._due(moment):
            try:
                poster.post(
                    channel=message.channel,
                    text=message.text,
                    idempotency_key=message.request_id,
                )
            except TransientDeliveryError as exc:
                with self._lock:
                    message.attempts += 1
                    message.last_error = str(exc)[:200]
                    if message.attempts >= MAX_DELIVERY_ATTEMPTS:
                        message.state = DeliveryState.DEAD
                        dead += 1
                    else:
                        message.next_attempt_at = moment + backoff(message.attempts)
                        retried += 1
                continue
            except PermanentDeliveryError as exc:
                with self._lock:
                    message.attempts += 1
                    message.last_error = str(exc)[:200]
                    message.state = DeliveryState.DEAD
                dead += 1
                continue
            with self._lock:
                message.attempts += 1
                message.state = DeliveryState.DELIVERED
                message.delivered_at = moment
            delivered += 1
        return DeliveryReport(delivered=delivered, retried=retried, dead=dead)

    def _due(self, moment: float) -> list[OutboxMessage]:
        with self._lock:
            return sorted(
                (
                    item
                    for item in self._messages.values()
                    if item.state is DeliveryState.PENDING and item.next_attempt_at <= moment
                ),
                key=lambda item: item.created_at,
            )

    def get(self, request_id: str) -> OutboxMessage | None:
        return self._messages.get(request_id)

    def counts(self) -> dict[str, int]:
        with self._lock:
            totals = {state.value: 0 for state in DeliveryState}
            for item in self._messages.values():
                totals[item.state.value] += 1
            return totals

    def reset(self) -> None:
        with self._lock:
            self._messages.clear()


def backoff(attempts: int) -> float:
    return min(BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), MAX_BACKOFF_SECONDS)


class LogPoster:
    """Demo poster: records what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self._keys: set[str] = set()

    def post(self, *, channel: str, text: str, idempotency_key: str) -> None:
        # Platforms that honour idempotency keys drop the duplicate server-side.
        if idempotency_key in self._keys:
            return
        self._keys.add(idempotency_key)
        self.sent.append({"channel": channel, "text": text, "key": idempotency_key})


OUTBOX = AnswerOutbox()
POSTER = LogPoster()
