# One alarm, on running task count, and an honest list of what nobody is watching

```
ADR id ............ FR-ADR-068
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-OPS-01; SRC-003 OPEN-NAME-01; SRC-002 §5.2.6; SRC-002 §6.3.6; SRC-002 §6.4.2; SRC-001 §8.2; SRC-003 OPEN-EMAILFAIL-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §10.28` asked who receives alerts if the system goes down. The build session's own note when
raising it as `OPEN-OPS-01` was that with no alerting configured the honest answer is "nobody", and
that this belongs written down as an accepted risk rather than left as an unnoticed hole.

The client answered "yes follow recommendation" and supplied a personal email address.

That closes the question of who. It does not close the question of what is watched, and the answer to
that is: **one thing.** This record exists to say so plainly rather than let a single alarm imply
monitoring.

## Decision

**One alarm: CloudWatch on the ECS service's running task count below 1, delivering through SNS to the
client's personal email address.**

**The address is never committed.** It lives in the SNS subscription the client creates and in local
`.env`. `SRC-003` redacts it for the same reason, and **this repository is public** (Art III.6).
Nothing downstream needs the literal string.

**The alarm, the SNS topic and the subscription are Zone C** (`§6.3.6`). The client builds all three.
What is owed is the specification (`§6.4.2`): the metric, the threshold, the evaluation period, the
treatment of missing data, and the acceptance criterion — stop the service, receive an email.

**One thing the specification must state, because it is the mistake that makes this alarm useless:**
set missing data to `breaching`. If the ECS service is deleted or the metric stops being published,
the default treatment leaves the alarm in `INSUFFICIENT_DATA` and it never fires. An alarm that stays
quiet when the thing it watches disappears is worse than no alarm, because it is believed.
*(reasoned, not observed.)*

### What nobody is watching — stated, not implied

**None of the following is alarmed.** Each is a real failure this system can have and nobody will be
told:

| Not watched | What it would catch |
|---|---|
| **Dead letter queue depth** | **a customer paid and their receipt never sent** (`FR-ADR-049`) |
| 5xx rate at the ALB | the application failing while its task is still running |
| Target group unhealthy hosts | readiness failing on Postgres or Redis (`FR-ADR-055`) |
| RDS free storage | forever retention filling 20 GB (`FR-ADR-012`) |
| RDS connection count | pool exhaustion against roughly 110 connections |
| Host memory | a container being killed for exceeding its limit (`FR-ADR-064`) |
| SES bounce and complaint rate | receipts going nowhere (`FR-ADR-060`) |
| `outbox_pending` rising | the relay stuck, receipts not enqueued (`FR-ADR-031`) |

**The first is the worst.** The product's central promise is that a customer receives a receipt that
gets them into a hall. When that fails repeatedly the message lands in the dead letter queue, and
today nothing looks there. **A dead letter queue alarm is the single most valuable thing the client
could add**, and it is offered as a recommendation, not adopted as a decision — `OPEN-OPS-01` ruled one
alarm and adding more is the client's call, not a stricter version of theirs.

**Nothing is added unasked.** `§6.3.6` puts alarms in Zone C and Art VII.6 says scope as written.
Building six alarms the client did not ask for would be writing Zone C and inventing scope in one
move.

**There is one operator and no backup decider** (`OPEN-NAME-01`: "Aniruddha Jathar is my name and i
will always be the one building", with no backup, stated affirmatively). **There is no escalation path
and no on-call rotation, and there cannot be.** If the alert email is not read, nothing else happens.
That is a property of the project and it belongs in the runbook.

**`/metrics` exists and nothing scrapes it** (`FR-ADR-057`). It is not an alerting mechanism and must
not be counted as one.

## Alternatives rejected

**Build the recommended alarms anyway because they are obviously useful.** Rejected on `§6.3.6` and
Art VII.6. They are recommended in writing instead, which is the form `§6.4` asks for.

**Alarm on the application publishing a custom heartbeat metric.** Rejected. CloudWatch custom metrics
are charged per metric per month, and running-task-count is published free by ECS.

**Use `/metrics` for alerting.** Rejected. Nothing scrapes it.

**Commit the alert address so the alarm specification is complete.** Rejected outright under
Art III.6. This repository is public and the address identifies a person.

**Treat one alarm as monitoring and move on.** Rejected. That is the implication this record exists to
prevent.

## Source

`SRC-003 OPEN-OPS-01` (the ruling and the redaction) · `OPEN-NAME-01` (one person, no backup) ·
`SRC-002 §5.2.6` (CloudWatch basic metrics) · `§6.3.6` (alarms are Zone C) ·
`§6.4.2` (the specification is owed) · `SRC-001 §8.2` (observable and recoverable by one person) ·
`SRC-003 OPEN-EMAILFAIL-01` (the failure the DLQ alarm would catch).

The unwatched list and the DLQ recommendation are the build session's under Art III.9.

## Consequences

**A running but broken application is invisible.** The task count alarm fires when nothing is running.
It does not fire when everything is running and every request returns 500.

The unwatched list belongs in the runbook (`§12.8`) as the things to check by hand during an incident,
since nothing will announce them.

The SNS topic, the subscription and the alarm are prep-queue items with a *needed by* stage of
Phase 1, announced now under Art VIII.4 — the client should have working alerting before the first
deployment, not after.

**A dead letter queue alarm is recommended in `docs/30 Deployment/` alongside the ruled one**, marked
clearly as a recommendation the client may decline. It pairs with `OPEN-EMAILFAIL-01`, which is still
open, and answering that row without adding this alarm would leave the ruled behaviour untriggerable.
