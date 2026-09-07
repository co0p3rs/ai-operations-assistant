from fastapi.testclient import TestClient


def test_bi_query_requires_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/bi/query",
        json={
            "metrics": ["orders"],
            "start_date": "2026-08-04",
            "end_date": "2026-08-31",
        },
    )
    assert response.status_code == 401


def test_bi_query_returns_contract_rows(client: TestClient) -> None:
    response = client.post(
        "/bi/query",
        json={
            "metrics": ["orders", "gross_revenue"],
            "start_date": "2026-08-04",
            "end_date": "2026-08-31",
        },
        headers={"authorization": "Bearer local-bi-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["metrics"]["orders"] > 0


def test_bi_query_rate_limit(client: TestClient) -> None:
    body = {
        "metrics": ["orders"],
        "start_date": "2026-08-04",
        "end_date": "2026-08-10",
    }
    headers = {"authorization": "Bearer local-bi-token"}
    statuses = [
        client.post("/bi/query", json=body, headers=headers).status_code for _ in range(61)
    ]
    assert 429 in statuses
