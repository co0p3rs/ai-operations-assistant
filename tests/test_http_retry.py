from app.http_retry import backoff_delay, is_retryable_status


def test_retries_rate_limits_and_server_errors() -> None:
    assert is_retryable_status(429)
    assert is_retryable_status(503)
    assert not is_retryable_status(400)
    assert not is_retryable_status(401)


def test_honours_retry_after_but_caps_it() -> None:
    assert backoff_delay(1, "2", base_seconds=1.0, maximum_seconds=20.0) == 2.0
    assert backoff_delay(1, "999", base_seconds=1.0, maximum_seconds=20.0) == 20.0
    assert backoff_delay(3, None, base_seconds=1.0, maximum_seconds=20.0) == 4.0
