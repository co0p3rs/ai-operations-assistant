"""Daily, model-free maintenance and a data-health digest.

Nothing here calls a model, and nothing here can merge or deploy. It keeps
state bounded (trace retention, stale incidents), redelivers answers the
outbox still owes, recovers abandoned turns, and tells a human which data
sources are late *before* someone quotes a stale number in a meeting.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from app.analytics.schema_gate import check_schema
from app.analytics.warehouse import Warehouse
from app.outbox import AnswerOutbox, ChatPoster
from app.providers.data import SOURCE_SYNCS
from app.store import EventStore

TRACE_RETENTION_SECONDS = 30 * 86_400
INCIDENT_STALE_SECONDS = 14 * 86_400

# How late each sync may be before the digest calls it out.
FRESHNESS_SLA_HOURS: dict[str, float] = {
    "commerce": 6,
    "ads": 12,
    "web_analytics": 24,
    "inventory": 24,
    "support": 12,
}


@dataclass(frozen=True)
class SourceHealth:
    source: str
    lag_hours: float | None
    sla_hours: float
    stale: bool


@dataclass(frozen=True)
class HousekeepingReport:
    traces_pruned: int
    incidents_closed: int
    turns_recovered: int
    turns_abandoned: int
    answers_redelivered: int
    schema_ok: bool
    sources: tuple[SourceHealth, ...]

    def digest(self) -> str:
        stale = [s for s in self.sources if s.stale]
        lines = ["Data health: " + ("all sources within SLA" if not stale else f"{len(stale)} source(s) late")]
        for item in stale:
            lag = "never synced" if item.lag_hours is None else f"{item.lag_hours:.1f}h behind"
            lines.append(f"- {item.source}: {lag} (SLA {item.sla_hours:g}h)")
        if not self.schema_ok:
            lines.append("- warehouse schema drift: analytics queries are refusing to answer")
        lines.append(
            f"Maintenance: pruned {self.traces_pruned} traces, closed {self.incidents_closed} "
            f"stale incidents, recovered {self.turns_recovered} turns "
            f"({self.turns_abandoned} abandoned), redelivered {self.answers_redelivered} answers."
        )
        return "\n".join(lines)


def source_health(syncs: dict[str, str], *, now: float) -> tuple[SourceHealth, ...]:
    rows: list[SourceHealth] = []
    for source, sla in FRESHNESS_SLA_HOURS.items():
        stamp = syncs.get(source)
        if not stamp:
            rows.append(SourceHealth(source, None, sla, True))
            continue
        lag = (now - datetime.fromisoformat(stamp).timestamp()) / 3600
        rows.append(SourceHealth(source, round(lag, 1), sla, lag > sla))
    return tuple(rows)


def run_housekeeping(
    *,
    store: EventStore,
    outbox: AnswerOutbox,
    poster: ChatPoster,
    warehouse: Warehouse,
    syncs: dict[str, str] = SOURCE_SYNCS,
    now: float | None = None,
) -> HousekeepingReport:
    moment = time.time() if now is None else now
    recoveries = store.recover_expired(now=moment)
    delivery = outbox.deliver_pending(poster, now=moment)
    return HousekeepingReport(
        traces_pruned=store.prune_traces(older_than=moment - TRACE_RETENTION_SECONDS),
        incidents_closed=store.resolve_stale_incidents(older_than=moment - INCIDENT_STALE_SECONDS),
        turns_recovered=sum(1 for r in recoveries if not r.gave_up),
        turns_abandoned=sum(1 for r in recoveries if r.gave_up),
        answers_redelivered=delivery.delivered,
        schema_ok=check_schema(warehouse).ok,
        sources=source_health(syncs, now=moment),
    )
