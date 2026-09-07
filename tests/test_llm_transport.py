import httpx
import pytest

from app.http_retry import is_retryable_status
from app.llm import transport
from app.llm.types import LLMError


class _SequenceTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self._responses.pop(0)


def _response(status: int, body: dict[str, object] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=body or {"ok": True},
        request=httpx.Request("POST", "https://example.test/v1"),
    )


@pytest.mark.asyncio
async def test_retries_503_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "RETRY_TIME_BUDGET_SECONDS", 10.0)
    monkeypatch.setattr(transport, "retry_delay_seconds", lambda *_args, **_kwargs: 0)
    sequence = _SequenceTransport(
        [_response(503, {"error": {"code": "overloaded"}}), _response(200, {"id": "ok"})]
    )
    payload = await transport.post_json(
        url="https://example.test/v1",
        headers={},
        request_body={},
        timeout=1.0,
        transport=sequence,
        provider="anthropic",
    )
    assert payload["id"] == "ok"
    assert sequence.calls == 2


@pytest.mark.asyncio
async def test_does_not_retry_401() -> None:
    sequence = _SequenceTransport([_response(401, {"error": {"code": "invalid_api_key"}})])
    with pytest.raises(LLMError, match="401"):
        await transport.post_json(
            url="https://example.test/v1",
            headers={},
            request_body={},
            timeout=1.0,
            transport=sequence,
            provider="anthropic",
        )
    assert sequence.calls == 1
    assert not is_retryable_status(401)


@pytest.mark.asyncio
async def test_invalid_json_is_not_silently_accepted() -> None:
    bad = httpx.Response(
        200,
        content=b"not-json",
        request=httpx.Request("POST", "https://example.test/v1"),
    )
    sequence = _SequenceTransport([bad])
    with pytest.raises(LLMError, match="invalid JSON"):
        await transport.post_json(
            url="https://example.test/v1",
            headers={},
            request_body={},
            timeout=1.0,
            transport=sequence,
            provider="openai",
        )
