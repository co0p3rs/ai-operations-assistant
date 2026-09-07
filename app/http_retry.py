"""The arithmetic of retrying, in one place.

Callers share the policy so they cannot drift: retry 429, 5xx, and a dead
connection. Do not retry a 4xx. A rejected key fails the same way on the
fourth try; only the wait grows.

Delays stay with each caller. A model that has not answered in seconds is
in trouble. A warehouse report over three years of orders is merely working.
"""


def is_retryable_status(status_code: int) -> bool:
    """Whether a second identical attempt could plausibly succeed."""
    return status_code == 429 or status_code >= 500


def backoff_delay(
    attempt: int,
    retry_after: str | None,
    *,
    base_seconds: float,
    maximum_seconds: float,
) -> float:
    """Prefer the service's own Retry-After, otherwise exponential backoff.

    A service that says when to come back knows better than our arithmetic,
    so the header wins — capped, because a header is not a promise that the
    wait is reasonable.
    """
    if retry_after:
        try:
            requested = float(retry_after)
        except ValueError:
            requested = -1.0
        if requested >= 0:
            return min(requested, maximum_seconds)
    return min(base_seconds * (2 ** (attempt - 1)), maximum_seconds)
