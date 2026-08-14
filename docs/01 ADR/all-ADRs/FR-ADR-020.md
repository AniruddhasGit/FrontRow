# The idempotency record lives in Postgres and is inserted before the work, not after

```
ADR id ............ FR-ADR-020
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.3.1; SRC-001 §5.3.2; SRC-002 §7.9; SRC-003 OPEN-OPS-02
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.3.1` requires the booking confirmation endpoint to take an `Idempotency-Key` header, with
a retry of the same key returning the original result rather than creating a second booking.
`SRC-001 §5.3.2` states the customer-facing version: never charge a customer twice for one booking
attempt, including on refresh or double-click.

The clause says what must happen. It does not say where the key is stored, what its scope is, how long
it lives, or what happens when the same key arrives twice at the same moment — and that last one is
where the naive implementation fails.

`GOTCHAS.md` records the trap: an idempotency key stored **after** the work is done is not idempotent.
Two simultaneous retries both check, both find nothing, and both book.

## Decision

**A table in PostgreSQL, not Redis.**

| Column | Holds |
|---|---|
| `id` | `bigint` identity |
| `user_id` | non-null foreign key. The key is scoped per user |
| `idempotency_key` | the client's header value, `text` |
| `request_fingerprint` | a hash of the canonicalised request body |
| `status` | `in_progress` or `completed` |
| `booking_id` | nullable foreign key, set when the booking commits |
| `response_body` | `jsonb`, the response that was returned |
| `created_at`, `completed_at` | `timestamptz` |

**Unique constraint on `(user_id, idempotency_key)`.**

**The row is inserted first, in the same transaction as the booking, before any work happens.** The
insert either succeeds — this request owns the key — or it violates the unique constraint, in which
case this request is a duplicate and reads the winner's row. There is no check-then-act window,
because the database's unique index *is* the check and the act.

**In Postgres and not Redis, for three reasons.** It has to be in the same transaction as the booking
insert, which a second data store cannot be. `SRC-002 §7.9` says Redis being down must not corrupt
anything, and an idempotency guard in Redis would vanish with it. And under `FR-ADR-012` nothing is
deleted, so the record is permanent rather than TTL'd.

**Behaviour on a duplicate:**

- **The winner has committed** (`status = completed`): return the stored `response_body` with the
  original status code. Never a second booking, never a second charge.
- **The winner is still in flight** (`status = in_progress`): return **409 Conflict** with a
  `Retry-After`. Not a block, not a wait, and not a replay of a result that does not exist yet. Making
  the second request wait ties up a connection on a 1 GB host for as long as the first takes.
- **The same key with a different `request_fingerprint`**: return **422**. The key has been reused for
  a different request, which is a client defect, and honouring it would return one booking's result
  for another booking's request.

**A missing `Idempotency-Key` header on booking confirmation is a 400.** The header is required, not
optional. An optional idempotency guard is one that the double-click path skips.

**The record is never expired.** `FR-ADR-012` says nothing is deleted, and a key that expires is a key
whose retry after the window creates a second booking.

## Alternatives rejected

**Store the key in Redis with a TTL.** Rejected on all three grounds above. It is the common answer
and it fails this project's specific constraints.

**Check for an existing key, then insert if absent.** Rejected — this is the trap. Two concurrent
retries both pass the check.

**Insert the key after the booking commits.** Rejected for the same reason, with the added failure
that a crash between commit and key-write leaves a booking with no idempotency record, so the retry
books again.

**Scope the key globally rather than per user.** Rejected. Two customers can generate the same key —
a client library with a weak generator, or a copied cURL command — and one would receive the other's
booking. Per-user scoping makes a collision harmless.

**Block the second request until the first completes, then return its result.** Rejected. It is the
friendlier behaviour and it holds a database connection and a worker slot for the duration, on a host
with roughly 110 available connections. 409 with `Retry-After` is honest and cheap.

## Source

`SRC-002 §8.3.1` (the header and the required behaviour) · `SRC-001 §5.3.2` (never charge twice) ·
`SRC-002 §7.9` (Redis loss must not corrupt) · `SRC-003 OPEN-OPS-02` (nothing is deleted).

Storage, scope, and the three duplicate behaviours are the build session's under Art III.9.

## Consequences

The booking confirm transaction gains one insert at its head. That insert is the serialisation point
for retries of the same key, which is exactly where it should be.

The 409-while-in-flight case needs a test that runs two requests concurrently with the same key. A
sequential test passes against a broken implementation, in the same way a sequential seat test passes
against a missing lock.

`response_body` stored as `jsonb` means a replayed response is byte-comparable to the original. If the
response shape ever changes, old replays return the old shape — which is correct, because they are
replays of an old request.

The table only grows, one row per booking attempt. It is smaller than `audit_log` and subject to the
same forever-retention.
