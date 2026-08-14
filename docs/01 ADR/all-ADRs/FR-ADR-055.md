# `/health/live` touches nothing; `/health/ready` checks Postgres and Redis and nothing else

```
ADR id ............ FR-ADR-055
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.4; SRC-002 §6.2.3; SRC-002 §6.4.2; SRC-002 §7.9; SRC-002 §4.11
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §7.4` says `/health/live` returns 200 if the process is alive, `/health/ready` returns 503 if
the database or Redis is unreachable, and — the sentence that matters — **"These must behave
differently, because the load balancer treats them differently."**

`GOTCHAS.md` records what goes wrong when they are the same: a health check that touches the database
makes a database blip restart every container. The blip is recoverable; the restart loop is not.

The clause names two dependencies. This system has more — SQS, SES, S3 — and the sweep asked whether
readiness should probe them too.

## Decision

**`/health/live` touches nothing.** No database query, no Redis command, no disk, no network. It
returns 200 with a fixed body. It answers exactly one question: is this process running and able to
serve HTTP.

**If it touches a dependency it is not a liveness check**, and wiring a dependency-touching endpoint to
a restart trigger converts every dependency outage into a restart loop.

**`/health/ready` checks PostgreSQL and Redis, and nothing else.**

- PostgreSQL: `SELECT 1`.
- Redis: `PING`.
- Both with a short timeout. A readiness check that hangs is a readiness check that fails by timing
  out at the caller, which is slower and less informative than failing fast.

**503 if either is unreachable**, with a body naming which one. An operator reading a 503 needs to know
which dependency, and it is not sensitive information.

**SQS, SES and S3 are deliberately not probed.**

- **The API can serve almost every request without them.** Browsing, the seat map, holds and bookings
  all work; only the receipt send is affected, and that is the worker's job through a durable queue
  (`FR-ADR-031`).
- **Probing them would take the site out of service for a failure it can absorb.** An SES outage does
  not stop anyone booking.
- Every probe is an API call on the readiness path, polled by the ALB continuously, against free-tier
  request allowances.

**The result is cached for a short interval** — a few seconds — so ALB polling does not run a query per
poll per instance. A stale-by-seconds readiness answer is correct for a check whose consumer polls on
an interval anyway.

**The worker has no HTTP surface and does not expose these endpoints.** Its liveness is the process
running, which ECS observes directly. **That is a real gap:** a worker that is running but wedged —
not polling, not failing — looks healthy. It is recorded rather than solved, and the queue-depth
metric (`FR-ADR-057`) is the signal that would reveal it.

**The static frontend container serves a static file as its health check.** A static web server that
can serve a file is working.

**Which endpoint goes where is Zone C** and the client wires it. The specification in
`docs/30 Deployment/` must say plainly: **the ALB target group health check points at `/health/ready`;
any container-level restart check points at `/health/live`.** Getting them the wrong way round turns a
recoverable dependency outage into a restart loop, and that is one of the two or three common mistakes
`§6.4.4` requires the specification to name.

**Neither endpoint is authenticated, and neither returns anything sensitive.** No version, no
hostname, no connection string. `PAYMENT_PROVIDER` is the one exception (`FR-ADR-041`) — it is
reported deliberately, because an operator needs to be able to tell whether the payments are real
without going through checkout, and it is not a secret.

## Alternatives rejected

**One `/health` endpoint.** Rejected by `§7.4` explicitly, and by the restart-loop trap.

**Make liveness check the database, on the grounds that a process that cannot reach its database is not
alive.** Rejected. That is precisely the failure `§7.4` splits the endpoints to avoid.

**Probe SQS, SES and S3 in readiness.** Rejected above.

**Do not cache the readiness result.** Rejected on cost. Two instances polled every few seconds
multiply into a steady query load for a value that changes rarely, on a `db.t3.micro`.

**Return 200 with a degraded body instead of 503 on Redis loss.** Rejected. `§7.4` says 503, and the
client wants to see the failure (`§7.9`).

**Soften readiness so a Redis outage does not take browsing down.** Rejected in `FR-ADR-028`, where the
consequence is recorded in full: with one instance, a Redis outage takes the site out of the ALB even
though browsing would have worked. That is the ruled behaviour.

## Source

`SRC-002 §7.4` (the two endpoints and why they differ) · `§6.2.3` (Zone B) ·
`§6.4.2` (the specification owes health check paths) · `§7.9` (fail loudly) ·
`§4.11` (there is an ALB, which is what makes the distinction load-bearing).

Which dependencies readiness probes, the caching, and the worker gap are the build session's under
Art III.9.

## Consequences

**Both endpoints are Zone B** (`§6.2.3`), so every line carries a comment saying what breaks without it
— including, on `/health/live`, a comment saying why it deliberately does nothing. That comment is the
one that stops a future contributor "improving" it by adding a database check.

The readiness cache interval and the ALB health check interval interact. If the cache is longer than
the ALB's unhealthy threshold window, the ALB reacts to stale information. The specification must
state both numbers and their required relationship. *(reasoned, not observed.)*

The wedged-worker gap belongs in the architecture folder's list of deliberate gaps, with queue depth
named as the signal that would reveal it.

Testing this means stopping PostgreSQL and asserting 503 from readiness and 200 from liveness in the
same moment. A mocked test proves the handler; only stopping the container proves the timeouts.
