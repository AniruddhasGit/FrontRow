# SIGTERM releases only the locks of holds that never became bookings, and it needs a per-instance registry

```
ADR id ............ FR-ADR-033
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §7.5; SRC-002 §7.3; SRC-002 §8.1.4; SRC-002 §E E-1; SRC-001 §7.5
Constitution ...... frontrow-constitution@0.1.0
```

> **This record resolves a contradiction the five-lens sweep found between two lenses.** The
> operations lens read `SRC-002 §7.5`'s "release Redis locks held by that instance" as conflicting
> with `§8.1.4`'s "expiry needs no cleanup job"; the concurrency lens read both as ruled and separately
> asked how a stateless container could know which locks were its own. Both observations are correct
> and the clause as written cannot be implemented literally without deciding something.

## Context

`SRC-002 §7.5`: on SIGTERM, stop accepting new requests, finish in-flight ones, **release the Redis
locks held by that instance**, then exit.

`SRC-002 §7.3`: containers are stateless. No local session state.

`SRC-002 §8.1.4`: on lock expiry the seat becomes available again with no cleanup job needed.

Read together these are in tension. A stateless instance does not know which locks are "held by that
instance" — the locks are in Redis, keyed by seat, and carry a hold token, not an instance id. And if
expiry needs no cleanup, it is not obvious why shutdown needs to release anything.

`GOTCHAS.md` supplies the missing reason: SIGTERM without lock release strands every seat that
instance was holding for the full TTL. A deploy during a Friday evening rush makes a block of seats
unbuyable with no error anywhere. The clause is not redundant with expiry — it exists to shorten a
window that expiry would eventually close.

## Decision

**Reconciled reading: `§7.5` shortens an outage window; `§8.1.4` guarantees correctness without it.**
Both hold. Expiry is the guarantee. Release on shutdown is an optimisation on top of it, and it must
never be relied on for correctness.

**A per-instance registry in Redis, not in the process.**

Each API instance has an id, generated at boot. When it grants a hold it adds the hold's keys to a
Redis set `instance:{instance_id}:holds`, with the same 3-minute TTL as the holds themselves. On
SIGTERM it reads that set and runs the compare-and-delete release for each key.

**In Redis rather than in process memory**, because `§7.3` forbids local state and because a process
killed with SIGKILL — which is what follows SIGTERM after the grace period — loses in-memory state
before it can act on it. A registry in Redis survives to be cleaned up by the next deploy's
housekeeping if the shutdown itself is cut short.

**Only holds are released. Bookings are never touched.** A hold whose booking committed had its lock
released at commit already (`FR-ADR-029`) and is gone from the registry. What remains at shutdown is,
by construction, holds that never became bookings.

**Holds still legitimately live are dropped, and that is the intended behaviour.** A customer
mid-checkout on a draining instance loses their hold and is told to re-select. The alternative —
keeping their seats locked while the instance that granted them disappears — leaves the seats
unbuyable for up to three minutes and does not help that customer either, because their next request
goes to a different instance and they have to re-select regardless.

**The compare-and-delete release means this cannot free someone else's lock.** If a hold expired and
another customer re-acquired the seat during the drain, the token no longer matches and the delete is
a no-op.

**Grace period ordering, and the numbers this depends on:**

1. The instance is deregistered from the ALB target group and stops accepting new connections.
2. It waits out the **ALB deregistration delay** before draining, so in-flight requests that were
   already routed complete.
3. In-flight requests finish, bounded by a **drain timeout**.
4. Locks are released from the registry.
5. The process exits.

**The ECS stop timeout must exceed the deregistration delay plus the drain timeout.** If it does not,
SIGKILL arrives at step 3 and steps 4 and 5 never happen. That relationship is the thing that breaks
silently, and **it is a Zone C configuration the client sets** — so `docs/30 Deployment/` owes a
specification stating the three values, their required ordering, and what breaks if they are wrong.
*(reasoned, not observed.)*

**The worker's shutdown is different and is specified here too.** On SIGTERM the worker stops polling,
finishes the message it is currently handling, and exits. It does **not** return an in-flight message
to the queue by letting the visibility timeout lapse, because `FR-ADR-032`'s claim row makes finishing
safe and abandoning it merely slower. It also completes any outbox relay batch in progress
(`FR-ADR-031`).

## Alternatives rejected

**Track held locks in a process-local set.** Rejected under `§7.3`, and it loses everything to SIGKILL.

**Do nothing on SIGTERM and let the TTL handle it.** Rejected by `§7.5`'s explicit text, and by the
trap: a deploy during a busy period makes a block of seats unbuyable for three minutes.

**Tag each lock's value with the instance id and `SCAN` for them at shutdown.** Rejected. A `SCAN`
across every lock key in Redis during a shutdown window is slow, and it competes with live traffic at
the worst moment. A set of known keys is a direct read.

**Transfer the holds to another instance.** Rejected. There is nothing to transfer — the lock is in
Redis and any instance can already serve a confirm against it. What the customer loses is their
in-progress request, not their lock's location.

**Keep live holds and only release abandoned ones.** Rejected as undecidable. An instance draining
cannot tell which of its holds belong to a customer who is about to pay.

## Source

`SRC-002 §7.5` (the shutdown sequence) · `§7.3` (stateless containers) · `§8.1.4` (expiry needs no
cleanup) · `§E E-1` (3 minutes) · `SRC-001 §7.5` (a restart mid-booking loses nobody money).

The registry mechanism, the reconciliation of `§7.5` with `§8.1.4`, and the worker's shutdown
semantics are the build session's under Art III.9.

## Consequences

**Correctness never depends on the release running.** If it fails, if the grace period is too short,
or if the instance is SIGKILLed, the locks expire in three minutes and no booking is affected. That
is the property that makes this safe to get wrong.

Every deploy drops the holds of every customer mid-checkout at that moment. With one EC2 instance and
a fixed host port, a deploy already has a hard downtime window (`FR-ADR-005`), so this adds nothing a
customer would not already notice. It belongs in the runbook: deploy when nobody is buying.

The `instance:{id}:holds` set carries the same TTL as the holds, so an instance that vanishes leaves
no permanent garbage in Redis.

Testing this requires sending a real SIGTERM to a running container and asserting the locks are gone,
not a unit test of the handler. A unit test proves the function; only the signal proves the wiring.
