import pytest

from app.outbox import (
    MAX_DELIVERY_ATTEMPTS,
    AnswerOutbox,
    DeliveryState,
    LogPoster,
    PermanentDeliveryError,
    TransientDeliveryError,
    backoff,
)


class FlakyPoster:
    def __init__(self, failures: int, error: type[Exception] = TransientDeliveryError) -> None:
        self.failures = failures
        self.error = error
        self.calls = 0

    def post(self, *, channel: str, text: str, idempotency_key: str) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("chat api unavailable")


def test_enqueue_is_idempotent_by_request_id() -> None:
    outbox = AnswerOutbox()
    first = outbox.enqueue(request_id="req-1", channel="C1", text="first")
    second = outbox.enqueue(request_id="req-1", channel="C1", text="recovered turn")
    assert first is second
    assert outbox.get("req-1").text == "first"


def test_transient_failure_backs_off_then_delivers() -> None:
    outbox = AnswerOutbox()
    poster = FlakyPoster(failures=1)
    outbox.enqueue(request_id="req-2", channel="C1", text="answer")

    report = outbox.deliver_pending(poster, now=100)
    assert report.retried == 1
    # Not due yet: backoff holds it.
    assert outbox.deliver_pending(poster, now=100.5).delivered == 0
    assert outbox.deliver_pending(poster, now=100 + backoff(1)).delivered == 1
    assert outbox.get("req-2").state is DeliveryState.DELIVERED


def test_permanent_failure_goes_straight_to_dead() -> None:
    outbox = AnswerOutbox()
    poster = FlakyPoster(failures=99, error=PermanentDeliveryError)
    outbox.enqueue(request_id="req-3", channel="archived", text="answer")
    assert outbox.deliver_pending(poster, now=0).dead == 1
    assert poster.calls == 1


def test_transient_failures_are_bounded() -> None:
    outbox = AnswerOutbox()
    poster = FlakyPoster(failures=99)
    outbox.enqueue(request_id="req-4", channel="C1", text="answer")
    moment = 0.0
    for _ in range(MAX_DELIVERY_ATTEMPTS):
        outbox.deliver_pending(poster, now=moment)
        moment += 10_000
    assert outbox.get("req-4").state is DeliveryState.DEAD
    assert poster.calls == MAX_DELIVERY_ATTEMPTS


def test_delivered_message_is_not_resent() -> None:
    outbox = AnswerOutbox()
    poster = LogPoster()
    outbox.enqueue(request_id="req-5", channel="C1", text="answer")
    outbox.deliver_pending(poster)
    outbox.deliver_pending(poster)
    assert len(poster.sent) == 1


@pytest.mark.parametrize(("attempts", "expected"), [(1, 2.0), (2, 4.0), (3, 8.0), (20, 300.0)])
def test_backoff_is_exponential_and_capped(attempts: int, expected: float) -> None:
    assert backoff(attempts) == expected
