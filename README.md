# AI Operations Assistant

A production-style FastAPI service that accepts signed chat-platform webhooks, rejects replayed events, applies role-based tool permissions, and routes approved requests to pluggable business-data providers.

This repository uses fictional providers and synthetic data. It contains no employer code, credentials, internal domains, or customer information.

## Engineering highlights

- HMAC-SHA256 webhook verification with timestamp replay protection
- O(1) event deduplication using a TTL hash map
- Deny-by-default role-based access control
- Provider protocol and dependency injection
- Structured request IDs and safe error responses
- Health endpoint and background event processing
- Unit and API tests
- Docker and GitHub Actions

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` to change demo settings. Never commit `.env`.

## Example request

The tests demonstrate how to sign `POST /webhooks/events`. The shared secret defaults to a test-only value when `ENVIRONMENT=development`.

## Architecture

```text
Webhook -> signature verification -> deduplication -> RBAC -> provider registry
```
