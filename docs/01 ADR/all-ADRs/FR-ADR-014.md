# A booking always belongs to a registered user; there is no anonymous order

```
ADR id ............ FR-ADR-014
Pack .............. PACK-DATA
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-BOOK-02; SRC-003 OPEN-ROLE-01; SRC-001 §9.2; SRC-001 §4.1; SRC-001 §5.4.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §4.1` grants a guest browsing rights and never says whether booking requires an account.
`§9.2` says one booking belongs to one customer, one showtime and one or more seats — but that was
listed under "assumptions we are making", and Art II.7 forbids an assumption hardening into a
constraint.

The question decides whether an order row can exist without a user row, which is a data model
question that reaches every table downstream of booking.

The client answered `OPEN-BOOK-02`: "no booking without an account as the recipet will be sent via
mail." `OPEN-ROLE-01` says the same thing from the other side: "the guest is someone who has no
account can browse but will need to amkee a account if want to purchase a ticket."

## Decision

**Browsing is open. Booking requires a registered account.**

- **A booking carries a non-null foreign key to a user row.** There is no anonymous order, no guest
  checkout, and no placeholder user.
- **A guest may see the seat map.** Reading availability is browsing. Guests are stopped at the point
  of holding a seat, not at the point of looking.
- **A guest cannot acquire a seat hold.** The hold is the first authenticated action, not the payment
  step. A hold consumes a scarce resource for three minutes and an unauthenticated actor can acquire
  an unbounded number of them.
- The customer's own booking list (`SRC-001 §5.4.2`) is reachable because the booking has an owner.

The email address the receipt goes to is the account's address. There is no separate
"delivery email" field on the booking, because there is no case where they differ.

## Alternatives rejected

**Guest checkout with an email address collected at payment.** Rejected by the ruling. It would also
break `SRC-001 §5.4.2` — a guest has no bookings list to return to — and would create a second
identity path for the receipt, which is the customer's only proof of purchase.

**Create a shadow user row for a guest at checkout.** Rejected. It satisfies the foreign key while
defeating the ruling, and it produces user rows nobody can log in to, in a system where nothing is
ever deleted.

**Stop the guest at payment rather than at the hold.** Rejected as the weaker option. An
unauthenticated hold endpoint lets anyone lock every seat in a 220-seat hall for three minutes with
no account and no rate-limit key beyond an IP address. Stopping at the hold is stricter and under
Art III.10 needs no signature.

**Stop the guest at the seat map.** Rejected as too strict and contrary to `SRC-001 §4.1`, which
grants browsing. Seeing what is available is the thing that makes someone register.

## Source

`SRC-003 OPEN-BOOK-02` (the ruling) · `OPEN-ROLE-01` (the same rule from the guest's side) ·
`SRC-001 §9.2` (one booking, one customer — an assumption, now confirmed) · `§4.1` (guests browse) ·
`§5.4.2` (customers see their bookings).

## Consequences

Every seat-hold and booking endpoint sits behind authentication. That is one authorisation dependency
on one router, per Art VI.4, not a check inside each handler.

The rate limiter has a real user key to work with on the booking path, not only an IP address behind
an ALB. `FR-ADR-058` depends on that.

The registration flow is on the critical path to a first booking, which makes its friction a
conversion problem. Where the guest is stopped, and whether their seat selection survives the
round trip, is decided in `FR-ADR-046`.

Whether an account must verify its email before it can book is a separate question and is decided in
`FR-ADR-050`. It matters here because the receipt is the only proof of purchase and an unverified
address means an undeliverable one.
