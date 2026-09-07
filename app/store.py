"""Single-owner event claims, request traces, and incidents.

The first owner of an event_id wins. A duplicate delivery — the chat
platform retries, a worker restarts, two replicas see the same webhook —
must not run the assistant twice. The claim token is what later completion
and failure writes use to prove they still own the row.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ClaimStatus(StrEnum):
    CLAIMED = "claimed"
    COMPLETE = "complete"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class ClaimResult:
    event_id: str
    claim_token: str
    status: ClaimStatus
    request_id: str


@dataclass
class RequestTrace:
    request_id: str
    event_id: str
    user_id: str
    status: str
    question: str
    answer: str = ""
    sources_used: list[str] = field(default_factory=list)
    provider: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None


@dataclass
class Incident:
    incident_id: str
    request_id: str
    event_id: str
    summary: str
    created_at: float = field(default_factory=time.time)
    resolved: bool = False


class EventStore:
    """Process-local store with the same ownership rules as the SQL version.

    Production replaces this with PostgreSQL `INSERT ... ON CONFLICT` and a
    compare-and-swap on `claim_token`. The in-memory map is enough for a
    single replica and for the test suite.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claims: dict[str, ClaimResult] = {}
        self._traces: dict[str, RequestTrace] = {}
        self._incidents: dict[str, Incident] = {}

    def claim(self, event_id: str) -> ClaimResult:
        with self._lock:
            existing = self._claims.get(event_id)
            if existing is not None:
                return ClaimResult(
                    event_id=event_id,
                    claim_token=existing.claim_token,
                    status=ClaimStatus.DUPLICATE,
                    request_id=existing.request_id,
                )
            result = ClaimResult(
                event_id=event_id,
                claim_token=secrets.token_urlsafe(32),
                status=ClaimStatus.CLAIMED,
                request_id=f"req_{secrets.token_hex(8)}",
            )
            self._claims[event_id] = result
            return result

    def complete(
        self,
        *,
        event_id: str,
        claim_token: str,
        user_id: str,
        question: str,
        answer: str,
        sources_used: list[str],
        provider: str,
    ) -> RequestTrace | None:
        with self._lock:
            claimed = self._claims.get(event_id)
            if claimed is None or claimed.claim_token != claim_token:
                return None
            self._claims[event_id] = ClaimResult(
                event_id=event_id,
                claim_token=claim_token,
                status=ClaimStatus.COMPLETE,
                request_id=claimed.request_id,
            )
            trace = RequestTrace(
                request_id=claimed.request_id,
                event_id=event_id,
                user_id=user_id,
                status="complete",
                question=question,
                answer=answer,
                sources_used=sources_used,
                provider=provider,
                completed_at=time.time(),
            )
            self._traces[claimed.request_id] = trace
            return trace

    def fail(
        self,
        *,
        event_id: str,
        claim_token: str,
        user_id: str,
        question: str,
        error: str,
    ) -> Incident | None:
        with self._lock:
            claimed = self._claims.get(event_id)
            if claimed is None or claimed.claim_token != claim_token:
                return None
            self._claims[event_id] = ClaimResult(
                event_id=event_id,
                claim_token=claim_token,
                status=ClaimStatus.FAILED,
                request_id=claimed.request_id,
            )
            self._traces[claimed.request_id] = RequestTrace(
                request_id=claimed.request_id,
                event_id=event_id,
                user_id=user_id,
                status="failed",
                question=question,
                error=error,
                completed_at=time.time(),
            )
            incident = Incident(
                incident_id=f"inc_{secrets.token_hex(6)}",
                request_id=claimed.request_id,
                event_id=event_id,
                summary=error,
            )
            self._incidents[incident.incident_id] = incident
            return incident

    def get_trace(self, request_id: str) -> RequestTrace | None:
        return self._traces.get(request_id)

    def traces(self) -> list[RequestTrace]:
        return list(self._traces.values())

    def open_incidents(self) -> list[Incident]:
        return [item for item in self._incidents.values() if not item.resolved]

    def oldest_open_incident(self) -> Incident | None:
        open_items = self.open_incidents()
        if not open_items:
            return None
        return min(open_items, key=lambda item: item.created_at)

    def reset(self) -> None:
        with self._lock:
            self._claims.clear()
            self._traces.clear()
            self._incidents.clear()


STORE = EventStore()
