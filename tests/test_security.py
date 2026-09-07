import time

from app.security import build_signature, verify_signature

SECRET = "local-test-secret"
BODY = b'{"event_id":"evt-1"}'


def test_accepts_valid_signature() -> None:
    timestamp = str(int(time.time()))
    signature = build_signature(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, timestamp, BODY, signature)


def test_rejects_tampered_body() -> None:
    timestamp = str(int(time.time()))
    signature = build_signature(SECRET, timestamp, BODY)
    assert not verify_signature(SECRET, timestamp, b'{"event_id":"other"}', signature)


def test_rejects_stale_timestamp() -> None:
    timestamp = str(int(time.time()) - 400)
    signature = build_signature(SECRET, timestamp, BODY)
    assert not verify_signature(SECRET, timestamp, BODY, signature)


def test_rejects_non_numeric_timestamp() -> None:
    signature = build_signature(SECRET, "now", BODY)
    assert not verify_signature(SECRET, "now", BODY, signature)


def test_rejects_missing_signature() -> None:
    timestamp = str(int(time.time()))
    assert not verify_signature(SECRET, timestamp, BODY, "")
