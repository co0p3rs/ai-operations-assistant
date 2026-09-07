from app.store import ClaimStatus, EventStore


def test_first_claim_wins() -> None:
    store = EventStore()
    first = store.claim("evt-1")
    second = store.claim("evt-1")
    assert first.status is ClaimStatus.CLAIMED
    assert second.status is ClaimStatus.DUPLICATE
    assert first.request_id == second.request_id
    assert first.claim_token == second.claim_token


def test_complete_requires_claim_token() -> None:
    store = EventStore()
    claim = store.claim("evt-2")
    assert (
        store.complete(
            event_id="evt-2",
            claim_token="wrong",
            user_id="U1",
            question="q",
            answer="a",
            sources_used=[],
            provider="demo",
        )
        is None
    )
    trace = store.complete(
        event_id="evt-2",
        claim_token=claim.claim_token,
        user_id="U1",
        question="q",
        answer="a",
        sources_used=["commerce_order_totals"],
        provider="demo",
    )
    assert trace is not None
    assert trace.status == "complete"


def test_failure_opens_an_incident() -> None:
    store = EventStore()
    claim = store.claim("evt-3")
    incident = store.fail(
        event_id="evt-3",
        claim_token=claim.claim_token,
        user_id="U1",
        question="q",
        error="provider down",
    )
    assert incident is not None
    assert store.oldest_open_incident() == incident
