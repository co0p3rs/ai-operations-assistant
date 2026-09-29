from app.store import LEASE_SECONDS, MAX_ATTEMPTS, STORE, ClaimStatus


def _complete(event_id: str, token: str):
    return STORE.complete(
        event_id=event_id,
        claim_token=token,
        user_id="U1",
        question="q",
        answer="a",
        sources_used=[],
        provider="demo",
    )


def test_live_lease_is_not_recovered() -> None:
    STORE.claim("evt-l1", now=1_000)
    assert STORE.recover_expired(now=1_000 + LEASE_SECONDS - 1) == []


def test_heartbeat_extends_lease() -> None:
    claim = STORE.claim("evt-l2", now=1_000)
    assert STORE.heartbeat("evt-l2", claim.claim_token, now=1_000 + LEASE_SECONDS - 1)
    assert STORE.recover_expired(now=1_000 + LEASE_SECONDS + 5) == []


def test_recovery_fences_the_stalled_worker() -> None:
    stalled = STORE.claim("evt-l3", now=1_000)
    [recovery] = STORE.recover_expired(now=1_000 + LEASE_SECONDS + 1)
    assert recovery.claim_token and recovery.claim_token != stalled.claim_token
    assert recovery.request_id == stalled.request_id

    # The old owner wakes up late: its writes and heartbeats are rejected.
    assert _complete("evt-l3", stalled.claim_token) is None
    assert not STORE.heartbeat("evt-l3", stalled.claim_token)
    # The new owner completes normally.
    assert _complete("evt-l3", recovery.claim_token) is not None


def test_completed_claim_cannot_be_completed_twice() -> None:
    claim = STORE.claim("evt-l4")
    assert _complete("evt-l4", claim.claim_token) is not None
    assert _complete("evt-l4", claim.claim_token) is None


def test_gives_up_after_max_attempts_and_opens_incident() -> None:
    STORE.claim("evt-l5", now=0)
    moment = 0.0
    results = []
    for _ in range(MAX_ATTEMPTS):
        moment += LEASE_SECONDS + 1
        results.extend(STORE.recover_expired(now=moment))
    assert results[-1].gave_up is True
    assert results[-1].claim_token is None
    assert any("abandoned" in item.summary for item in STORE.open_incidents())
    assert STORE.claim("evt-l5").status is ClaimStatus.DUPLICATE
