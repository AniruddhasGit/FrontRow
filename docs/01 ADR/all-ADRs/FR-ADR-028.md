# When Redis is down: the seat path fails loudly, browsing keeps working, and readiness still goes 503

```
ADR id ............ FR-ADR-028
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.9; SRC-002 §7.4; SRC-002 §8.2.1; SRC-002 §8.2.2; SRC-002 §5.2.3; SRC-001 §7.2
Constitution ...... frontrow-constitution@0.1.0
```

> **This record resolves a contradiction the five-lens sweep found between two lenses.** The
> operations lens read `SRC-002 §7.9` as scoped to locks; the user-visible lens read it as scoped to
> the whole seat map; the concurrency lens flagged the scope as undecided. All three were reading the
> same clause. It is decided here.

## Context

`SRC-002 §7.9` says: "If Redis is down, do not silently fall back to the database for locks. Return an
error. I need to see the failure."

The sentence names locks. But Redis does three jobs in this system — locks (`§8.1`), the seat-map and
listing cache (`§8.2.1`, `§8.2.2`), and the rate limiter's token bucket (`§8.4.1`) — and the clause
does not say what the other two do when it is gone.

There is a second clause pulling the other way. `§7.4` says `/health/ready` returns 503 when the
database **or Redis** is unreachable. If readiness fails, the ALB takes the instance out of service,
and every path goes down including the ones that did not need Redis. So a strict reading of `§7.4`
makes the scope question moot in the worst way.

## Decision

**Three different behaviours, because the three uses have different consequences.**

**1. Locks — fail loudly.** If Redis is unreachable, the hold endpoint returns **503** with a clear
message. It never falls back to the database for locking, never proceeds without a lock, and never
degrades quietly. `§7.9` is explicit and Art IV.6 makes it non-waivable: a silent fallback turns a
visible outage into an invisible correctness risk.

**Booking confirmation also returns 503.** Confirming without a live hold would rely on the database
constraint alone, which is safe against overselling but wrong for the customer — it would let someone
confirm seats another customer is holding, and the loser would find out at payment.

**2. Cache — degrade silently and serve from PostgreSQL.** The seat map, the movie list and the
showtime list are cache-aside (`§8.2.1`, `§8.2.2`). A cache miss and a cache outage are the same event
to a cache-aside reader. Browsing, the seat map read path, movie listings and a customer's own
bookings all keep working, slower.

This is **not** a fallback in the sense `§7.9` forbids. `§7.9` forbids substituting the database for
Redis's *lock* semantics, which the database cannot provide the same way. Reading a seat map from its
source of truth is not a substitution; it is the source.

**3. Rate limiter — fail closed.** If the token bucket cannot be read, the limited endpoints return
**503**, not unlimited access. `FR-ADR-058` carries it. A rate limiter that fails open removes a
control at exactly the moment the system is least healthy.

**4. `/health/ready` still returns 503 when Redis is unreachable**, exactly as `§7.4` requires. It is
not softened to keep read traffic alive.

**The consequence of that is stated rather than avoided:** with one EC2 instance, a Redis outage takes
every instance out of the ALB, so the site is down even though browsing would have worked. That is
`§7.4`'s design and `§1.3`'s intent — the client wants to see the failure — and softening readiness to
keep a degraded site up would hide the outage the clause exists to reveal. It is recorded here as a
known cost, not discovered later. *(reasoned, not observed.)*

**Why the cache behaviour is still specified even though readiness will pull the instance:** the two
are not simultaneous. Readiness is polled on an interval, so there is a window in which requests
arrive at an instance that has lost Redis, and there is a longer window during a partial failure where
some commands time out and others succeed. Browsing continuing to work in that window is correct, and
it is what makes the failure a *partial* outage rather than a corruption.

## Alternatives rejected

**Read `§7.9` as covering every Redis use, so the whole site errors.** Rejected. It converts a cache
outage into a total outage at the application layer as well as the load balancer layer, and it means a
Redis blip loses browsing traffic that PostgreSQL could have served.

**Read `§7.9` as covering only the literal `SETNX`, so confirmation proceeds on the database
constraint alone.** Rejected above: safe against overselling, wrong for the customer.

**Soften `/health/ready` so it only reports the database, keeping the site up on Redis loss.**
Rejected. It contradicts `§7.4`'s explicit text and hides the failure `§7.9` wants visible. Collapsing
or weakening the health endpoints defeats the reason they exist.

**Fail the rate limiter open so customers are not blocked.** Rejected as the weaker option. Failing
closed is stricter and under Art III.10 needs no signature.

## Source

`SRC-002 §7.9` (fail loudly on dependency loss) · `§7.4` (readiness returns 503 on Redis loss) ·
`§8.2.1`, `§8.2.2` (cache-aside) · `§5.2.3` (one node, no replica) · `SRC-001 §7.2` (availability
during the busiest period).

The three-way split is the build session's under Art III.9.

## Consequences

`GOTCHAS.md` records the second-outage trap and it applies directly: a Redis failure caught in an
`except` block must not touch Redis again to build the error message or to log. **The failure path
touches nothing that can fail.**

The Redis client needs explicit connect and command timeouts. A default of no timeout turns an
unreachable node into hung requests rather than a 503, and hung requests exhaust the connection pool.
`FR-ADR-058` and the configuration inventory in `FR-ADR-053` carry the values.

There is one `cache.t3.micro` node with no replica (`§5.2.3`), so this is not a hypothetical. A
maintenance restart produces it, and every live hold is lost with it (`FR-ADR-025`).

This behaviour needs a test that actually stops Redis, not one that mocks a connection error. A mock
proves the handler; only stopping the container proves the client's timeout configuration.
