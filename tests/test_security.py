from app.security import build_signature, verify_signature


def test_valid_signature() -> None:
    body = b'{"event_id":"evt-1"}'
    signature = build_signature("secret", "1000", body)
    assert verify_signature("secret", "1000", body, signature, now=1000)


def test_rejects_stale_or_modified_request() -> None:
    body = b"original"
    signature = build_signature("secret", "1000", body)
    assert not verify_signature("secret", "1000", b"modified", signature, now=1000)
    assert not verify_signature("secret", "1000", body, signature, now=1400)
