import json
import time

from fastapi.testclient import TestClient

from app.main import app, deduplicator, settings
from app.security import build_signature


client = TestClient(app)


def signed_headers(body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "x-event-timestamp": timestamp,
        "x-event-signature": build_signature(settings.webhook_signing_secret, timestamp, body),
    }


def test_health() -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_accepts_then_deduplicates_event() -> None:
    deduplicator._events.clear()
    body = json.dumps({"event_id": "evt-api-1", "role": "viewer", "provider": "analytics", "text": "weekly summary"}).encode()
    assert client.post("/webhooks/events", content=body, headers=signed_headers(body)).status_code == 202
    duplicate = client.post("/webhooks/events", content=body, headers=signed_headers(body))
    assert duplicate.json()["status"] == "duplicate"


def test_rejects_unsigned_request() -> None:
    assert client.post("/webhooks/events", json={"event_id": "evt-2"}).status_code == 401
