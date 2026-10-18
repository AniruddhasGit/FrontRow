# P1 · The one alarm: no api task running  (prep-queue row 13 · needed by Phase 1)

> Zone C specification (`SRC-002 §6.3.6`). What to build, not how. Every claim about AWS behaviour is
> **reasoned, not observed**. Ruled by `SRC-003 OPEN-OPS-01`.

## 1. What you need to build

- **One CloudWatch alarm** that fires when the api has no running, healthy task. Without it, the honest
  answer to "how does anyone learn the site is down" is *nobody, until a customer complains*.
- **An SNS topic and an email subscription.** **The destination address is not written in this
  repository** (`FR-ADR-071`). Enter it directly into the subscription, and confirm the subscription
  email when it arrives.

## 2. What the application expects

- Nothing from the alarm itself. The application does not read or publish any metric in Phase 1
  (`/metrics` arrives in Phase 7).
- **Pick a metric that exists without a paid feature, and check that it is really published.** Two
  candidates, both to be confirmed in your account before you rely on them:
  - a running-task count for the api service. This may require Container Insights, which is billed
    (reasoned, not observed).
  - the api target group's **healthy host count** from the load balancer, which comes with the load
    balancer. Note that it also drops to 0 when RDS or Redis is down, because `/health/ready` is the
    check. That is arguably the right signal, since the site is down either way.
- **Missing data must count as breaching.** If nothing is running, nothing reports. An alarm that
  treats missing data as fine stays green through the outage it exists to catch.

## 3. Acceptance criteria

1. The alarm exists, on a metric you have seen with real data points in the console.
2. Its action publishes to the SNS topic, and the topic has one **confirmed** email subscription.
3. Missing data is treated as breaching.
4. **It has been watched failing once**: set the api service's desired count to 0 (or stop its task).
   The alarm goes to `ALARM`, the email arrives, and the alarm returns to `OK` when the service is
   restored. Write the time it took into the prep queue. An alarm nobody has seen fire is decoration.

## 4. Common mistakes

- **An unconfirmed subscription.** The alarm fires and nobody receives anything. SNS shows
  "pending confirmation".
- **Missing data treated as "not breaching"** (reasoned, not observed: this is the default). A stopped
  service publishes no data points, so the alarm stays `OK`.
- **An alarm on CPU or memory instead.** Both look normal right up to the moment the task is gone,
  and then they have no data at all.
