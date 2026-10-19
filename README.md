# AI Operations Assistant

A production-style FastAPI service that turns a signed chat webhook into a
permission-scoped answer over read-only business data.

Employees of a fictional DTC brand, **Northstar Outfitters**, ask
questions in chat. The service verifies the event, claims it once,
checks who is allowed to see which source, gives the model every tool
that person may use (the router only advises), and refuses to claim it
checked a source it never called. Dashboards and the assistant read the
same precomputed snapshots, refreshed in the background, so nobody waits
for an aggregation and the two never disagree.

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
- Advisory intent router: a hint in the prompt, never a filter on the tool list
- Claude tool loop with three cache breakpoints (tools, system, newest message)
  and headroom for thinking; a spent tool budget answers from what it gathered
- Per-turn token and cost meter on every model call, stored on the trace
- Shared retry policy: 429 / 5xx / dead connection only, with a wall-clock budget
- Dual-model fallback that resets tool counters and skips budget errors
- Contract-bounded analytics warehouse; incomplete LTV horizons are `null`
- Shared daily snapshot layer: incremental window refresh, nightly full
  rebuild with a drift report, generation counter that changes only with data
- Dashboard cache keyed by data generation, single builder per shape,
  stale-while-revalidate, post-sync warming
- Upstream report pulls that never page: date chunks that fit one page,
  reconciliation against the source total, window replacement
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
        → identity + RBAC → every permitted tool + routing hint (+ playbook)
        → model (demo | Claude tool loop, cached → OpenAI)   ── usage meter
        → evidence + coverage note + redaction → trace (+ cost) / incident
        → outbox → chat (idempotent, retried)

Upstream APIs ─ chunked, reconciled pull ─▶ facts ─▶ daily snapshot ─┬─▶ assistant tools
                (window replaced)                  (generation)    └─▶ /bi/query ◀─ cache
                                                                         (by generation,
                                                                     stale-while-revalidate)

Housekeeping (daily, no model): recover expired leases → redeliver outbox
        → prune traces → close stale incidents → full snapshot rebuild
        → schema + freshness + snapshot-drift digest
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

## What running it in production changed

The first version of this design worked in tests. These are the changes
that only showed up once real people asked real questions every day. Each
one is a problem I could measure, the decision, and what it bought.

| Problem in production | Decision | Result |
|---|---|---|
| The router picked the tool list. One misclassified question ("how many units do we have" read as sales) left the model without the right tool, so it refused or answered from the wrong source. The most common complaint, and more keywords never fixed it for good. | The router **advises**. The model receives every tool the caller is permitted to use; the routed intent is one line of advice. Permissions stay enforced in code. (`app/routing.py`) | A wrong guess costs a hint, not an answer. The stronger model does the choosing. |
| Nobody could say what an answer cost. The console showed one number per day. | Every model call is metered at the transport layer into a per-turn meter; the trace stores tokens and an estimated price. (`app/llm/usage.py`) | Cost per answer is visible per request, which is how the next two fixes were found. |
| Each tool round resent the whole conversation at full price, up to eight rounds per answer. | Three cache breakpoints: tools, system, and a marker that moves to the newest message every round. Same messages, same answer. (`app/llm/claude.py`) | Roughly 3x cheaper on a five-round answer: ~85% of input tokens read from cache. |
| Answers silently fell back to the second model. The primary model *thinks* before answering, and thinking counts against `max_tokens`; on hard questions the budget ran out before any text. | Headroom: `max_tokens` = 4x the answer budget. Only produced tokens are billed. The no-text case stays a visible error. | No more double billing and double latency, and hard questions are answered by the stronger model. |
| Dashboards and the assistant aggregated raw orders on every request, separately, and could disagree. | One shared **daily snapshot**: incremental refresh of a trailing window, nightly full rebuild that reports drift, ratios computed from sums at read time. (`app/analytics/snapshots.py`) | A year-long view sums 366 rows instead of scanning a year of orders, and both readers return the same number. |
| TTL caching was either stale after a sync or rebuilt for nothing; a sync stampeded the database; viewers waited for rebuilds. | Cache keys carry the **data generation**; one builder per shape; the last good answer is served (marked stale) while a rebuild runs; a warmer rebuilds common shapes after each sync. (`app/dashboard_cache.py`) | Valid exactly until the data changes. Viewers never wait for a build. |
| Two upstream APIs paged grouped reports in metric order. Ties made pages overlap: rows duplicated, others never served, no error. A page cap had also stopped one sync at 20,000 of ~25,800 rows. | **Never page**: one request per date chunk that fits a page, halved when it does not; the rows must add up to the source's total or nothing is written; the window is replaced, not merged. (`app/sync/chunked.py`) | Every month reconciles to the source total to the cent. The bug is reproduced in `tests/test_chunked_sync.py`. |

## Design decisions worth reading in the code

- `app/security.py` — why the timestamp is part of the signed payload
- `app/access.py` — why admin ≠ data access
- `app/store.py` — why completion needs the claim token, and why recovery rotates it
- `app/outbox.py` — why "answer computed" and "answer posted" are separate states
- `app/http_retry.py` and `app/llm/transport.py` — what is retried, and why a 401 is not
- `app/llm/service.py` — why a tool-budget error must not switch providers
- `app/routing.py` — why the router advises instead of filtering tools
- `app/llm/claude.py` — the moving cache breakpoint, and why `max_tokens` has headroom
- `app/llm/usage.py` — metering every model call without touching the callers
- `app/analytics/snapshots.py` — incremental window, nightly rebuild, drift as a signal
- `app/dashboard_cache.py` — generation keys, single flight, stale-while-revalidate
- `app/sync/chunked.py` — why paging a sorted report can lose rows silently
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
RBAC, provider denial, advisory routing on a misrouted question,
contract validation, LTV honesty, retry policy, fallback vs. tool-budget,
cache breakpoints and thinking headroom against a mocked Messages API,
cost metering, snapshot refresh and drift, generation-keyed and
stale-while-revalidate caching, a reproduction of the tied-sort pagination
bug, evidence gaps, redaction, BI auth and rate limits, and guardrail escapes.

```bash
pytest
```

## License

MIT. See [LICENSE](LICENSE).
