# The receipt job is enqueued through a transactional outbox, not a post-commit send

```
ADR id ............ FR-ADR-031
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.5.1; SRC-002 §E E-5; SRC-003 OPEN-EMAIL-01; SRC-003 OPEN-TICKET-01; SRC-002 §7.3; SRC-002 §8.5.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §8.5.1`, as corrected by erratum `E-5`, says: after a booking is confirmed, push a message to
the queue; the worker sends the receipt email.

That email is not a notification. `SRC-003 OPEN-EMAIL-01` and `OPEN-TICKET-01` together make it **the
customer's only proof of purchase and their only way into the hall**. A lost enqueue is a customer who
paid and cannot enter.

The obvious implementation — commit the transaction, then call the queue — has a window. The process
dies between the commit and the send, and the message is never enqueued. Nothing retries it, because
nothing knows it was owed: there is no scheduler (`FR-ADR-005`) and no reconciler.

The reverse order is worse. Sending inside the transaction means a rolled-back booking has already
enqueued a receipt for a booking that does not exist.

## Decision

**A transactional outbox.**

**An `outbox_message` table**: `id`, `created_at`, `topic`, `payload` (`jsonb`), `status`
(`pending` / `sent`), `sent_at`, `attempts`, `last_error`.

**The row is inserted inside the booking transaction**, at step 9 of `FR-ADR-029`, immediately before
commit. It commits with the booking or it does not exist. There is no window.

**A relay sends it.** Immediately after commit, the same request attempts the queue send and marks the
row `sent`. That is the fast path and it is what happens almost always.

**If that send fails, or the process dies before it, the row stays `pending`** — and this is where
this project's constraints bite. There is no scheduler to sweep it. The relay therefore also runs
**in the worker's receive loop**: before each poll of the queue, the worker checks for `pending`
outbox rows older than a short threshold and sends them. The worker is already a long-running
process (`FR-ADR-005`), so this needs no new process and no schedule — it is work done on an existing
loop, not a timer.

**The relay's claim is `SELECT ... FOR UPDATE SKIP LOCKED`**, so a second worker instance never picks
up the same row.

**Sending twice is safe and expected.** A crash between the queue send and the `sent` update
re-sends the message. SQS is at-least-once anyway, so the worker must already suppress duplicates —
`FR-ADR-032` carries that, and it is the reason at-least-once here costs nothing extra.

## Alternatives rejected

**Post-commit send with no outbox.** Rejected on the window above. It is the common implementation and
it is defensible when the message is a notification. It is not defensible when the message *is* the
ticket.

**Send inside the transaction.** Rejected. A rolled-back booking sends a receipt for a booking that
does not exist, which is worse than a missing one.

**An outbox with a scheduled relay process.** Rejected under `FR-ADR-005` — nothing runs on a schedule
and there is no fourth process to run one in. Folding the relay into the worker's existing loop is
what makes an outbox possible inside this project's constraints, and it is the reason the pattern is
affordable here at all.

**Skip the outbox and let the customer resend from their bookings page.** Rejected as the only
recovery. It requires the customer to notice, and `OPEN-EMAILFAIL-01` is still open on what they are
told. A resend affordance may exist as well, and it is not a substitute for the message being durable.

**Use the booking row itself as the outbox — query for bookings with no `receipt_sent_at`.** Rejected.
It works for this one message type and breaks the moment a second kind of job exists, and it puts job
state on a customer-facing record.

## Source

`SRC-002 §8.5.1` as corrected by `§E E-5` (push to the queue; the worker sends the receipt) ·
`SRC-003 OPEN-EMAIL-01` (the receipt is load-bearing) · `OPEN-TICKET-01` (the reference gets them in)
· `SRC-002 §7.3` (stateless containers, so nothing can be held in memory across a restart) ·
`§8.5.2` (retries and a dead letter path).

The outbox and the worker-loop relay are the build session's under Art III.9.

## Consequences

The booking transaction gains one insert. The outbox table only grows, under `FR-ADR-012`; it is small
— one row per booking — and `sent` rows are kept as the record that the receipt was dispatched.

**If the worker is down, receipts are delayed but not lost.** They are sitting in the outbox and go out
when it comes back. Under a post-commit send they would have been lost.

The relay in the worker loop is one more thing the worker does, and it must not starve the queue poll.
It runs before each poll with a bounded batch size.

**This does not solve `OPEN-EMAILFAIL-01`.** The outbox guarantees the job is *attempted*. What happens
when SES itself refuses after payment is captured is unruled and reserved — `FR-ADR-049`.

The worker's shutdown behaviour has to account for the relay as well as the queue poll
(`FR-ADR-033`).
