import time


class EventDeduplicator:
    """In-memory TTL hash map. Replace with Redis for multi-instance deployment."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._events: dict[str, float] = {}

    def accept(self, event_id: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        self._remove_expired(current)
        if event_id in self._events:
            return False
        self._events[event_id] = current + self.ttl_seconds
        return True

    def _remove_expired(self, now: float) -> None:
        expired = [event_id for event_id, deadline in self._events.items() if deadline <= now]
        for event_id in expired:
            del self._events[event_id]
