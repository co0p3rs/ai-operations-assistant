import json
import time

from fastapi.testclient import TestClient

from app.security import build_signature
from tests.conftest import event_body, signed_headers


def test_health(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["llm"]["demo"] is True


def test_accepts_then_deduplicates_event(client: TestClient) -> None:
    body = event_body(event_id="evt-api-1")
    first = client.post("/webhooks/events", content=body, headers=signed_headers(body))
    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    duplicate = client.post("/webhooks/events", content=body, headers=signed_headers(body))
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["request_id"] == first.json()["request_id"]


def test_rejects_unsigned_request(client: TestClient) -> None:
    assert client.post("/webhooks/events", json={"event_id": "evt-2"}).status_code == 401


def test_rejects_stale_signed_request(client: TestClient) -> None:
    body = event_body(event_id="evt-stale")
    timestamp = str(int(time.time()) - 400)
    headers = {
        "x-event-timestamp": timestamp,
        "x-event-signature": build_signature("local-test-secret", timestamp, body),
    }
    assert client.post("/webhooks/events", content=body, headers=headers).status_code == 401


def test_rejects_oversized_body(client: TestClient) -> None:
    body = b"x" * (1_048_576 + 1)
    timestamp = str(int(time.time()))
    headers = {
        "x-event-timestamp": timestamp,
        "x-event-signature": build_signature("local-test-secret", timestamp, body),
    }
    assert client.post("/webhooks/events", content=body, headers=headers).status_code == 413


def test_url_verification(client: TestClient) -> None:
    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    response = client.post("/webhooks/events", content=body, headers=signed_headers(body))
    assert response.json() == {"challenge": "abc"}


def test_requires_event_id(client: TestClient) -> None:
    body = json.dumps({"type": "message", "text": "hi"}).encode()
    response = client.post("/webhooks/events", content=body, headers=signed_headers(body))
    assert response.status_code == 422
