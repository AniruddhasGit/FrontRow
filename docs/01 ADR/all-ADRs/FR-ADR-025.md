# Redis lock mechanics: `SET NX PX` in one command, an owner token, and a Lua compare-and-delete release

```
ADR id ............ FR-ADR-025
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.1.1; SRC-002 §8.1.2; SRC-002 §8.1.3; SRC-002 §8.1.4; SRC-002 §E E-1; SRC-003 OPEN-SEAT-03
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.1.2` requires the lock to be acquired atomically — "two users clicking the same seat at
the same millisecond must produce exactly one winner". `§8.1.3` requires a token so a client can only
release a lock it owns. `§8.1.4` requires expiry with no cleanup job.

Those three clauses state requirements, not implementations, and each has a wrong implementation that
passes ordinary tests. `GOTCHAS.md` records two of them.

## Decision

**Key: `lock:seat:{showtime_id}:{seat_id}`.** One key per seat per showtime. **Per seat, not per
group** — `SRC-003 OPEN-SEAT-03` rules out paired seats, which keeps the hardest part of this system
at its simplest form.

**Acquire: `SET key <token> NX PX <ttl_ms>` — one command.**

The TTL is set **in the same command** as the acquisition. Never `SETNX` followed by `EXPIRE`: a
process that crashes between those two calls leaves a lock with no expiry, and the seat becomes
unbuyable forever with no error anywhere and no test that catches it.

**Token: a per-hold random value**, generated from a cryptographically secure source. **One token per
hold, shared across every seat in that hold**, not one per seat — the hold is the unit the customer
owns, and a single token is one thing to carry through the confirm request rather than ten.

**Release: a Lua script that compares the token and deletes atomically.**

```
if redis.call("GET", KEYS[1]) == ARGV[1] then return redis.call("DEL", KEYS[1]) else return 0 end
```

`GET` then `DEL` as two calls has the race the token exists to prevent: user A's lock expires, user B
acquires the same seat, then A's abandoned tab fires its release and frees B's seat while B is paying.

**TTL: 3 minutes, from configuration.** See `FR-ADR-027`.

**Expiry is Redis's job and nothing else's.** No sweeper, no reconciler, no scheduled job — there is
nothing to schedule one on (`FR-ADR-005`). A seat becomes available again because its key is gone.

**The hold is not persisted in PostgreSQL.** Redis is the only record of a live hold. That is a
decision, not an omission: a hold table would need its own expiry mechanism, which is the cleanup job
`§8.1.4` explicitly removes, and it would create a second source of truth about who holds a seat.

**Redis TTL is therefore the sole authority on expiry.** No `held_until` timestamp is written
anywhere else to be compared against, so there is no clock skew between API instances to reconcile.

**The token is returned to the client and presented on confirm.** It is not a secret worth protecting
beyond the session — it grants the right to release or confirm a hold the client already made — and
it is stored client-side in `sessionStorage` so a page refresh keeps the hold. `FR-ADR-047` carries
that.

## Alternatives rejected

**`SETNX` then `EXPIRE`.** Rejected above. The permanent-lock failure.

**`GET` then `DEL` for release.** Rejected above. Deletes someone else's lock.

**A lock value that is not a token — a fixed string, or the user id.** Rejected. The user id is
guessable and is the same across that user's two tabs, so one tab's release frees the other's hold.

**Redlock across multiple Redis nodes.** Rejected. There is one `cache.t3.micro` node with no replica
(`SRC-002 §5.2.3`), so the algorithm has nothing to distribute across.

**One token per seat instead of one per hold.** Rejected as ten values to carry where one suffices,
with no property gained: the client either owns the whole hold or none of it.

**Refreshing the TTL on activity, so an active customer never loses their seats.** Rejected. It makes
the hold unbounded in the presence of a polling client, which is exactly what the seat map does every
three seconds. `FR-ADR-027` decides the fixed-window behaviour.

## Source

`SRC-002 §8.1.1` (a lock per showtime and seat with a TTL) · `§8.1.2` (atomic) · `§8.1.3` (token) ·
`§8.1.4` (expiry with no cleanup) · `§E E-1` (3 minutes) · `SRC-003 OPEN-SEAT-03` (per seat).

The command shapes, the token scope and the no-persistence decision are the build session's under
Art III.9.

## Consequences

**An ElastiCache restart drops every live hold.** Those customers lose their selection mid-checkout
and see an error. No booking is corrupted, because the database guard is untouched. That is a visible
partial outage by design and `GOTCHAS.md` says not to "fix" it.

Because holds are not persisted, no query can list current holds from the database. The `/metrics`
seat-lock count reads from Redis; `FR-ADR-057` carries how, and why a `SCAN` over up to 220 keys per
showtime needs care.

The Lua release script is a single deployable artifact whose content is part of the correctness
guarantee. It gets its own test asserting that a wrong token does not delete.
