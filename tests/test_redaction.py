from app.redaction import REDACTED, redact_json, redact_text


def test_strips_api_tokens_but_keeps_business_fields() -> None:
    text = "order 1042 for casey@example.com api_key=sk-abcdefghijklmnopqrstuvwxyz"
    redacted = redact_text(text, limit=None)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "order 1042" in redacted
    assert "casey@example.com" in redacted
    assert REDACTED in redacted


def test_redacts_nested_secret_keys() -> None:
    payload = {
        "order_id": "1042",
        "access_token": "secret-value",
        "nested": {"password": "hunter2", "sku": "FLASK-32"},
    }
    redacted = redact_json(payload)
    assert redacted["order_id"] == "1042"
    assert redacted["access_token"] == REDACTED
    assert redacted["nested"]["password"] == REDACTED
    assert redacted["nested"]["sku"] == "FLASK-32"
