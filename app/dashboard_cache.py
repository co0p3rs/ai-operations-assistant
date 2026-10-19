"""Dashboard responses keyed by data generation, served stale while rebuilding.

Three problems this replaced, in the order they showed up:

1. **TTL caching served wrong numbers or none.** A short TTL rebuilt the
   same answer every few minutes when nothing had changed; a long one kept
   showing yesterday after a sync landed. Keys now carry the *generation* of
   every source the response reads (`bump` on a sync that changed rows), so
   an entry is valid exactly until its data changes, however long that is.

2. **A sync stampeded the database.** The first viewer after a bump missed
   the cache, so did everyone else who opened the board in the same second,
   and each started the same heavy build. One builder per key now holds a
   lock; the others wait for its result instead of repeating it.

3. **Viewers waited for the builder.** Even single-flight, whoever arrived
   during the rebuild waited the full build. A version-free "latest" entry
   keeps the last good answer per endpoint and parameters; while a build is
   running it is returned at once, marked `stale`, and only the builder (in
   production, the post-sync warmer) waits.

Versioned entries expire after `ttl_seconds` so dead generations do not fill
memory; the "latest" entry lives longer because it is the fallback.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

Producer = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class CacheInfo:
    hit: bool
    stale: bool
    generations: dict[str, int]


@dataclass
class DashboardCache:
    ttl_seconds: float = 7_200
    latest_ttl_seconds: float = 7 * 86_400
    clock: Callable[[], float] = time.monotonic
    generations: dict[str, int] = field(default_factory=dict)
    _entries: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def bump(self, source: str) -> int:
        """A sync changed `source`: every response that reads it is now old."""
        self.generations[source] = self.generations.get(source, 0) + 1
        return self.generations[source]

    async def get(
        self,
        endpoint: str,
        parameters: dict[str, Any],
        sources: Sequence[str],
        producer: Producer,
    ) -> tuple[dict[str, Any], CacheInfo]:
        versions = {source: self.generations.get(source, 0) for source in sources}
        shape = json.dumps({"endpoint": endpoint, "parameters": parameters}, sort_keys=True)
        key = json.dumps({"shape": shape, "versions": versions}, sort_keys=True)
        latest_key = "latest:" + shape

        cached = self._read(key)
        if cached is not None:
            return cached, CacheInfo(hit=True, stale=False, generations=versions)

        lock = self._locks.setdefault(key, asyncio.Lock())
        previous = self._read(latest_key)
        if lock.locked() and previous is not None:
            # Someone is already rebuilding this shape: do not wait for them.
            return previous, CacheInfo(hit=True, stale=True, generations=versions)

        async with lock:
            cached = self._read(key)  # built by the holder we waited for
            if cached is not None:
                return cached, CacheInfo(hit=True, stale=False, generations=versions)
            payload = await producer()
            now = self.clock()
            self._entries[key] = (now + self.ttl_seconds, payload)
            self._entries[latest_key] = (now + self.latest_ttl_seconds, payload)
        self._locks.pop(key, None)
        return payload, CacheInfo(hit=False, stale=False, generations=versions)

    async def warm(
        self, shapes: Iterable[tuple[str, dict[str, Any], Sequence[str], Producer]]
    ) -> int:
        """Rebuild the shapes people actually open, right after a sync."""
        built = 0
        for endpoint, parameters, sources, producer in shapes:
            _payload, info = await self.get(endpoint, parameters, sources, producer)
            built += 0 if info.hit else 1
        return built

    def reset(self) -> None:
        self.generations.clear()
        self._entries.clear()
        self._locks.clear()

    def _read(self, key: str) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= self.clock():
            self._entries.pop(key, None)
            return None
        return payload
