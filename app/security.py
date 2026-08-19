import hashlib
import hmac
import time


def build_signature(secret: str, timestamp: str, body: bytes) -> str:
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
    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return False

    current_time = int(time.time()) if now is None else now
    if abs(current_time - request_time) > max_age_seconds:
        return False

    expected = build_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, supplied_signature)
