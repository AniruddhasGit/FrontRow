# The price paid is snapshotted onto every booked seat and is never recomputed

```
ADR id ............ FR-ADR-039
Pack .............. PACK-MONEY
Decision type ..... STRICTER_ADOPTION
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §7.6; SRC-003 OPEN-PRICE-01; SRC-003 OPEN-OPS-02; SRC-001 §5.2.4
Constitution ...... frontrow-constitution@0.1.0
```

## Context

Both inputs to the price are mutable. An admin can change a showtime's base price, and an admin can
change a seat category's uplift — which under `OPEN-PRICE-01` applies uniformly across every hall and
show, so one edit moves every future price at once.

If a booking's price is recomputed from those live values whenever it is displayed, then an admin
editing a price in September changes what a receipt from August says the customer paid.

`SRC-001 §7.6` makes bookings permanent and requires the system to answer who booked a seat and when.
A permanent record whose money figure moves is not a record.

## Decision

**The price is written onto the row at confirmation and is read from there forever after.**

**On `booking_seat`:**

- `price_paise` — the rounded per-seat price the customer paid, from `FR-ADR-038`.
- `seat_category_id` — the category **at the time of booking**, copied, not joined for display.
- `uplift_basis_points_applied` — the uplift that produced the figure.
- `base_price_paise_applied` — the showtime base price that produced it.

**On `booking`:**

- `total_paise` — the sum of the seat prices, from `FR-ADR-038`.

**The three inputs are stored alongside the output on purpose.** Storing only `price_paise` makes the
figure unauditable — nobody can tell whether ₹333.33 was a 33.33% uplift on ₹250 or a 25% uplift on
something else. `SRC-001 §7.6` asks the system to answer for its records, and four integers per row
is a small price for an answer that reconstructs itself.

**`total_paise` on the booking is denormalised and that is deliberate.** It could be summed from the
seat rows. Storing it means the receipt, the customer's booking list and the dashboard all read one
number rather than three implementations of a sum. A check at write time asserts it equals the sum,
and that assertion is a test, not a database constraint — a constraint here would need a trigger.

**Nothing recomputes.** No display path, no receipt, no dashboard, no export multiplies a base price
by an uplift for a booking that already exists.

**The price is fixed earlier than confirmation — at hold acquisition** (`FR-ADR-035`), so the customer
pays what they were shown. Confirmation copies that held figure onto the row; it does not recompute it
either.

## Alternatives rejected

**Store nothing and recompute from the showtime and category.** Rejected. An admin price edit
retroactively rewrites history, which `SRC-001 §7.6` forbids in substance even where it does not use
the word.

**Store only `price_paise` and drop the three inputs.** Rejected above: the figure becomes
unauditable, and the first dispute about a charge has no answer.

**Version the showtime price and the category uplift, and point each booking at a version.** This is
the fully normalised answer and it is correct. Rejected as disproportionate: two version tables, two
joins on the receipt path and the dashboard path, to avoid four integers per booked seat. Recorded as
the alternative to reach for if the client ever needs price history as a first-class reporting
dimension.

**Store the total only on the booking and not per seat.** Rejected. The receipt shows seat numbers
with their prices (`SRC-001 §E E-9` requires the seats on it), and the seat map showed a per-seat
figure (`§5.2.4`).

## Source

`SRC-001 §7.6` (bookings are permanent and auditable) · `SRC-003 OPEN-PRICE-01` (both price inputs
are admin-mutable) · `OPEN-OPS-02` (nothing is deleted, so these rows are read years later) ·
`SRC-001 §5.2.4` (the customer saw a per-seat figure).

Snapshotting is the stricter option and under Art III.10 needs no signature.

## Consequences

`booking_seat` carries four integers beyond its foreign keys. Against forever retention that is the
largest per-row cost in the schema after `audit_log`, and it is the cost of a booking record that can
answer for itself.

The dashboard's revenue figure sums `price_paise` from `booking_seat` — the money actually taken — and
never recomputes from current prices. `FR-ADR-043` depends on that.

Changing `FR-ADR-038`'s rounding rule later reprices nothing already sold. That is what makes the
rounding rule reversible and is why it could be decided by the build session at all.

An admin who mistypes a base price and corrects it five minutes later has already sold tickets at the
wrong price, and those bookings keep it. That is correct — the customer paid what they were shown —
and it is the operational reason the audit row records the before and after (`FR-ADR-019`).
