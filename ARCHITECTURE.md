# Architecture

This note is the design document behind the service. The code is the
source of truth; this page is the reasoning.

## Problem

Internal teams ask operational questions in chat: revenue last week,
inventory cover, campaign efficiency, open work. The answers live in
several systems. A helpful bot that can see all of them is also a
privilege-escalation path, a secret-exfiltration path, and a way to
invent numbers that nobody can audit.

The service is built around those failure modes, not around a demo
transcript.

## Request path

```text
Chat platform
    │  HMAC-SHA256 + 5-minute replay window + 1 MB body cap
    ▼
POST /webhooks/events
    │  verify → parse → single-owner claim(event_id)
    │  HTTP 202 {request_id}
    ▼
Background turn
    │  company-domain identity
    │  deny-by-default RBAC
    │  every permitted tool (RBAC-scoped, never router-scoped)
    │  keyword intent → one line of advice in the prompt
    ▼
Model (demo, or Claude then OpenAI)                  ◀── usage meter (per turn)
    │  tool loop: cached tools + system + moving history breakpoint
    │  max_tokens with thinking headroom, date-slice guard
    │  evidence check (fail-closed)
    │  playbook coverage note
    │  credential redaction
    ▼
Trace + training example + optional incident
    │
    ▼
Answer outbox ──► chat platform (idempotency key = request_id)
```

The webhook does not answer. A slow model must not hold the chat
platform's retry budget. `request_id` is the claim's id, so logs, traces,
and incidents join without a second identifier.

## Data path

```text
Upstream report APIs
    │  one unpaged request per date chunk (halved until it fits a page)
    │  rows must sum to the source's own total, or nothing is written
    │  the pulled date window is replaced, never merged
    ▼
Facts (order / line-item level)
    │  incremental refresh: trailing window, every few minutes
    │  full rebuild: nightly, reports days that drifted
    ▼
Daily snapshot  ── generation +1 only when a row changed
    ├──▶ assistant tools (analytics_query)
    └──▶ /bi/query ◀── response cache keyed by generation
                        single builder per shape
                        last good answer served while rebuilding
                        warmed after each sync
```

Both readers sum the same snapshot rows, so the chat answer and the
dashboard cannot disagree about last month's revenue.

## Why these boundaries exist

**Replay window.** A captured webhook is useful to an attacker only
until the timestamp ages out. The compare is constant-time.

**Single-owner claim.** Chat platforms retry. Workers restart. Two
replicas can see the same `event_id`. The first claim wins; everyone
else gets `duplicate` and the original `request_id`. Completion and
failure writes must present the claim token, which is the in-memory
stand-in for `UPDATE ... WHERE claim_token = $1`.

**Claims are leases, and recovery is fenced.** A worker that is killed
mid-turn (deploy, OOM, node loss) leaves a claim that nobody will finish.
Each claim carries a lease that the worker extends with a heartbeat. The
housekeeping job re-owns expired leases, and re-owning rotates the claim
token. That rotation is the fence: if the "dead" worker was only paused
(GC, network partition) and wakes up, its `complete` presents the old
token and is rejected, so there is never a race between two answers.
After three attempts the event becomes an incident instead of a loop.

**Answer outbox.** Computing an answer and posting it fail independently.
The turn persists the final answer before posting. Delivery retries only
transient errors (rate limit, 5xx, dropped connection) with capped
exponential backoff, dead-letters permanent ones (archived channel,
removed bot), and uses `request_id` as the idempotency key so a replay
after a crash cannot post twice. `enqueue` is itself idempotent, so a
recovered turn cannot queue a second copy.

**Deny-by-default RBAC.** A role is not a bag of integrations. Users
start with an empty permission set. Admins can manage users and do not
automatically see commerce or ads. Super-admins see everything. Extra
sources are explicit grants. Admins cannot promote other admins.

**Provider protocol.** Each source is a `Provider` with `tools()` and
`execute()`. The registry is the only path from a model tool name to a
source, and it re-checks the caller's permission on every execution.
Tests inject the registry; they never need a network.

**Contract warehouse.** `analytics_query` accepts a fixed metric list
and a date range. It does not accept SQL. Incomplete LTV horizons
return `null`. A twelve-month number from an eight-month-old cohort is
not LTV, and a chart that pretends otherwise is a lie.

**Isolated BI API.** `/bi/query` is a separate router with its own
bearer token, a per-minute rate limit, and the same contract compiler.
It is not given model keys or the webhook secret. A leaked BI token
cannot dump credentials or chat history.

**Retry policy.** One module decides what is worth another attempt:
429, 5xx, dead connection. A 4xx is not. Attempts are also bounded by
wall clock so four slow timeouts cannot become minutes of silence
before fallback starts.

**Fallback is not a second try at the same mistake.** Claude is
primary; OpenAI is fallback when configured. Each provider retries its
own transient failures first. A tool-call budget error is our limit,
not a provider outage. Switching models would re-run every business
call, bill those APIs twice, and fail on the same cap. The
orchestrator refuses to fall over in that case. When a real fallback
does happen, tool counters reset so the second model is not blocked by
the first attempt.

**The router advises; it does not gate.** The first design let the
keyword router (and later a small classifier) decide which tools the
answer model received. Every misclassification then became a wrong or
"I can't access that" answer, and it was the most frequent complaint in
production. Adding keywords moved the failures around instead of removing
them. Now the model always gets every tool the caller is permitted to use,
and the routed intent travels as one line of advice. Permission is still
enforced by the registry on every call, so widening the *choice* did not
widen *access*.

**Cost is measured where it happens.** All model HTTP goes through one
transport function, so that is where usage is read into a per-turn meter
(a context variable, so no caller changes). The trace keeps tokens by
model, cache reads and writes, and an estimated price. A daily console
total cannot tell a heavy answer from a test run; a per-request number can,
and it is what exposed the next two problems.

**Cached tool rounds.** A tool loop resends the entire conversation each
round: system prompt, every tool definition, every tool result so far.
Round six pays for rounds one to five again. Anthropic allows four cache
breakpoints; the loop uses three: the last tool definition, the system
block, and the newest message, re-placed on every round so the next round
reads everything before it at a tenth of the price. The model sees the
same messages. Measured on a five-round answer: ~85% of input from cache,
roughly a third of the uncached price.

**Thinking needs headroom.** Models that reason before answering count the
reasoning against `max_tokens`. With a tight answer budget, a multi-source
question used the whole budget thinking and returned no text. The
orchestrator saw a provider failure and redid the entire answer on the
fallback model: billed twice, twice the latency, and the weaker model wrote
the answer. `max_tokens` is now four times the answer budget. Unused
headroom costs nothing; the instructions, not the cap, set answer length.
A no-text response is still raised as an error so it stays visible.

**Snapshots, not request-time aggregation.** Dashboards first aggregated
order-level facts on every open, and the assistant did the same thing in
its own code. A year-long view scanned a year of orders, and the two paths
could round or filter differently. One daily snapshot now feeds both.
Refunds and cancellations settle late, so an incremental job rewrites a
trailing window often, and a nightly full rebuild recomputes everything and
reports which days drifted outside that window. Drift is a signal: the
window is too short, or an upstream rewrote history. Ratios such as AOV are
computed from stored sums at read time, never stored, so there is no
average of averages.

**A cache keyed by data, not by the clock.** A TTL is wrong both ways:
too short rebuilds unchanged answers, too long shows yesterday after a sync.
Response keys carry the generation of every source they read, and a sync
bumps a generation only when rows changed. Two further problems came with
the first busy morning. A sync made every open dashboard miss at once and
start the same heavy build, so one builder per key now holds a lock while
the rest wait for its result. Whoever arrived during that build still
waited for it, so the last good answer per shape is kept and served at once,
marked stale, while the build runs; a warmer rebuilds the common shapes
right after each sync so real viewers rarely meet a cold key.

**Pulling from paged APIs.** Two upstream report APIs paged grouped rows in
metric order. Many rows tie on that metric, and without a unique tiebreaker
the order of ties differs between requests, so consecutive pages overlapped:
some rows arrived twice and others never. Nothing errored; the duplicates
collapsed on the primary key and the warehouse held a slightly smaller
number than the source. Separately, a page cap had stopped one pull at
20,000 of ~25,800 rows. The sync now never pages: it requests date chunks
small enough for a single page and halves any chunk whose reported total
exceeds what came back. The pulled rows must add up to the source's own
total for the window, or the pull is refused before anything is written.
Storage replaces the pulled window instead of merging into it, so a row the
upstream re-keyed or removed cannot survive beside its replacement. The bug
is reproduced in `tests/test_chunked_sync.py` against a fake API with
unstable tie ordering.

**Evidence is fail-closed.** If the answer says it checked Commerce
and no `commerce_*` tool succeeded, the answer is replaced. The model
does not get a second chance to invent a citation.

**Diagnostic questions get a playbook.** "Why did revenue drop?" is a
multi-source question. The playbook orders the checks (confirm the move,
then spend, traffic, stock, support), restricts them to the caller's
grants, and after the turn appends what was not covered. "Not checked"
and "no access" are reported separately: one is a gap in this answer,
the other is a permission boundary the user may want to escalate.

**Schema-drift gate.** The compiler declares the columns it reads. Before
any warehouse query, the gate intersects the columns of *every* row (a
partial backfill leaves old-shaped rows at the end) with that list. Drift
returns 503 naming the missing columns, and `/health` exposes a short
fingerprint of the live shape so a deploy can be compared to the last
known-good one.

**Housekeeping without a model.** A daily job recovers expired leases,
redelivers the outbox, prunes traces past retention, closes incidents
too old to still be live, and produces a digest of source lag against
per-source SLAs. It is deliberately boring: nothing in it can call a
model, merge, or deploy.

**Redaction keeps business data.** Training examples need real
questions. They must not keep tokens. Credential-shaped strings and
secret-named keys are stripped; order ids and SKUs stay.

**Repair agent guardrails.** Failed turns become incidents. The agent
may read source and propose a fix. It may not read `.env`, write
`.github/`, edit `redaction.py`, or edit itself. It never merges.

## Production mapping

This repository runs as a single FastAPI process with an in-memory
store and a synthetic warehouse so a reviewer can clone, test, and
curl it without credentials.

The same shapes map onto a multi-process deployment:

| Demo | Production-shaped replacement |
|---|---|
| `EventStore` dict + lock | PostgreSQL `INSERT ... ON CONFLICT` + compare-and-swap on `claim_token` |
| FastAPI `BackgroundTasks` | Celery / Redis worker, late ack, prefetch 1 |
| In-memory lease map | `lease_expires_at` column + `SELECT ... FOR UPDATE SKIP LOCKED` recovery |
| `AnswerOutbox` dict | Outbox table written in the same transaction as the trace |
| `/admin/housekeeping` | Scheduled timer (cron / systemd) calling the same function |
| In-process warehouse | Local mirror of the commerce API, incremental sync, nightly reconcile |
| `SnapshotLayer` rows | Materialized snapshot table, refreshed by a timer (window every 15 min, full nightly) |
| `DashboardCache` dict + `asyncio.Lock` | Redis: `INCR` generation per source, versioned keys with TTL, `SET NX` build lock, "latest" key |
| `fetch_unpaged` against a fake API | The same function over `httpx`, one request per chunk, reconcile before the write transaction |
| Usage on the trace | A JSON column on the request row, shown next to latency in the admin |
| Demo model | Claude primary, OpenAI fallback, shared `llm/transport.py` |
| Seeded `DEMO_USERS` | Directory sync + stored grants |

None of those replacements change the permission model, the contract
vocabulary, or the evidence rule.

## What is intentionally absent

There is no live store, no customer list, no employer domain, and no
deploy path onto a private host. Those belong in a private operations
repository, not in a public one.
