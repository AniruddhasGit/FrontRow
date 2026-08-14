# The confirm transaction: what is inside it, in what order, and what a unique violation means

```
ADR id ............ FR-ADR-029
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.1.5; SRC-002 §8.3.1; SRC-001 §5.3.1; SRC-001 §5.3.2; SRC-001 §7.5; SRC-001 §5.2.6; SRC-002 §7.3
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.1.5` requires "a unique constraint on `(showtime_id, seat_id)` plus optimistic locking or
`SELECT ... FOR UPDATE`". It offers two options and does not choose. `SRC-001 §5.3.1` requires payment
before confirmation. `§7.5` requires that killing a container mid-request loses no money and leaves
nobody holding a seat they did not get.

Together those clauses constrain the ordering of five things — the idempotency record, the lock check,
the payment capture, the booking insert, and the queue enqueue — without specifying it. Every ordering
has a crash window and they are not equally bad.

`GOTCHAS.md` records the trap that decides one of them: `SELECT ... FOR UPDATE` on rows that do not
exist locks nothing. Two transactions both find no booking for a seat, both proceed, both insert. The
row lock cannot protect a row that is not there.

## Decision

**Isolation level: `READ COMMITTED`, PostgreSQL's default.** The correctness guarantee is the unique
constraint, which holds at every isolation level. Raising to `SERIALIZABLE` would add serialisation
failures and retries to every booking to protect against an anomaly the constraint already prevents.

**The unique constraint is the guard. `SELECT ... FOR UPDATE` is not, and is used only where it
actually helps** — locking the showtime row to serialise the cut-off check and the price read against
a concurrent admin edit (`FR-ADR-035`). It is not used to "check whether the seat is free", because
that check has nothing to lock.

**Order inside one transaction:**

1. **Insert the idempotency record** (`FR-ADR-020`). A unique violation here means this is a duplicate
   request; the transaction rolls back and the duplicate path runs. Nothing else has happened yet.
2. **Re-validate the hold in Redis** — every seat's key still exists and carries this hold's token.
   If not, roll back with 409 "your hold expired". This is a check against Redis inside a database
   transaction, which is unusual and deliberate: it costs a read and it stops a customer confirming
   seats that were released and re-taken while they were paying.
3. **`SELECT ... FOR UPDATE` the showtime row.** Serialises against a concurrent admin price change
   and gives the cut-off check a stable read.
4. **Check the sales cut-off** (`FR-ADR-042`).
5. **Compute and snapshot the price** (`FR-ADR-039`).
6. **Capture payment through the simulated provider** (`FR-ADR-041`).
7. **Insert the booking and its seat-occupancy rows.** The unique constraint fires here if it is going
   to.
8. **Insert the audit row** if the action is privileged. A customer booking is not (`FR-ADR-019`).
9. **Update the idempotency record** to `completed` with the response body.
10. **Commit.**

**The queue enqueue is outside the transaction** and is decided in `FR-ADR-031`.

**Why payment is captured before the insert, given that leaves a crash window.** `SRC-001 §5.3.1`
requires payment before confirmation, so the order is not free. The window — captured, then the
process dies before commit — is what `SRC-001 §7.5` is about, and it is closed by two things: the
capture is against the simulated provider and is idempotent on the idempotency key
(`FR-ADR-041`), and the transaction rolls back, so the retry with the same key finds the
`in_progress` record and replays rather than capturing again. **No money is captured twice and no
seat is booked without a capture.**

**A unique-constraint violation at step 7 is not an error. It is the guard working.** It is caught,
translated into a 409 naming the seats that were taken, and returned as the "someone took that seat"
message `SRC-001 §5.2.6` requires. It is **not retried** — retrying a lost race just loses it again,
slower — and it is **not** logged as an exception. It is logged as an expected outcome with a counter,
because the rate at which it fires is the signal that tells the operator the lock layer has a problem.

**The Redis locks are released after commit, not before, and not inside the transaction.** Releasing
before commit opens a window where the seat is free and unbooked. Releasing inside the transaction
does nothing, because Redis does not roll back. If the release fails, the keys expire on their own
within three minutes and the seats are already booked, so the database refuses anyone else.

## Alternatives rejected

**`SERIALIZABLE` isolation.** Rejected above: retries on every booking to prevent an anomaly the
constraint already prevents, on a `db.t3.micro`.

**Optimistic locking with a version column on the showtime.** The other option `§8.1.5` offers.
Rejected because the contention is between bookings on *different seats* of the same showtime, which a
showtime version column would serialise unnecessarily — every booking on a busy show would conflict
with every other.

**`SELECT ... FOR UPDATE` on the seat rows to reserve them.** Rejected. It locks the permanent seat
row, which every showtime on that screen shares, so two bookings on different showtimes in the same
hall would block each other.

**`INSERT ... ON CONFLICT DO NOTHING` on the seat-occupancy rows.** Rejected. It turns the guard into
silence: the booking commits with fewer seats than the customer paid for and no error anywhere. The
violation must be raised.

**Capture payment after the booking commits.** Rejected by `SRC-001 §5.3.1`, and it produces the worse
crash window — a confirmed booking with no payment, which is a seat given away.

**Retry the whole transaction on a unique violation.** Rejected above.

## Source

`SRC-002 §8.1.5` (the constraint plus row locking) · `§8.3.1` (idempotency) ·
`SRC-001 §5.3.1` (payment before confirmation) · `§5.3.2` (never charge twice) ·
`§7.5` (recoverability) · `§5.2.6` (tell the customer immediately) · `SRC-002 §7.3` (stateless).

The ordering, the isolation level and the violation handling are the build session's under Art III.9.

## Consequences

The transaction spans a payment capture, which makes it longer than a database transaction should
normally be. That is bounded by the simulated provider's artificial delay, which `FR-ADR-041` caps
well below the three-minute hold. **If a real provider were ever introduced, this ordering would have
to be revisited** — a multi-second external call inside a database transaction on a host with roughly
110 connections is a different problem. `FR-ADR-041` rules out a real provider entirely, so the
problem does not arise, and this sentence records why the shape is acceptable here and would not be
elsewhere.

The Redis re-validation at step 2 means the confirm path fails when Redis is down (`FR-ADR-028`),
which is the ruled behaviour.

Two multi-seat bookings with overlapping seats can no longer deadlock, because `FR-ADR-026` acquires
locks in seat-id order and the losing request never reaches the transaction.

The 409-on-violation path needs a test that plants a conflicting row and asserts the message, and the
stress script (`FR-ADR-034`) asserts the shape of all forty-nine losers.
