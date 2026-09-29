import json
import time

import pytest
from fastapi.testclient import TestClient

from app.bi_api import reset_rate_limit
from app.config import reset_settings
from app.main import app
from app.outbox import OUTBOX, POSTER
from app.security import build_signature
from app.store import STORE
from app.training import BUFFER


@pytest.fixture(autouse=True)
def clean_state() -> None:
    STORE.reset()
    BUFFER.reset()
    OUTBOX.reset()
    POSTER.sent.clear()
    reset_rate_limit()
    reset_settings()
    yield
    STORE.reset()
    BUFFER.reset()
    reset_rate_limit()
    reset_settings()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def secret() -> str:
    return "local-test-secret"


def signed_headers(body: bytes, secret: str = "local-test-secret") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "x-event-timestamp": timestamp,
        "x-event-signature": build_signature(secret, timestamp, body),
    }


def event_body(
    *,
    event_id: str = "evt-1",
    email: str = "viewer@northstar.example",
    user_id: str = "U_VIEWER",
    text: str = "What was revenue last week?",
) -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "email": email,
            "user_id": user_id,
            "text": text,
            "type": "message",
        }
    ).encode()
