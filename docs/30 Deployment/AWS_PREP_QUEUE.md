# AWS prep queue — what the client must create, and when it is needed

> **This file is the BUILD → OPS handshake** (`COORDINATION.md`). The build session writes the
> requests. The client (OPS lane) creates the thing by hand and records **what actually exists** —
> endpoint, version, role name, region, ARN.
>
> **The build session creates nothing in AWS** (`CONSTITUTION.md` Art VIII.1). As of 2026-08-14 it
> holds read-only credentials and may `describe` / `list` / `get` to check what was built against
> the specification. **No create, no modify, no delete until the client says otherwise in writing.**
>
> **Every row here was also said in chat**, early enough to prepare while code was still being
> written (Art VIII.4). A row that appears here without having been announced is the
> "I reported an action I did not perform" breach the consistency check exists to catch.
>
> **A row is not done because it is on this list.** It is done when the client says what exists.

## How to read a row

| Field | Meaning |
|---|---|
| **Needed by** | the phase of `SRC-002 §12` that blocks without it. Not a date. |
| **Status** | `REQUESTED` · `IN PROGRESS` · `EXISTS` · `DECLINED` · `BLOCKED` |
| **What exists** | filled in by OPS, in concrete terms. "Created" is not an answer; an endpoint is. |
| **Spec** | the Zone C specification in this folder that says what to build and how to know it is right |

---

## Queue

| # | Item | Needed by | Status | What exists | Spec |
|---|---|---|---|---|---|
| 1 | **TMDB developer API key** — not AWS, but the same handshake. Free for non-commercial use, requires attribution in the footer (`SRC-002 §10.2`). Read from an environment variable, never committed (`§10.5`). | Phase 6 · **request it now**, approval is not instant | `REQUESTED` | — | — |
| 2 | **ECR repository** — one per image. Free tier holds **500 MB total**, so the image budget is real, not advisory (`SRC-002 §5.4.2`). | Phase 1 | `REQUESTED` | — | *(to be written by `GOAL_14`)* |
| 3 | **EC2 `t3.micro` + ECS cluster on it** — 1 GB RAM total, shared with the OS, the Docker daemon and the ECS agent (`§5.2.1`). | Phase 1 | `REQUESTED` | — | *(to be written by `GOAL_14`)* |
| 4 | **Application Load Balancer + target group + listener** — the health check path matters: it must call `/health/ready`, **not** `/health/live` (`§7.4`). Wiring it to the wrong one turns a recoverable dependency blip into a restart loop. | Phase 1 | `REQUESTED` | — | *(to be written by `GOAL_14`)* |
| 5 | **VPC with a public subnet, and security groups** — there is **no NAT Gateway** (`§5.3`), so the application runs in a public subnet behind strict security groups (`§5.4.4`). Outbound egress is needed for TMDB, S3, SQS and SSM. | Phase 1 | `REQUESTED` | — | *(to be written by `GOAL_14`)* |
| 6 | **RDS PostgreSQL `db.t3.micro`, 20 GB** — plus a **restricted runtime role that does not own the tables**. Local Postgres gives you superuser; RDS never will, so building against the restricted role from day one is the point (`GOTCHAS.md`). | Phase 2 | `REQUESTED` | — | — |
| 7 | **SSM Parameter Store paths** for every secret. **Not Secrets Manager** (`§5.4.3`) — it is on the forbidden list. | Phase 1 | `REQUESTED` | — | — |
| 8 | **CloudWatch Logs group + the `awslogs` driver on the task definition** — with the default driver, container stdout dies with the container, so the record of a crash loop is destroyed by the restart that caused it. `§5.4.5` requires JSON to stdout; **something has to collect it.** Retention is a cost decision and therefore the client's. | Phase 1 | `REQUESTED` | — | — |
| 9 | **ElastiCache Redis `cache.t3.micro`** — one node, no replica, no failover. Art IV.6 makes a Redis outage a visible partial outage by design. | Phase 4 | `REQUESTED` | — | — |
| 10 | **S3 bucket for movie posters** — we download once and serve our own URLs; we never hotlink (`§10.6.3`). Needs a lifecycle answer for orphaned objects. | Phase 6 | `REQUESTED` | — | — |
| 11 | **SQS queue + a dead letter queue** — `§8.5.2` requires the DLQ path to exist and failures to be visible, not just retried. | Phase 5 | `REQUESTED` | — | — |
| 12 | **EventBridge rule for the daily TMDB sync** — `§10.6.1` requires three trigger routes (CLI, an admin-token HTTP endpoint, and a schedule) so the client can compare EventBridge against a cron container. | Phase 6 | `REQUESTED` | — | — |
| 13 | **An IAM task role** with exactly the permissions the application needs: S3 `PutObject`/`GetObject` on one prefix, SQS send and receive on the two queues, SSM `GetParameters` on one path, and nothing else. | Phase 1, extended per phase | `REQUESTED` | — | — |
| 14 | **A TLS certificate (ACM) on the ALB** — blocked on `OPEN-TLS-01`. Until it is ruled, the session cookie's `Secure` flag has no ruled value and Art VIII.14 keeps this environment un-named as production. ACM is free for ALB use and is not on the forbidden list. | Phase 1 | `BLOCKED` — needs a ruling | — | — |

---

## Standing notes

**Public IPv4 now costs money.** With no NAT Gateway the EC2 instance needs a public address, which
is billed hourly. Free tier covers 750 hours a month for the first 12 months, so **one** instance is
covered and a second is not. *(reasoned, not observed)*

**One instance and a fixed host port means two tasks cannot run at once**, so ECS's default
deployment configuration waits forever for a healthy new task that can never start. Minimum-healthy
at 0, and accept a hard downtime window on every deploy. *(reasoned, not observed)*

**Destructive AWS actions are always human.** No session, in either lane, deletes a database, drops
a bucket, or rotates a credential.
