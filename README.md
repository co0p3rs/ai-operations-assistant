# AI Operations Assistant

A production-style FastAPI service that turns a signed chat webhook into a
permission-scoped answer over read-only business data.

Employees of a fictional DTC brand, **Northstar Outfitters**, ask
questions in chat. The service verifies the event, claims it once,
checks who is allowed to see which source, calls only those tools, and
refuses to claim it checked a source it never called.

This repository is a public, self-contained portfolio project. Providers
and numbers are synthetic. It contains no employer code, credentials,
internal domains, or customer information.

## Why this exists

A chat assistant with access to revenue, ads, inventory, and support is
useful only if it is also boring in the ways that matter:

- a replayed or unsigned event never reaches a model
- the same `event_id` is answered at most once, even if a worker dies mid-turn
- a finished answer survives a chat-platform outage and is posted exactly once
- a user with no grants sees no business tools
- an admin can manage users without inheriting commerce access
- a model cannot invent a source citation
- a "why did revenue drop" answer says which checks it could not run
- a warehouse whose schema drifted refuses to answer instead of returning zeros
- a leaked trace cannot contain a token
- a repair agent cannot read `.env` or edit its own guardrails

Those rules are enforced in code and covered by tests. The demo model
exists so the path is exercisable without API keys. Optional Claude and
OpenAI keys turn the same path into a real dual-provider loop, including
the decision *not* to fall over when the failure is our own tool-call
budget.

## Engineering highlights

- HMAC-SHA256 webhook verification, 5-minute replay window, 1 MB body cap
- Single-owner event claim with a compare-and-swap token
- Claims are leases: heartbeat, fenced recovery with token rotation, bounded attempts
- Transactional answer outbox: idempotency key, exponential backoff, dead-letter
- Deny-by-default RBAC; admins do not automatically see business data
- Provider protocol and a registry that re-checks permission on every call
- Deterministic intent router plus a pluggable model layer
- Shared retry policy: 429 / 5xx / dead connection only, with a wall-clock budget
- Dual-model fallback that resets tool counters and skips budget errors
- Contract-bounded analytics warehouse; incomplete LTV horizons are `null`
- Isolated `/bi/query` API: bearer token, rate limit, no model credentials
- Fail-closed evidence checks and credential-only redaction
- Cross-source diagnostic playbook with explicit coverage gaps
- Schema-drift gate with a warehouse fingerprint in `/health`
- Model-free daily housekeeping and a data-freshness digest against per-source SLAs
- Guardrailed incident agent that proposes a fix and cannot widen its leash
- Health endpoint, request traces, training capture
- Unit and API tests, Docker, GitHub Actions

## Architecture

```text
Webhook → signature + replay check → claim(event_id) = lease
        → identity + RBAC → intent (+ diagnostic playbook) → allowed tools
        → model (demo | Claude → OpenAI)
        → evidence + coverage note + redaction → trace / incident
        → outbox → chat (idempotent, retried)

Housekeeping (daily, no model): recover expired leases → redeliver outbox
        → prune traces → close stale incidents → schema + freshness digest
```

A longer design note, including the production mapping for PostgreSQL
and a worker queue, is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload --port 8080
```

Copy `.env.example` to `.env` to change demo settings. Never commit `.env`.

```bash
docker compose up --build
curl -fsS http://localhost:8080/health
```

OpenAPI is served at `/docs` when `ENVIRONMENT` is not `production`.

## Example request

Seeded users (all `@northstar.example`):

| Email | Role | Can read |
|---|---|---|
| `viewer@northstar.example` | user | commerce, web analytics |
| `operator@northstar.example` | user | commerce, ads, inventory, work |
| `support@northstar.example` | user | support |
| `admin@northstar.example` | admin | user management + commerce |
| `owner@northstar.example` | super_admin | everything |

```bash
python - <<'PY'
import json, time, hmac, hashlib, urllib.request

secret = "local-test-secret"
body = json.dumps({
    "event_id": "evt-demo-1",
    "type": "message",
    "email": "viewer@northstar.example",
    "user_id": "U_VIEWER",
    "text": "What was revenue last week?",
}).encode()
timestamp = str(int(time.time()))
digest = hmac.new(
    secret.encode(), b"v1:" + timestamp.encode() + b":" + body, hashlib.sha256
).hexdigest()
request = urllib.request.Request(
    "http://localhost:8080/webhooks/events",
    data=body,
    headers={
        "Content-Type": "application/json",
        "x-event-timestamp": timestamp,
        "x-event-signature": f"v1={digest}",
    },
    method="POST",
)
print(urllib.request.urlopen(request).read().decode())
PY
```

A signed duplicate of the same `event_id` returns `{"status":"duplicate"}`
and the original `request_id`. An unsigned body returns 401. After the
background turn finishes, `GET /admin/traces?email=admin@northstar.example`
shows the redacted question, answer, and tools used.

The isolated warehouse API:

```bash
curl -sS http://localhost:8080/bi/query \
  -H "authorization: Bearer local-bi-token" \
  -H "content-type: application/json" \
  -d '{"metrics":["orders","gross_revenue"],"start_date":"2026-08-04","end_date":"2026-08-31"}'
```

## Public endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness plus model-configuration flags (never secret values) |
| POST | `/webhooks/events` | Signed chat ingress and URL verification |
| GET | `/admin/traces` | Redacted request traces (admin email required) |
| GET | `/admin/incidents` | Open repair incidents |
| GET | `/admin/training` | Captured training candidates |
| POST | `/admin/housekeeping` | Run the daily maintenance job and return the data-health digest |
| POST | `/bi/query` | Token-gated contract query; 503 on schema drift |

## Design decisions worth reading in the code

- `app/security.py` — why the timestamp is part of the signed payload
- `app/access.py` — why admin ≠ data access
- `app/store.py` — why completion needs the claim token, and why recovery rotates it
- `app/outbox.py` — why "answer computed" and "answer posted" are separate states
- `app/http_retry.py` and `app/llm/transport.py` — what is retried, and why a 401 is not
- `app/llm/service.py` — why a tool-budget error must not switch providers
- `app/evidence.py` — fail-closed source claims
- `app/playbook.py` — "not checked" and "no access" are different gaps
- `app/analytics/schema_gate.py` — why every row is inspected, not the first
- `app/housekeeping.py` — what runs without a model, and what it reports
- `app/analytics/engine.py` — incomplete LTV horizons stay `null`
- `app/autofix/guardrails.py` — paths the repair agent cannot touch

## Tests

`pytest` does not need PostgreSQL, Redis, or model keys. The suite covers
signature and replay rejection, claim ownership, lease fencing, outbox
retry and dead-letter, playbook coverage, schema drift, freshness SLAs,
RBAC, provider denial,
contract validation, LTV honesty, retry policy, fallback vs. tool-budget,
evidence gaps, redaction, BI auth and rate limits, and guardrail escapes.

```bash
pytest
```

## License

MIT. See [LICENSE](LICENSE).
