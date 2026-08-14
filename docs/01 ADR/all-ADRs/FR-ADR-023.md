# What happens to bookings and to the money when an admin withdraws a showtime

```
ADR id ............ FR-ADR-023
Pack .............. PACK-DATA
Decision type ..... RESERVED
Decision owner .... client
Decision status ... NOT_DECIDED
Decision outcome .. HOLD_PENDING_DECISION
Decided by ........ (none — reserved: money, irreversible)
Decision date ..... (none)
Source ............ SRC-003 OPEN-SHOWCANCEL-01; SRC-003 OPEN-OPS-03; SRC-003 OPEN-CANCEL-02; SRC-003 OPEN-CANCEL-01
Constitution ...... frontrow-constitution@0.1.0
```

> **This record exists so the question is visible and traceable. It decides nothing.**
> `OPEN-SHOWCANCEL-01` is a live Article X row, owned by the client, class
> **reserved: money, irreversible**.

## Context

Two of the client's own rulings point in different directions.

`OPEN-OPS-03` lists what only the admin may do: "changes in movie, **cancel a show** or other
priviledged things". So cancelling a show is a named admin capability.

`OPEN-CANCEL-02` — asked what happens when the cinema cancels a show, and whether refunds are
automatic — answered "no forget this". And `OPEN-CANCEL-01` answered "no refund policy".

The reconciliation recorded in `SRC-003 OPEN-OPS-03` is that there is no *customer-facing*
cancellation flow and no refunds, and that an admin withdrawing a showtime is a scheduling action
rather than a refund action. That reading is sound as far as it goes, and it stops exactly where the
money starts.

**It does not answer what happens to bookings that already exist on the withdrawn showtime.** Those
customers have paid. Under `FR-ADR-013` there are no refunds. So either they are refunded — which
contradicts a ruling — or they have paid for a show that will not happen and receive nothing, which
is a decision about money that no model may make.

## Decision

**Not decided.** Reserved under Art III.8 as money and as irreversible. **No timeout defaults past
this** — if the client is unavailable, the dependent work stops.

The question, stated so it can be answered in one message:

> An admin withdraws a showtime that already has confirmed, paid bookings. What happens to those
> bookings, and what happens to the money?

Four answers, each with a different consequence, offered so the question is easy rather than to
recommend one:

1. **Withdrawal is blocked once any booking exists.** No money question arises. The admin can only
   withdraw an empty showtime. Simplest, and it means a genuinely cancelled screening has no path in
   the system.
2. **Withdrawal is allowed; bookings become `cancelled`; no money moves.** Uses the `status` and
   `cancelled_at` columns `FR-ADR-013` already reserved. The customer loses their money.
3. **Withdrawal is allowed; bookings are cancelled and refunded.** Requires a refund model, which
   `FR-ADR-013` deliberately did not build, and contradicts `OPEN-CANCEL-01`.
4. **Withdrawal is out of scope for v1.** The admin capability named in `OPEN-OPS-03` is deferred and
   nothing is built.

**Until this closes, the admin has no withdraw-a-showtime capability.** That is the fail-closed
position under Art III.1: an unbuilt capability is recoverable, an unrefunded customer is not.

## Alternatives rejected

**Rule option 1 as the obviously safe answer.** Rejected, and this is the tempting one. Blocking the
withdrawal decides that a real cancelled screening has no representation in the system, which is a
product decision, and it strands a scenario the client explicitly named as an admin capability.
Art VII.3 forbids filling an open row with something sensible.

**Rule option 2 because no money moves and it therefore is not a money decision.** Rejected. Deciding
that a paying customer receives nothing when the business cancels is a money decision, and it is
irreversible for that customer.

**Build the capability behind an admin-only flag and decide later.** Rejected. A capability that
exists is a capability that will be used, and the first use is the irreversible one.

## Source

`SRC-003 OPEN-SHOWCANCEL-01` (the row as raised) · `OPEN-OPS-03` ("cancel a show" as an admin action)
· `OPEN-CANCEL-02` ("no forget this") · `OPEN-CANCEL-01` ("no refund policy").

## Consequences

`FR-ADR-013` already keeps `status` and `cancelled_at` on the booking row, which means options 2 and 3
need no migration on live data whenever the client answers. That is why those columns exist.

The showtime entity carries no `withdrawn_at` and no cancellation state in v1, because adding one
would imply a capability that is not built.

Phase 2's admin CRUD ships without showtime withdrawal, and that gap is stated to the client rather
than left for them to find. It is the only named admin capability from `OPEN-OPS-03` that v1 does not
deliver.

The concurrency question that follows from it — what a withdrawal does to live seat holds and
in-flight checkouts — is unanswerable until this closes, and `FR-ADR-035` records that it is blocked
on this row rather than pretending to resolve it.
