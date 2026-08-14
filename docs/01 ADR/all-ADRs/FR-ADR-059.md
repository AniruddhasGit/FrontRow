# One queue interface: SQS in AWS, ElasticMQ locally, and no task-queue library over either

```
ADR id ............ FR-ADR-059
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-QUEUE-01; SRC-002 §4.5; SRC-002 §5.4.1; SRC-002 §8.5.1; SRC-002 §8.5.2; SRC-002 §6.1.7; SRC-002 §13.1
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §4.5` requires "a separate worker process consuming AWS SQS". `SRC-002 §5.4.1` says "Prefer
`RQ` or `Dramatiq` over Celery" — and both of those are Redis-brokered task queues, not SQS
consumers.

**Those are two different architectures**, and under Art II.2 the build session may not pick between
two clauses of the client's own mandate. It was raised as `OPEN-QUEUE-01`, together with the second
question the clause leaves open: what stands in for SQS in local development, which is a new
dependency and `§13.1` requires asking.

The client answered: "yes allowed to have ELASTICmq."

That settles the broker. The sweep found that it does not settle the library — `§5.4.1`'s preference
is still sitting there unaddressed, and a future session reading it will reasonably wire up Dramatiq.

## Decision

**AWS SQS in AWS. ElasticMQ in `docker-compose.yml` for local development only, never deployed.**

**One queue interface in the application code.** A small port with `send`, `receive`, `delete` and
`extend_visibility`. **The worker does not know which implementation is behind it**, and neither does
the code that enqueues.

ElasticMQ speaks the SQS wire protocol, so both implementations are the same client pointed at a
different endpoint URL. The interface exists so that is a configuration change (`QUEUE_URL`) and not a
branch in the code.

**No task-queue library. Not RQ, not Dramatiq, not Celery.**

`§5.4.1`'s preference is read as guidance about **which library to choose if a Redis-brokered task
queue were used** — it sits in a section about memory footprint, and its point is that Celery is heavy.
`§4.5` states the architecture, and `OPEN-QUEUE-01` confirmed SQS. **RQ and Dramatiq cannot consume
SQS**, so adopting either would mean either a second broker or abandoning `§4.5`.

Using neither also satisfies `§5.4.1`'s actual concern — footprint — better than either would. And
under `§13.1` a task-queue library is a dependency that is not obviously necessary when the interface
is four operations against a client the AWS SDK already provides.

**This reading is recorded rather than left implicit, because the clause is still in a frozen source
and no erratum touches it.** Anyone reading `§5.4.1` alone will reach a different conclusion.

**A standard queue, not FIFO** — decided in `FR-ADR-032`, where duplicate suppression is a claim row
rather than a queue feature.

**A dead letter queue exists** (`§8.5.2`). `maxReceiveCount`, the visibility timeout and the message
retention period are **Zone C values the client sets**. The application does not configure them and
`docs/30 Deployment/` owes a specification saying what the application expects of each and what
breaks at the wrong value — in particular that the visibility timeout must exceed the worst-case SES
call plus the worker's processing time, or the message is redelivered while the first attempt is still
running.

**Long polling**, with a wait time of 20 seconds. Short polling against a mostly-empty queue burns the
1M-request free-tier allowance on empty receives; long polling makes an idle worker cost roughly three
requests a minute. *(reasoned, not observed.)*

**The message payload is minimal**: `booking_id`, `request_id` (`FR-ADR-056`), and a
`message_version` integer. The worker reads the booking from PostgreSQL. **No customer data travels in
the queue** — no email address, no seat list, no price — because a queue message is a copy that goes
stale and a place customer data would sit outside the database.

**`message_version` exists from the first message.** Adding a version field to a payload after
messages are in flight means the first consumer to see an unversioned message has to guess.

## Alternatives rejected

**Dramatiq or RQ with a Redis broker.** Rejected above: contradicts `§4.5` and `OPEN-QUEUE-01`, and
would put durable job state in the one component this project treats as losable (`FR-ADR-028`).

**Celery.** Rejected by `§5.4.1` explicitly.

**Use SQS directly with no interface.** Rejected. The interface is what makes ElasticMQ a URL change
rather than a code branch, and `OPEN-QUEUE-01`'s filing says the worker targets one interface and does
not know which is behind it.

**LocalStack instead of ElasticMQ locally.** Rejected. The client granted ElasticMQ specifically, and
LocalStack is a much larger container for one service.

**Skip the local queue and call the worker function directly in development.** Rejected. It removes
the asynchrony from local development, so the at-least-once behaviour, the visibility timeout and the
dead letter path are never exercised until they are exercised in AWS.

**Put the booking details in the message so the worker need not query.** Rejected above.

## Source

`SRC-003 OPEN-QUEUE-01` ("yes allowed to have ELASTICmq"; one interface, DLQ, local only) ·
`SRC-002 §4.5` (a worker consuming SQS) · `§5.4.1` (the RQ/Dramatiq preference, read as scoped) ·
`§8.5.1` (push a message after confirmation) · `§8.5.2` (retries and a DLQ) ·
`§6.1.7` (`docker-compose.yml` is local only) · `§13.1` (ask before adding a dependency).

The no-library reading, long polling and the payload shape are the build session's under Art III.9.

## Consequences

The worker is a plain loop: receive, handle, delete, with the outbox relay on the same loop
(`FR-ADR-031`). That is more code than a decorator over a task function and it is code the client can
read, which `§1.3` values.

**Nothing watches the dead letter queue.** A receipt that fails repeatedly lands there invisibly. That
is recorded in `FR-ADR-032` and `FR-ADR-068` as an accepted weakness with a named mitigation the
client could choose.

The SQS queue, its DLQ and the redrive policy are AWS resources the client creates. They belong in
`docs/30 Deployment/AWS_PREP_QUEUE.md` with a *needed by* stage of Phase 5, announced now under
Art VIII.4.

**The task role needs `sqs:SendMessage`, `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`
and `GetQueueAttributes`** on the queue — the last for the queue-depth metric (`FR-ADR-057`). That is
part of the IAM specification owed under `§6.4.2`.
