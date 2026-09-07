"""HMAC-SHA256 webhook verification with a replay window."""

import hashlib
import hmac
import time


def build_signature(secret: str, timestamp: str, body: bytes) -> str:
    """Sign `v1:{timestamp}:{body}` the way the chat platform would."""
    payload = b"v1:" + timestamp.encode("ascii") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def verify_signature(
    secret: str,
    timestamp: str,
    body: bytes,
    supplied_signature: str,
    max_age_seconds: int = 300,
    now: int | None = None,
) -> bool:
    """Accept only a timely, untampered, constant-time-compared signature.

    A missing or non-numeric timestamp is a reject, not a crash. The clock
    window is absolute so a replayed event from five minutes ago cannot be
    forwarded as new. `hmac.compare_digest` keeps the compare from leaking
    how many leading bytes already matched.
    """
    if not secret or not timestamp or not timestamp.isascii() or not timestamp.isdigit():
        return False
    if not supplied_signature:
        return False

    try:
        request_time = int(timestamp)
    except ValueError:
        return False

    current_time = int(time.time()) if now is None else now
    if abs(current_time - request_time) > max_age_seconds:
        return False

    expected = build_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, supplied_signature)
