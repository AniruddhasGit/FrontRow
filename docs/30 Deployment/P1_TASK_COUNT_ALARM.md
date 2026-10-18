# P1 · The one alarm: no api task running  (prep-queue row 13 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.6`). What to build, not how. Every claim about AWS behaviour is
> **reasoned, not observed**. Ruled by `SRC-003 OPEN-OPS-01`. The build session creates none of the
> alarm, the topic or the subscription.

## What to build

- **One CloudWatch alarm** that fires when the api has no running, healthy task: running-task-count < 1.
  Without it, the honest answer to "how does anyone learn the site is down" is *nobody, until a
  customer complains*.
- **An SNS topic and an email subscription.** **The destination address is not written in this
  repository** (`FR-ADR-071`). Enter it directly into the subscription, and confirm the subscription
  email when it arrives.
- **Missing data treated as breaching:** `TreatMissingData: breaching`. A stopped service publishes no
  data points at all. With any other treatment the alarm sits in `INSUFFICIENT_DATA` or `OK` through
  exactly the outage it exists to catch, and nobody is told.

## What the application expects

- Nothing from the alarm itself. The application does not read or publish any metric in Phase 1
  (`/metrics` arrives in Phase 7).
- **Pick a metric that exists without a paid feature, and check that it is really published.** Two
  candidates, both to be confirmed in your account before you rely on them:
  - a running-task count for the api service. This may require Container Insights, which is billed
    (reasoned, not observed).
  - the api target group's **healthy host count** from the load balancer, which comes with the load
    balancer. Note that it also drops to 0 when RDS or Redis is down, because `/health/ready` is the
    check. That is arguably the right signal, since the site is down either way.

## Acceptance criteria

Acceptance criterion: stop the service, receive an email.

1. The alarm exists, on a metric you have seen with real data points in the console.
2. Its action publishes to the SNS topic, and the topic has one **confirmed** email subscription.
3. Missing data is treated as breaching (`TreatMissingData: breaching`), so the alarm never rests in
   `INSUFFICIENT_DATA` while nothing runs.
4. **It has been watched failing once**: set the api service's desired count to 0 (or stop its task).
   The alarm goes to `ALARM`, the email arrives, and the alarm returns to `OK` when the service is
   restored. Write the time it took into the prep queue. An alarm nobody has seen fire is decoration.

## Common mistakes

- **An unconfirmed subscription.** The alarm fires and nobody receives anything. SNS shows
  "pending confirmation".
- **Missing data left at its default treatment** (reasoned, not observed: the default is "missing"). A
  stopped service publishes no data points, so the alarm shows `INSUFFICIENT_DATA` and sends nothing.
- **An alarm on CPU or memory instead.** Both look normal right up to the moment the task is gone,
  and then they have no data at all.

## Not watched, and deliberately so

One alarm is the ruling (`SRC-003 OPEN-OPS-01`). Everything below can fail without anyone being told,
and that is a recorded choice rather than an oversight (PRD `P-XCT-14`, S7.14):

- dead-letter queue depth: a receipt that failed every retry sits in the DLQ and nobody is told. The
  customer has paid and holds no proof of purchase except what the booking screen showed.
- the worker process: it can die while the api stays healthy; receipts stop and requests do not.
- RDS storage: nothing is ever deleted (`SRC-003 OPEN-OPS-02`), so the 20 GB fills slowly and silently.
- the S3 poster bucket: an upload failure shows only to the admin who attempted it.
- SES sending reputation and the sandbox: bounces or a suspension stop every receipt.
- memory headroom on the `t3.micro`: the first sign is a container killed by the kernel.

Recommended, not adopted: an alarm on dead-letter queue depth.
