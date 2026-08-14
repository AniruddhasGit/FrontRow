# A seat is never sold twice: the guarantee is enforced twice, and the database half may not be waived

```
ADR id ............ FR-ADR-024
Pack .............. PACK-CONC
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-001 §2.2; SRC-001 §3.2; SRC-001 §7.1; SRC-002 §8.1.5; SRC-002 §8.1.2; SRC-002 §9.1
Constitution ...... frontrow-constitution@0.1.0
```

> This is the central record of the project. `SRC-001 §2.2` calls eliminating double-booking
> "non-negotiable" and `§7.1` says a seat sold twice is a failure of the whole system regardless of
> load. Everything in `PACK-CONC` exists to make that testable rather than hoped for.

## Context

`SRC-001 §1.2` says the client currently has disputes where two customers are sold the same seat.
That is the problem the product was commissioned to solve, and `§2.2` and `§7.1` state it in
absolute terms: not "rare", not "under normal load" — never.

`SRC-002 §8.1` describes a Redis lock. `SRC-002 §8.1.5` separately requires a database guard, "so
that Redis being wrong cannot oversell a seat". Those are two mechanisms and the mandate asks for
both, which is unusual enough that it needs recording as a decision rather than left as two clauses
someone might read as alternatives.

## Decision

**The guarantee is enforced twice, in two different systems, and neither alone satisfies it.**

**Redis provides the hold.** A lock per `(showtime_id, seat_id)`, acquired atomically, carrying an
owner token, expiring on its own. It answers "can this customer start checking out with this seat".
Mechanics are in `FR-ADR-025`.

**PostgreSQL provides the truth.** A **unique constraint on `(showtime_id, seat_id)`** on the table
that records seat occupancy, plus row locking in the confirm transaction. It answers "does this seat
belong to this booking". Mechanics are in `FR-ADR-029`.

**The database guard may not be waived, at any confidence, for any reason.** Redis is a cache and a
lock service. Losing it, or having it be wrong, must degrade the product and must never corrupt it.
Waiving a quality check is reserved to the client under Art III.8, and this is the check.

**The constraint is total, not partial.** No `WHERE status <> 'cancelled'` clause. `FR-ADR-013` rules
out cancellation in v1, so a partial index would exclude a state that cannot occur while making the
guard conditional. **If cancellation is ever added, this constraint must be revisited before it,**
because a cancelled booking holding a seat forever is what a total constraint would then produce.

**The unique constraint is declared on the seat-occupancy table** — one row per (booking, seat) —
not on the booking. A booking holds up to ten seats (`FR-ADR-026`), so the guard has to be at seat
granularity.

**Why two systems rather than the better one.** A database-only design would need every seat
selection to hold a row lock for the duration of checkout, which is a three-minute transaction held
open across a payment step, on a `db.t3.micro` with roughly 110 connections. A Redis-only design has
no truth to fall back on when Redis is wrong. Each covers the other's failure mode, and
`SRC-002 §8.1.5` says so in one sentence.

## Alternatives rejected

**Redis lock only, trusting the TTL.** Rejected by `SRC-002 §8.1.5` and by reasoning: a Redis restart,
an eviction under memory pressure, a clock difference, or a bug in the release path each produce two
holders, and there is then nothing to stop two bookings.

**Database only, holding a row lock for the whole checkout.** Rejected on connection exhaustion, above.
It is also worse for the customer — a lock waiter blocks rather than being told the seat is taken.

**Advisory locks in PostgreSQL instead of Redis.** Rejected. It would work, and it would remove
Redis from the seat path entirely — which `SRC-002 §4.4` puts there deliberately, and which
`§1.3` wants the client to operate. It also moves three-minute holds into database session state on
the instance that took them, which breaks `§7.3`'s stateless containers.

**A partial unique index excluding cancelled bookings, for future-proofing.** Rejected above. It makes
the guard conditional today to accommodate a state that does not exist.

**Application-level checking before insert.** Rejected. `GOTCHAS.md` records why: `SELECT ... FOR
UPDATE` on rows that do not exist locks nothing, so two transactions both find no booking for the
seat, both proceed, and both insert. The unique constraint is the only thing that catches that.

## Source

`SRC-001 §2.2` (non-negotiable) · `§3.2` (zero double-booked seats under concurrent load) ·
`§7.1` (a failure of the whole system regardless of load) · `SRC-002 §8.1.5` (the database guard and
its reason) · `§8.1.2` (atomic acquisition) · `§9.1` (the proof).

## Consequences

Every code path that writes seat occupancy goes through the constrained table. There is no
alternative write path, no bulk insert that bypasses it, and no `ON CONFLICT DO NOTHING` that turns a
violation into silence.

A unique violation on confirm is a normal, expected outcome — it is the guard working — and it is
translated into the "someone took that seat" message `SRC-001 §5.2.6` requires. It is not an error to
be logged and swallowed. `FR-ADR-029` carries the translation.

**A guard nobody has watched fail is decoration.** `FR-ADR-034` carries the red-proof drill: drop the
constraint on purpose, watch the stress script produce more than one winner, restore it, verify the
restore.

The constraint must exist before Phase 4 ships, and it is created in the Phase 2 migration rather than
alongside the booking code, so that no window exists in which bookings can be written without it.
