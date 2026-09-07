from fastapi.testclient import TestClient

from app.store import STORE


def test_admin_traces_require_an_admin(client: TestClient) -> None:
    assert client.get("/admin/traces", params={"email": "viewer@northstar.example"}).status_code == 403


def test_admin_can_list_traces(client: TestClient) -> None:
    claim = STORE.claim("evt-admin-1")
    STORE.complete(
        event_id="evt-admin-1",
        claim_token=claim.claim_token,
        user_id="U_VIEWER",
        question="revenue?",
        answer="42 orders",
        sources_used=["commerce_order_totals"],
        provider="demo",
    )
    response = client.get("/admin/traces", params={"email": "admin@northstar.example"})
    assert response.status_code == 200
    traces = response.json()["traces"]
    assert traces[0]["answer"] == "42 orders"
    assert "secret" not in response.text.lower() or "local-test-secret" not in response.text
