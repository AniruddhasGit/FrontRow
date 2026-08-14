# A booking is final — no cancellation and no refund — and the schema keeps `status` and `cancelled_at` anyway

```
ADR id ............ FR-ADR-013
Pack .............. PACK-DATA
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-CANCEL-01; SRC-003 OPEN-CANCEL-02; SRC-001 §E E-2; SRC-001 §6.6
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.4.3` required a customer to be able to cancel a booking within an allowed window.
`SRC-002 §12` had no phase for it. Under Art II.2 that is a conflict between the two frozen sources
and it went to the client as `OPEN-CANCEL-01` and `OPEN-CANCEL-02`, both classed reserved because
refunds are money and irreversible.

The answers were "no refund policy" and "no forget this."

Those two answers need reading together. "No refund policy" on its own would still permit cancelling
without a refund. Combined with "no forget this" the whole cancellation surface is out — and a
cancellation that returns no money is not a feature a customer would use.

## Decision

**A confirmed booking is final.**

- **No customer-initiated cancellation.** No endpoint, no button, no flow.
- **No refunds of any kind**, partial or full, for any reason, in v1.
- `SRC-001 §5.4.3` is withdrawn by erratum `E-2`.

**The schema still carries a booking `status` column and a `cancelled_at` timestamp, and no v1
endpoint exposes either.**

That is not hedging. `SRC-001 §6.6` says the client may ask for these later and forbids designing in
a way that blocks them, and adding a status column to a booking table that already holds real
bookings is a migration on live data with a backfill nobody can verify. Two columns that are never
written cost nothing now.

`status` is written once, at confirmation, to the confirmed value. `cancelled_at` stays null for
every row v1 ever creates. `FR-ADR-023` carries the one case that could change that — an admin
withdrawing a showtime that already has bookings — and it is unruled.

**What is deliberately not added:** no refund table, no refund amount, no cancellation reason, no
cancellation policy configuration. Those are the parts that require a money decision, and a money
decision that nobody made is worse than a missing column.

## Alternatives rejected

**Omit `status` and `cancelled_at` entirely, because v1 has no cancellation.** Rejected under
`SRC-001 §6.6`. This is the exact shape of the exclusion that hardens into an architectural
impossibility, which Art I.3 calls a defect.

**Add the whole cancellation model — status, reason, refund amount, policy — and leave the endpoints
off.** Rejected. A refund amount column implies a refund rule, and there is no ruled refund rule.
Modelling money movements nobody has authorised is inventing a money decision in schema form.

**Build cancellation without a refund, since "no refund policy" permits it literally.** Rejected on
the combined reading recorded in `SRC-003 OPEN-CANCEL-02`, and because it would be a feature that
takes a customer's seat and keeps their money — a worse product than not having it.

## Source

`SRC-003 OPEN-CANCEL-01` ("no refund policy") · `OPEN-CANCEL-02` ("no forget this") ·
`SRC-001 §E E-2` (§5.4.3 withdrawn) · `SRC-001 §6.6` (excluded is not blocked).

## Consequences

The payment path has no reverse. Once captured, a simulated payment is never unwound, which removes
an entire class of state transition from the payment interface.

A customer who cannot attend loses their money. That is the ruled behaviour for a demonstration
project and it would need revisiting before a real customer ever booked. Recorded as a known
deferral, not an oversight.

The unique constraint on `(showtime_id, seat_id)` can be **total rather than partial**. A partial
unique index excluding cancelled bookings would be required if cancellation existed; with no
cancellation, the simpler and stricter total constraint is correct. `FR-ADR-024` depends on this.
**If cancellation is ever added, that constraint has to be revisited first** — a cancelled booking
holding a seat forever is the failure it would cause.

`OPEN-SHOWCANCEL-01` remains open and is the one route by which a booking could still end up
cancelled. See `FR-ADR-023`.
