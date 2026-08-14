# No tax line, no discounts, no fees — the price shown is the price paid

```
ADR id ............ FR-ADR-040
Pack .............. PACK-MONEY
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PRICE-02; SRC-003 OPEN-PRICE-03; SRC-001 §10.16; SRC-001 §10.17
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §10.16` asked about discount codes, student pricing and convenience fees. `§10.17` asked
whether tax is shown separately on the ticket, noting that tax is rarely reversible once bookings
exist. Both were raised as reserved: money, and `§10.17` also as legal.

The client answered "no discout for now" and, on tax, "no".

Both are real answers and both bind. Each also has a consequence worth writing down, because the
absence of a column is the kind of decision that looks like an oversight later.

## Decision

**No tax is shown, stored or computed.**

There is no tax column, no tax rate, no net-and-tax split, and no tax line on the receipt. The stored
total is a **single figure** and it is the whole of what the customer paid.

**No discounts of any kind.** No discount codes, no promotional pricing, no student or concession
rates, no membership pricing. There is no coupon entity, no discount column, and no field for one at
checkout.

**No fees.** No booking fee, no convenience fee, no service charge. The price the seat map shows,
summed, is what the payment step charges.

**What this means in one sentence, and it should be checkable by reading the code:** the amount
charged equals the sum of the per-seat prices from `FR-ADR-038`, with nothing added and nothing taken
away.

## Alternatives rejected

**Model a tax rate at zero percent, so it can be turned on later.** Rejected. A zero-rate tax field
implies a tax model that has not been designed, invites someone to set it, and would need a decision
about whether the stored price is tax-inclusive or tax-exclusive — a question with no answer, because
the client said there is no tax. It also produces a receipt line reading "Tax: ₹0.00", which is a
statement about tax that the client did not authorise.

**Store the total as a net amount plus a tax amount, both populated with the whole and zero.**
Rejected for the same reason, with the added cost that every sum has to decide which column it means.

**Add a discount column defaulted to zero for future flexibility.** Rejected under Art VII.6. A
discount is a money decision and modelling one nobody ruled is inventing a money decision in schema
form. `FR-ADR-013` makes the same argument about refunds and reaches the same place.

**Add a nullable `discount_code` on the booking, since it costs nothing.** Rejected. It costs the next
reader, who will reasonably conclude discounts exist somewhere in the system.

## Source

`SRC-003 OPEN-PRICE-02` ("no discout for now") · `OPEN-PRICE-03` ("no") · `SRC-001 §10.16` ·
`§10.17`.

## Consequences

**Recorded, not challenged: a real cinema in India would show GST on a ticket.** `SRC-003
OPEN-PRICE-03` records the client's own reasoning for why this is acceptable — no real money moves —
and records the consequence explicitly: **the stored total is a single figure and cannot be split
later.** A retrospective GST split across existing bookings would be guesswork, because nothing
records what portion was ever intended as tax.

That is the irreversible part of this decision and it is the reason the ruling was classed reserved.
It is written down here so that it is a known deferral rather than something discovered by an
accountant.

**If tax is ever added, it is a new decision and it is reserved**, and it applies from a date forward
rather than retroactively. Bookings taken before it stay as they are.

The absence of discounts keeps the checkout screen simple and keeps the price path to one function
(`FR-ADR-038`). That is a real benefit and it is worth naming, because a discount engine is the
component most likely to reintroduce a float on the money path.

The dashboard's revenue figure is the sum of what was charged, with no gross-versus-net distinction to
get wrong (`FR-ADR-043`).
