# An admin edit cannot change the price a customer is already holding seats at

```
ADR id ............ FR-ADR-035
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PRICE-01; SRC-003 OPEN-OPS-03; SRC-001 §5.2.4; SRC-001 §5.5.1; SRC-002 §8.1.5
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.5.1` lets the admin create showtimes with a price band and `SRC-003 OPEN-PRICE-01` lets
them set a base price per showtime and a percentage uplift per seat category. `OPEN-OPS-03` puts every
privileged write on the admin.

None of those say what happens when an admin exercises one of those writes **while a customer is
holding seats on the affected showtime**. Three cases, all reachable:

- The admin changes a showtime's base price while a customer is at checkout.
- The admin changes a category uplift, which applies uniformly across every hall and show
  (`OPEN-PRICE-01`), so it affects every live checkout at once.
- Two admins edit the same movie or showtime at the same time.

`SRC-001 §5.2.4` requires the total to update as seats are selected. A customer who sees ₹950 and is
charged ₹1,100 has been shown a false price.

## Decision

**The price a customer pays is the price that was current when their hold was granted.**

At hold acquisition the API computes the per-seat prices and stores them **with the hold, in Redis,
under the hold token**. At confirmation those stored prices are used, not recomputed. `FR-ADR-039`
carries the snapshot onto the booking row at commit.

The window is bounded by the hold: at most three minutes of price protection, which is the same
duration as the seat protection and needs no separate expiry.

**Admin price edits are allowed at any time and take effect for holds acquired after them.** They are
not blocked, because blocking them would mean one customer sitting at a checkout screen freezes
pricing for a whole showtime.

**A category uplift change is allowed and affects only future holds**, for the same reason and by the
same mechanism.

**The confirm transaction takes `SELECT ... FOR UPDATE` on the showtime row** (`FR-ADR-029` step 3).
That is not there to prevent the edit — it is there so the cut-off check and any price read inside
the transaction see one consistent version of the showtime rather than a value that changes
mid-transaction.

**Two admins editing the same row: optimistic concurrency with a `version` integer.** The client sends
the version it read; a mismatch returns **409** with "this was changed by someone else" and the admin
re-reads. Last-write-wins is rejected because a silently discarded edit to a price is a money error
nobody sees. This applies to `movie`, `showtime`, `screen` and `seat_category`.

**A showtime whose start time is edited re-derives its cut-off**, because the cut-off is derived and
never stored (`FR-ADR-018`). A customer holding seats on a showtime that has just been moved earlier
past the cut-off may still complete — the cut-off is checked at hold acquisition and the hold is
honoured, matching `OPEN-BOOK-03`'s rule that existing holders may finish checking out.

**What is not decided here:** what an admin *withdrawing* a showtime does to live holds and in-flight
checkouts. That depends on what withdrawal does to paid bookings, which is `OPEN-SHOWCANCEL-01` and
is reserved. **This record is blocked on `FR-ADR-023` for that case and does not resolve it.** The
capability does not exist in v1, so the case cannot arise yet.

## Alternatives rejected

**Recompute the price at confirmation from the live base price and uplift.** Rejected. It is the
simpler implementation and it charges the customer a price they were never shown, which
`SRC-001 §5.2.4` rules out.

**Block admin price edits while any hold exists on the showtime.** Rejected. One customer with an open
tab would freeze pricing for three minutes at a time, indefinitely, on a busy show.

**Store the held price in PostgreSQL rather than with the Redis hold.** Rejected. It reintroduces the
hold table that `FR-ADR-025` refused, and it would need its own expiry — the cleanup job `§8.1.4`
removes. The price expires with the hold, which is exactly the lifetime it should have.

**Last-write-wins for concurrent admin edits.** Rejected above.

**A row lock on the showtime for the whole admin edit.** Rejected as heavier than optimistic
concurrency for a conflict that will be rare with one admin, and it would hold a lock across a form
submission.

## Source

`SRC-003 OPEN-PRICE-01` (base price per showtime, uniform category uplift) ·
`OPEN-OPS-03` (admin-only writes) · `SRC-001 §5.2.4` (the total updates as seats are selected) ·
`§5.5.1` (the admin sets the price) · `SRC-002 §8.1.5` (row locking in the confirm path).

The snapshot-at-hold rule and optimistic concurrency are the build session's under Art III.9.

## Consequences

The hold in Redis now carries more than a token: the seat list and the per-seat prices. It is still a
single key per hold plus the per-seat lock keys, and it still expires as one unit.

An admin changing a price cannot see which customers are mid-checkout at the old price. That is
acceptable — the window is under three minutes — and the audit row records the change with its before
and after (`FR-ADR-019`), so the difference is reconstructable.

The `version` column adds one integer to four tables and one comparison to each admin update. Every
admin form must round-trip it, which is a small discipline that has to be applied consistently or the
protection is absent on whichever form forgot.

With one admin account in practice, concurrent admin edits will be rare. The control exists because
"rare" and "impossible" are different, and because the client may add a second admin.
