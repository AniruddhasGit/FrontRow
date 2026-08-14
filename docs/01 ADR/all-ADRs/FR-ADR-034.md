# The concurrency proof, and the red-proof drill that stops it being decoration

```
ADR id ............ FR-ADR-034
Pack .............. PACK-CONC
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-002 §9.1; SRC-002 §9.2; SRC-001 §3.2; SRC-001 §7.1; SRC-003 OPEN-SCALE-03; SRC-002 §8.1.5
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §9.1` requires `scripts/stress_seats.py` to fire 50 simultaneous requests for the same seat
and assert exactly one succeeds, runnable against local Docker and against the deployed environment by
changing a base URL. That is the client's own acceptance criterion for the thing the product exists
to do.

`GOTCHAS.md` records two ways this proof can pass while proving nothing.

**The script may not actually be concurrent.** Fifty requests from one Python process using a single
event loop, one connection pool, or `requests` in a thread pool can serialise enough that the race
never happens — and the test then passes against genuinely broken code.

**A test that proves the lock works does not prove the constraint works.** With Redis healthy the
database guard never fires, so a missing unique constraint passes every normal test. That is why
Art IV.5 requires the guard to be watched failing.

## Decision

**`scripts/stress_seats.py`, as `SRC-002 §9.1` specifies**, with these additions.

**The script proves its own concurrency before it trusts its result.** It records the start instant of
each of the fifty requests and asserts the spread between first and last is small — a configured
threshold, defaulting to 100 ms. **If the spread is too wide the script fails with "not concurrent",
not with "passed".** A proof that cannot distinguish a passing system from a serialised client is not
a proof.

**Fifty distinct authenticated customers**, seeded for the purpose. Holding requires an account
(`FR-ADR-014`), and fifty requests from one account would be caught by the per-user rate limiter
(`FR-ADR-058`) and would measure the limiter rather than the lock.

**The rate limiter is not disabled for the run.** Fifty distinct users against a per-user bucket do not
trip it, and per-IP limiting is configured to permit the test's source. Disabling a control to make a
test pass is the shape of a fake green.

**Assertions, at both layers:**

- Exactly **one** HTTP 200 and **forty-nine** 409s. Not "at most one" — exactly one, because zero
  winners is also a failure.
- Exactly **one row** in the seat-occupancy table for that `(showtime_id, seat_id)`, read directly
  from PostgreSQL. **The HTTP assertion alone is not sufficient.** `SRC-001 §3.2` says zero
  double-booked seats and the seat is a database row, so the database is where the claim is settled.
- The forty-nine losers carry the "someone took that seat" shape `SRC-001 §5.2.6` requires, not a 500.

**The red-proof drill, run by hand and recorded:**

1. Run the script. Observe one winner.
2. **Drop the unique constraint on `(showtime_id, seat_id)`.**
3. Run the script again. **Observe more than one winner.** If it still produces one winner, the test
   is not exercising the constraint and the whole proof is void — that outcome is a stop-the-line
   finding, not a pleasant surprise.
4. Restore the constraint.
5. **Verify the restore** by re-running the script and observing one winner again, and by reading the
   constraint back from the catalogue.

**Where the drill runs: locally only.** Dropping a correctness constraint in the deployed environment
is a destructive schema change, and `FR-ADR-003` gives the build session no write access to AWS at
all. The client may run it there themselves; the specification in `docs/30 Deployment/` says how and
says plainly what it does.

**The stress script itself runs against both**, by base URL, exactly as `§9.1` requires. Only the
constraint-dropping step is local.

**The light load test** (`§9.2`) is a separate script at **50 concurrent bookers** — `ASSUMED`, from
`OPEN-SCALE-03` where the client said "you pick". It reports where performance degrades. It proves
nothing about correctness and may never be cited as if it did.

## Alternatives rejected

**Assert "at most one winner".** Rejected. Zero winners passes, and zero winners means the endpoint is
broken.

**Assert only at the HTTP layer.** Rejected. A bug that returns 200 to one caller while writing two
rows is precisely the failure being hunted.

**Use one authenticated user for all fifty requests.** Rejected on the rate limiter, above.

**Disable rate limiting during the run.** Rejected. Waiving a quality check is reserved to the client
under Art III.8, and this is a control the production path relies on.

**Skip the red-proof because the constraint is obviously there.** Rejected. Art IV.5 forbids it and
Art III.8 makes waiving a quality check reserved. A gate nobody has watched fail is decoration.

**Run the red-proof against the deployed environment for a stronger result.** Rejected on
`FR-ADR-003`. It is also the one place where an interrupted drill leaves a live system with no
oversell guard.

## Source

`SRC-002 §9.1` (the script and its assertion) · `§9.2` (the light load test) ·
`SRC-001 §3.2` (zero double-booked seats under concurrent load) · `§7.1` (regardless of load) ·
`SRC-003 OPEN-SCALE-03` `ASSUMED` (50 concurrent bookers) · `SRC-002 §8.1.5` (the constraint being
proved).

The self-concurrency check, the two-layer assertion and the drill's local-only scope are the build
session's under Art III.9.

## Consequences

**This gate is never waived, never skipped, and never marked expected-to-fail.** A red concurrency
gate blocks the story it belongs to; the story is marked `Blocked` with a note and surfaced. That is
Art IX.2 and it has no exception.

The drill is a manual procedure with a recorded outcome, and the record says who ran it and when. An
undated claim that it was run is not evidence.

Fifty seeded customers are needed before Phase 4, which makes them a seed script requirement, not a
test fixture. `FR-ADR-067` carries the seed script's scope.

Running the script against the deployed environment writes real bookings there. The specification must
say so, and say which showtime to point it at.
