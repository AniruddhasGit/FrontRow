# What the customer is told when SES fails after payment is captured

```
ADR id ............ FR-ADR-049
Pack .............. PACK-UX
Decision type ..... RESERVED
Decision owner .... client
Decision status ... NOT_DECIDED
Decision outcome .. HOLD_PENDING_DECISION
Decided by ........ (none — reserved: product)
Decision date ..... (none)
Source ............ SRC-003 OPEN-EMAILFAIL-01; SRC-003 OPEN-EMAIL-01; SRC-003 OPEN-TICKET-01; SRC-002 §8.5.2
Constitution ...... frontrow-constitution@0.1.0
```

> **This record exists so the question is visible and traceable. It decides nothing.**
> `OPEN-EMAILFAIL-01` is a live Article X row, owned by the client, class **reserved: product**.

## Context

Three of the client's own rulings combine into a failure mode none of them anticipated on its own.

`OPEN-BOOK-02` requires an account "as the recipet will be sent via mail". `OPEN-TICKET-01` makes the
unique id on that receipt the thing that gets the customer into the hall. `OPEN-EMAIL-01` adds SES to
the stack and states the consequence plainly: **if SES fails, the customer has paid and cannot
enter.**

`FR-ADR-013` closes the obvious escape: there are no refunds. So a customer whose receipt never
arrives has paid, cannot get in, and cannot get their money back.

Everything the build session can do without a ruling has been done. `FR-ADR-031` makes the send
durable through an outbox, so a crash cannot lose the job. `FR-ADR-032` retries and dead-letters.
`FR-ADR-048` puts the reference on the confirmation screen and in the customer's bookings list, and
offers a resend.

**What remains is the case those do not reach:** SES has definitively refused, or the address is
undeliverable, and the customer is not looking at their bookings list. What are they told, when, and
by what channel — and does the booking's state change.

## Decision

**Not decided.** Reserved to the client under Art III.8. **No timeout defaults past a reserved
matter.**

The question, stated so it can be answered:

> The customer has paid. The receipt email has definitively failed — SES refused it, or the address
> bounced. They are not on the site. What happens?

The dimensions the answer has to cover, offered so the question is answerable rather than to
recommend one:

1. **Is the booking still valid?** Almost certainly yes — the seat is sold and no refund exists — but
   it needs saying, because the alternative is a booking that is confirmed and unusable.
2. **How is the customer reached, if the only channel has failed?** There is no phone number on the
   account and no second address. The honest answer may be that they cannot be reached, in which case
   the mitigation is entirely on the site.
3. **Does anyone find out?** Nothing watches the dead letter queue (`FR-ADR-068`), so today a failed
   receipt is invisible to the operator. An answer that depends on someone noticing needs an alarm,
   which is Zone C and needs a prep-queue row.
4. **What does the door do?** Entry is a person checking a reference (`OPEN-TICKET-02`). If the
   customer arrives with a reference from the confirmation screen and no email, is that accepted?
   That is a business-process answer, not a software one, and it may be the cheapest fix available.
5. **Does the booking record carry the failure?** `FR-ADR-032`'s `receipt_dispatch` row already holds
   `failed` with the error, so the data exists. Whether it surfaces anywhere is part of the answer.

**Until this closes, the mitigations already built stand and nothing further is invented.** The
reference is on the confirmation screen, in the bookings list, and resendable. Those exist because
`OPEN-EMAIL-01` asked for the on-screen id specifically.

## Alternatives rejected

**Rule that the booking stays valid and the customer uses the on-screen reference.** Rejected as the
tempting one. It is probably the answer, and it is still a product decision about what a customer is
entitled to when the business fails to deliver the thing they paid for. Art VII.3 forbids filling an
open row with something sensible.

**Auto-refund on a failed receipt.** Rejected outright. `FR-ADR-013` rules out refunds, and a refund
path invented for this case would be a money decision made by a model.

**Fail the booking if the receipt cannot be sent.** Rejected. It would mean rolling back a captured
payment and releasing seats after the customer was told they had them, which is a worse outcome and a
harder one to unwind.

**Send the receipt synchronously so the failure is visible at checkout.** Rejected. It contradicts
`SRC-002 §8.5.1`, it couples checkout to SES's availability, and it converts a delayed receipt into a
failed booking.

**Block Phase 5 until this closes.** Rejected. The send path, the outbox, the retries and the dead
letter queue are all buildable and are all correct regardless of the answer. Only the customer-facing
message and the booking's disposition wait.

## Source

`SRC-003 OPEN-EMAILFAIL-01` (the row as raised) · `OPEN-EMAIL-01` (SES is load-bearing; show the id on
screen) · `OPEN-TICKET-01` (the reference is what gets them in) ·
`SRC-002 §8.5.2` (retries and a dead letter path).

## Consequences

Phase 5 ships the mechanism and not the message. The PRD carries a placeholder that cites this record,
so nobody writes a plausible sentence into a screen and calls the question answered.

**SES sandbox makes this failure mode certain in early testing**, because a sandboxed SES can only
send to verified addresses. Every test booking to an unverified address exercises this path. That is
useful — the path gets exercised — and it must not be mistaken for the ruled behaviour.

`receipt_dispatch` already records the failure with the SES error, so whatever the client rules, the
data to act on exists.

**An alarm on a non-empty dead letter queue would make this visible to the operator.** It is not
ruled — `OPEN-OPS-01` ruled exactly one alarm — and it is the most useful thing the client could add
alongside answering this row. Carried as a recommendation in `FR-ADR-068`, not as a decision.
