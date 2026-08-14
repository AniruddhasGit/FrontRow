# The emailed receipt is the only proof of purchase, so the reference is also shown on screen

```
ADR id ............ FR-ADR-048
Pack .............. PACK-UX
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-TICKET-01; SRC-003 OPEN-TICKET-02; SRC-003 OPEN-EMAIL-01; SRC-003 OPEN-BOOK-02; SRC-001 §5.3.4; SRC-001 §5.4.2; SRC-001 §E E-9; SRC-002 §E E-5
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.3.3` asked for a scannable ticket and `SRC-002 §8.5.1` had the worker generate a QR code.
Both are withdrawn. The client ruled: "the receipt sent on email which has a unique ID. that will be
shown at the entrance", and separately "we will have manual check up with the unique ID".

That makes one email the load-bearing artefact of the entire product. `SRC-003 OPEN-EMAIL-01` states
the consequence in the client's own filing: **if SES fails, the customer has paid and cannot enter.**

It also says what to do about the part that is not reserved: the booking page must show the reference
on screen as well.

## Decision

**The receipt email carries: the booking reference, the seat numbers, the hall, the showtime, the
movie title, and the total paid.** That is `SRC-001 §E E-9`'s list plus the movie and the amount,
because a receipt without either is not a receipt.

**No QR code.** Not in the email, not on the confirmation screen, not anywhere
(`SRC-002 §E E-5`).

**The reference is displayed on the confirmation screen, prominently, immediately on confirmation** —
before and independently of the email being sent. The confirmation screen does not wait for the worker
and does not claim the email has been sent, because at that moment it has not been: the send is
asynchronous through the outbox and the queue (`FR-ADR-031`).

**The screen says what has actually happened.** "Your booking is confirmed. Your reference is
`FR-ABCD-EFGH`. A receipt is on its way to `<address>`." Not "we have sent you an email", which is a
claim about something that has not occurred yet and may not.

**The reference appears in three places, all reading from the same booking row:** the confirmation
screen, the customer's bookings list (`SRC-001 §5.4.2`), and the email. A customer who loses the email
can find it by signing in — that is the mitigation available without ruling on `OPEN-EMAILFAIL-01`.

**Formatted for reading aloud** — `FR-ADR-015`'s `FR-XXXX-XXXX` grouping — in a monospaced face at a
size that survives a phone screen at arm's length at a door.

**A resend control on the customer's booking page**, which re-enqueues the receipt job. It is
rate-limited per booking. It is a convenience for a customer who deleted the email; **it is not the
answer to SES failing**, because a customer who never received anything may not know to look.

**What the customer is shown when SES fails after payment is captured is not decided here.** That is
`OPEN-EMAILFAIL-01`, reserved, and carried as `FR-ADR-049`.

**No entry validation exists.** No scanner, no validation endpoint, no used-ticket state
(`OPEN-TICKET-02`). Entry is a person reading the reference and checking it. **Nothing prevents the
same reference being presented twice**, and that is an accepted weakness of a demonstration project,
recorded in `SRC-003 OPEN-TICKET-02` and carried into the architecture folder's list of deliberate
gaps.

## Alternatives rejected

**Wait for the email to send before showing the confirmation screen.** Rejected. It couples a
synchronous customer-facing response to SES's availability, which is what the queue exists to avoid,
and it would make a slow SES look like a failed booking.

**Say "we have emailed you a receipt" on the confirmation screen.** Rejected under Art VII.1. At that
moment it is not true, and it may not become true.

**Show only the reference and not the seat details on screen.** Rejected. A customer who never
receives the email needs the whole thing, and it is already on the page.

**Add a QR code as a convenience alongside the reference.** Rejected by `SRC-002 §E E-5` and
`SRC-001 §E E-9`, and there is nothing to scan it with.

**Offer a downloadable PDF ticket.** Rejected under Art VII.6. Nobody asked for it, it is a new
dependency for PDF generation under `SRC-002 §13.1`, and it does not solve the failure it appears to
solve — a customer who did not get the email is not on the page to download anything.

**Make the resend control the answer to `OPEN-EMAILFAIL-01`.** Rejected. It requires the customer to
notice, and what they are told is the reserved part.

## Source

`SRC-003 OPEN-TICKET-01` (the reference on the emailed receipt gets them in) ·
`OPEN-TICKET-02` (manual human check, no scanner) · `OPEN-EMAIL-01` (the receipt is load-bearing; show
the id on screen too) · `OPEN-BOOK-02` (the receipt is why an account is required) ·
`SRC-001 §5.3.4` (send a confirmation by email) · `§5.4.2` (customers see their bookings) ·
`§E E-9` · `SRC-002 §E E-5`.

The wording rule, the three placements and the resend control are the build session's under Art III.9.

## Consequences

The email address on the account is the delivery address (`FR-ADR-014`), which makes whether that
address is verified a load-bearing question rather than a hygiene one. `FR-ADR-050` decides it.

The confirmation screen is a durable page reachable again from the bookings list, not a one-time
interstitial. A customer who closes it has lost nothing.

**Every mitigation here reduces the blast radius of an SES failure without deciding what
`OPEN-EMAILFAIL-01` asks.** The reference is on screen, in the list, and resendable. What the
customer is *told* when the send has definitively failed is still the client's to rule.

The receipt's layout, sender name and branding are PRD-level detail and are not decided here. The
sender identity itself is blocked on the domain (`FR-ADR-060`, `OPEN-TLS-01`).
