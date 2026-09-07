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
    │  keyword intent router
    │  permission-scoped tool list
    ▼
Model (demo, or Claude then OpenAI)
    │  tool loop + date-slice guard
    │  evidence check (fail-closed)
    │  credential redaction
    ▼
Trace + training example + optional incident
```

The webhook does not answer. A slow model must not hold the chat
platform's retry budget. `request_id` is the claim's id, so logs, traces,
and incidents join without a second identifier.

## Why these boundaries exist

**Replay window.** A captured webhook is useful to an attacker only
until the timestamp ages out. The compare is constant-time.

**Single-owner claim.** Chat platforms retry. Workers restart. Two
replicas can see the same `event_id`. The first claim wins; everyone
else gets `duplicate` and the original `request_id`. Completion and
failure writes must present the claim token, which is the in-memory
stand-in for `UPDATE ... WHERE claim_token = $1`.

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

**Evidence is fail-closed.** If the answer says it checked Commerce
and no `commerce_*` tool succeeded, the answer is replaced. The model
does not get a second chance to invent a citation.

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
| In-process warehouse | Local mirror of the commerce API, incremental sync, nightly reconcile |
| Demo model | Claude primary, OpenAI fallback, shared `llm/transport.py` |
| Seeded `DEMO_USERS` | Directory sync + stored grants |

None of those replacements change the permission model, the contract
vocabulary, or the evidence rule.

## What is intentionally absent

There is no live store, no customer list, no employer domain, and no
deploy path onto a private host. Those belong in a private operations
repository, not in a public one.
