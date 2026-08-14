# The worker suppresses duplicate receipts with a claim row, not with queue semantics

```
ADR id ............ FR-ADR-032
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §8.5.1; SRC-002 §8.5.2; SRC-002 §E E-5; SRC-003 OPEN-QUEUE-01; SRC-003 OPEN-EMAIL-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

SQS standard queues deliver at least once. So does the outbox relay in `FR-ADR-031`, which re-sends a
message if the process dies between the queue send and the `sent` update. Two mechanisms, both
at-least-once, feeding one job that sends an email to a customer.

`SRC-002 §8.5.2` requires retries and a dead letter path. Retries are also duplicate deliveries by
another name.

A duplicated receipt is not a correctness failure in the way a double booking is, but it is a
customer-visible defect and it damages the one artefact that gets a person into the hall — a customer
holding two receipts does not know which is real.

## Decision

**A `receipt_dispatch` claim row, unique on `booking_id`.**

Before sending, the worker inserts a row `(booking_id, claimed_at, status='sending')`. The insert
either succeeds — this delivery owns the send — or it violates the unique constraint, in which case
another delivery already has it and this one deletes its queue message and stops.

**The claim is the guard, not the queue's configuration.** That is the point of this record: the
suppression must not depend on SQS's visibility timeout, on FIFO deduplication, or on the retry count
being right, because none of those are under the application's control and two of them are Zone C.

**On success** the row moves to `sent` with the SES message id. **On failure** it moves to `failed`
with the error, and the queue message is *not* deleted, so SQS redelivers it. On redelivery the worker
finds its own `failed` row for that booking and retries the send — a `failed` claim is retryable; a
`sending` or `sent` claim is not.

**A `sending` row older than the visibility timeout is treated as abandoned** and may be reclaimed.
Without that, a worker killed mid-send leaves a claim nobody can ever take, and the receipt never
goes out. The threshold is configuration, not a literal.

**The queue is a standard queue, not FIFO.**

- FIFO's deduplication window is five minutes, which is a *window* and not a guarantee for a message
  that could be redriven hours later from a dead letter queue.
- There is no ordering requirement between two customers' receipts.
- FIFO's throughput limits and message-group semantics are complexity this has no use for.
- ElasticMQ is the local stand-in (`SRC-003 OPEN-QUEUE-01`); keeping to standard-queue semantics keeps
  the local and deployed behaviour the same, which is the point of having one queue interface.

**The message payload carries the `booking_id` and a `message_version` integer, and nothing else about
the booking.** The worker reads the current booking from PostgreSQL. A payload carrying the seat list
and the price would go stale, and would put customer data in a queue.

## Alternatives rejected

**Rely on the SQS visibility timeout alone.** Rejected. It reduces duplicates; it does not prevent
them. It is also a Zone C value the client sets, so the application's correctness would depend on
infrastructure configuration the application cannot see.

**Use a FIFO queue with content-based deduplication.** Rejected above — a five-minute window is not a
guarantee, and a dead-letter redrive is exactly the case that exceeds it.

**A `receipt_sent_at` column on the booking row.** Rejected. It puts job state on a customer-facing
record, cannot express `sending` versus `failed` without adding more columns to `booking`, and gives
the retry logic nowhere to record an error.

**Suppress in Redis with a `SETNX` on the booking id.** Rejected. Redis is losable (`FR-ADR-028`), and
losing the suppression set means every unacknowledged message re-sends. The claim must be as durable
as the booking.

**Accept duplicate receipts as harmless.** Rejected. Two receipts for one booking, each carrying the
same reference, is a customer at a door with two pieces of paper and no way to tell which one the
system knows about.

## Source

`SRC-002 §8.5.1` as corrected by `§E E-5` (the worker sends the receipt) · `§8.5.2` (retries and a
dead letter path) · `SRC-003 OPEN-QUEUE-01` (SQS in AWS, ElasticMQ locally, one interface) ·
`OPEN-EMAIL-01` (the receipt is load-bearing).

The claim-row mechanism and the standard-queue choice are the build session's under Art III.9.

## Consequences

`receipt_dispatch` is the table an operator reads to answer "did this customer get their receipt", and
it holds the SES message id that makes the answer checkable. That is worth more than the column it
replaces.

The dead letter queue receives messages whose send failed repeatedly. **Nothing watches it.** No alarm
on non-empty DLQ is ruled — `SRC-003 OPEN-OPS-01` ruled exactly one alarm, on running task count — so
a receipt that ends up there is invisible until someone looks. That is a real gap and it is recorded
in `FR-ADR-068` as an accepted weakness rather than silently left.

`maxReceiveCount`, the visibility timeout and the message retention period are Zone C values. The
application does not set them, and `docs/30 Deployment/` owes the client a specification saying what
the application expects of each and what breaks at the wrong value.

Duplicate suppression needs a test that delivers the same message twice concurrently and asserts one
send. Delivering it twice sequentially passes against a check-then-act implementation.
