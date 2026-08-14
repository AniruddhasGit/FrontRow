# Rate limiting: a Redis token bucket keyed on the real client IP and on the user, failing closed

```
ADR id ............ FR-ADR-058
Pack .............. PACK-OPS
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.4.1; SRC-002 §8.4.2; SRC-002 §7.9; SRC-002 §4.11; SRC-002 §8.3.1; SRC-001 §8.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.4.1` requires a token bucket in Redis on seat selection and booking endpoints, **per user
and per IP**. `§8.4.2` requires 429 with a `Retry-After` header.

`GOTCHAS.md` records two ways a rate limiter looks like it works while protecting nothing.

**A limiter storing state in-process multiplies its own limit.** With two workers across N tasks, "5
attempts per 15 minutes" is really 5 × 2 × N. `§8.4.1` requiring Redis is what avoids this — but only
if every process actually uses it.

**A limiter behind a load balancer limits the load balancer.** Its default key is the peer address,
which behind an ALB is the ALB. Every customer then shares one bucket, and the limiter appears to work
while protecting nothing. `§8.4.1` requires per-user **and** per-IP, so getting the IP wrong silently
halves the design.

Three things the clause does not settle: the bucket sizes, how the real client IP is obtained, and
what happens when Redis — which holds the buckets — is itself unreachable.

## Decision

**A token bucket in Redis, evaluated by a Lua script so the read, the refill and the decrement are one
atomic operation.** A read-then-write in two round trips is a limiter that leaks under exactly the
concurrency it exists to control.

**Two independent buckets per limited request. Both must have a token.**

- **Per user**, for authenticated endpoints. Keyed on the user id.
- **Per IP**, always, keyed on the real client address.

**The real client IP comes from the rightmost-but-one entry of `X-Forwarded-For`**, with the
application configured to trust exactly one proxy — the ALB. Not the leftmost entry, which a client
can forge by sending its own header. Uvicorn runs with `--proxy-headers` and an explicit
`--forwarded-allow-ips` naming the ALB's subnet range rather than a wildcard.

**Getting this wrong is silent**, which is why it needs a test: assert that two requests carrying
different forged `X-Forwarded-For` values from the same peer are counted in the same bucket.

**Limited endpoints and their buckets** — starting values, tuned once measured:

| Endpoint | Per user | Per IP |
|---|---|---|
| seat hold | 20 / minute | 60 / minute |
| booking confirm | 10 / minute | 30 / minute |
| login | 10 / 15 minutes | 30 / 15 minutes |
| registration | — | 5 / hour |
| password reset request | — | 5 / hour |
| booking lookup by reference | 20 / minute | 60 / minute |
| seat map read | — | 120 / minute |

**Login, registration and password reset are limited even though `§8.4.1` names only seat selection
and booking.** Extending a control is stricter and under Art III.10 needs no signature. An unlimited
login endpoint is a guessing oracle, and an unlimited registration endpoint fills a table that is
never pruned (`FR-ADR-012`).

**The seat map read is limited per IP only**, generously, because it is unauthenticated and polled
every three seconds by every viewer (`FR-ADR-045`). The limit exists to stop scraping, not to stop
browsing, and 120 a minute is far above what a legitimate poller uses.

**On Redis being unreachable, the limiter fails closed: 503.** Not unlimited access. A limiter that
fails open removes a control at exactly the moment the system is least healthy. This is consistent
with `FR-ADR-028`, and it is the stricter option.

**A retry carrying an already-seen `Idempotency-Key` still consumes a token.** It is a real request
arriving at the server. The bucket sizes are set so a customer's legitimate double-click and one or
two retries fit comfortably inside them — ten confirms a minute against a three-minute hold is not a
constraint a real customer meets.

**429 responses carry `Retry-After` in seconds**, computed from the bucket's refill rate rather than a
constant, and the error envelope's `RATE_LIMITED` code (`FR-ADR-052`).

**The stress script is not exempted.** It authenticates as fifty distinct users
(`FR-ADR-034`), which stays inside the per-user buckets, and the per-IP limit for seat holds is
configured to permit the test's source. **Disabling a control to make a test pass is a fake green**
and Art III.8 makes waiving a quality check reserved.

## Alternatives rejected

**In-process rate limiting.** Rejected by `§8.4.1` and by the multiplication trap.

**A fixed window instead of a token bucket.** Rejected by `§8.4.1`, and a fixed window permits a burst
of twice the limit across a boundary.

**Trust the leftmost `X-Forwarded-For` entry.** Rejected: client-forgeable.

**`--forwarded-allow-ips="*"`.** Rejected. It trusts any peer's header, which is the same as trusting
the client.

**Fail open when Redis is down.** Rejected above.

**Exempt idempotent retries from the limit.** Rejected. The exemption would be keyed on a
client-supplied header, which makes it an unlimited path for anyone who sends one.

**Skip limiting the seat map because it is public and cached.** Rejected. Cached or not, it is the
largest payload in the product and an unlimited public endpoint on a `t3.micro` is the cheapest way to
exhaust it.

## Source

`SRC-002 §8.4.1` (token bucket in Redis, per user and per IP) · `§8.4.2` (429 with `Retry-After`) ·
`§7.9` (fail loudly on dependency loss) · `§4.11` (the ALB is what makes the IP question exist) ·
`§8.3.1` (idempotent retries) · `SRC-001 §8.2` (one person operates this).

The bucket values, the endpoint list, the IP derivation and the fail-closed choice are the build
session's under Art III.9.

## Consequences

The limiter is a second Redis dependency on the request path, so a Redis outage now produces 503 on
limited endpoints from two independent causes. That is consistent and it is stated.

**The ALB's subnet range is a Zone C value the application needs.** It goes in the prep queue and in
`docs/30 Deployment/`, because `--forwarded-allow-ips` cannot be set correctly without it. Announcing
it now rather than on the day it blocks is Art VIII.4.

The starting bucket values are **estimates, not measurements**. They are configuration
(`FR-ADR-053`) and Phase 7's load test is what replaces them with observed numbers. *(reasoned, not
observed.)*

A customer who legitimately trips a limit sees a 429 with a real wait time rather than a generic
failure, which for a one-person operation is one fewer support question.
