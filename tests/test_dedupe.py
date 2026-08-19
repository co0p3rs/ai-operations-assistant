from app.dedupe import EventDeduplicator


def test_event_is_accepted_once_until_ttl_expires() -> None:
    cache = EventDeduplicator(ttl_seconds=10)
    assert cache.accept("evt-1", now=0)
    assert not cache.accept("evt-1", now=5)
    assert cache.accept("evt-1", now=11)
