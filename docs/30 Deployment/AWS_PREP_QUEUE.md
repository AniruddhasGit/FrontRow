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

> **Revised 2026-08-14 by `SRC-003`.** Two rows were **deleted, not marked done**: the TMDB API key
> and the EventBridge rule. `SRC-002 §10` is withdrawn in full — there is no movie import, and with
> it gone **nothing in this system runs on a schedule.** One row was **added**: Amazon SES, which
> the client approved into the service list. The row numbers below were reallocated; do not cite a
> row by number from an earlier commit.

| # | Item | Needed by | Status | What exists | Spec |
|---|---|---|---|---|---|
| 1 | **ECR repository** — one per image. Free tier holds **500 MB total**, so the image budget is real, not advisory (`SRC-002 §5.4.2`). | Phase 1 | `REQUESTED` | — | *(owed by `GOAL_14`)* |
| 2 | **EC2 `t3.micro` + ECS cluster on it** — 1 GB RAM total, shared with the OS, the Docker daemon and the ECS agent (`§5.2.1`). Three containers now, not four (`SRC-003 OPEN-PROC-01`). | Phase 1 | `REQUESTED` | — | *(owed by `GOAL_14`)* |
| 3 | **Application Load Balancer + target group + listener** — the health check path matters: it must call `/health/ready`, **not** `/health/live` (`§7.4`). Wiring it to the wrong one turns a recoverable dependency blip into a restart loop. | Phase 1 | `REQUESTED` | — | *(owed by `GOAL_14`)* |
| 4 | **VPC with a public subnet, and security groups** — there is **no NAT Gateway** (`§5.3`), so the application runs in a public subnet behind strict security groups (`§5.4.4`). Outbound egress is needed for **S3, SQS, SES and SSM**. TMDB is no longer among them. | Phase 1 | `REQUESTED` | — | *(owed by `GOAL_14`)* |
| 5 | **RDS PostgreSQL `db.t3.micro`, 20 GB** — plus a **restricted runtime role that does not own the tables**. Local Postgres gives you superuser; RDS never will, so building against the restricted role from day one is the point (`GOTCHAS.md`). **Nothing is ever deleted** (`SRC-003 OPEN-OPS-02`), so watch the 20 GB. | Phase 2 | `REQUESTED` | — | — |
| 6 | **SSM Parameter Store paths** for every secret. **Not Secrets Manager** (`§5.4.3`) — it is on the forbidden list. | Phase 1 | `REQUESTED` | — | — |
| 7 | **CloudWatch Logs group + the `awslogs` driver on the task definition** — with the default driver, container stdout dies with the container, so the record of a crash loop is destroyed by the restart that caused it. `§5.4.5` requires JSON to stdout; **something has to collect it.** Retention is a cost decision and therefore yours. | Phase 1 | `REQUESTED` | — | — |
| 8 | **ElastiCache Redis `cache.t3.micro`** — one node, no replica, no failover. Art IV.6 makes a Redis outage a visible partial outage **by design**, not a bug to paper over. | Phase 3 | `REQUESTED` | — | — |
| 9 | **SQS queue + a dead letter queue** — `§8.5.2` requires the DLQ path to exist and failures to be visible, not just retried. Locally this is **ElasticMQ** in `docker-compose.yml`, approved by `SRC-003 OPEN-QUEUE-01`; ElasticMQ is never deployed. **Two orderings the application depends on, published by `P-TKT-05`:** the queue's **visibility timeout must be LESS THAN `RECEIPT_CLAIM_STALE_SECONDS`**, and **`maxReceiveCount` must be GREATER THAN `ceil(stale / visibility)`** — 8 at the worked pair. Get either backwards and a receipt is either retried while the first attempt is still running, or dead-lettered before the worker has had its allowed attempts. **The customer's only proof of purchase is what is in that message.** | Phase 5 | `REQUESTED` | — | — |
| 10 | **Amazon SES** — **added to the approved service list by `SRC-003 OPEN-EMAIL-01`.** Starts sandboxed: you can only send to addresses you have verified, and leaving the sandbox is a support request that takes a day or two. **Request it early.** | Phase 5 · **request now** | `REQUESTED` | — | — |
| 11 | **S3 bucket for movie posters** — the **admin uploads** them and we serve our own URLs (`§10.6.3` survives in effect even though the rest of `§10` is withdrawn). Needs a lifecycle answer for objects uploaded and never attached to a movie. | Phase 6 | `REQUESTED` | — | — |
| 12 | **An IAM task role** with exactly the permissions the application needs and nothing else: S3 `PutObject`/`GetObject` on one prefix, SQS send and receive on the two queues, SES `SendEmail` from one verified identity, SSM `GetParameters` on one path. | Phase 1, extended per phase | `REQUESTED` | — | — |
| 13 | **CloudWatch alarm on running-task-count < 1, plus an SNS topic and an email subscription.** Ruled by `SRC-003 OPEN-OPS-01`. **The destination address is deliberately not written in this repository** — you enter it directly into the SNS subscription. (Originally because the repository was public; it went private on 2026-08-14 and the omission stands anyway — `FR-ADR-071`.) Without this row the honest answer to "how does anyone learn the site is down" is *nobody, until a customer complains.* | Phase 1 | `REQUESTED` | — | — |
| 14 | **A TLS certificate (ACM) on the ALB** — blocked on `OPEN-TLS-01`, which is `DEFERRED`: you are sourcing a domain. Until it exists the session cookie's `Secure` flag stays off in the deployed environment and Art VIII.14 keeps that environment un-named as production. ACM is free for ALB use and is not on the forbidden list; the domain is the only real cost. | Phase 1 | `BLOCKED` — awaiting a domain | — | — |
| 15 | **An IAM *execution* role, distinct from the task role in row 12.** ECS uses two roles and confusing them is the single most common Phase 1 failure. The **execution** role is used by the ECS agent *before your container starts* — pulling from ECR, writing to CloudWatch Logs, and **reading SSM parameters injected as `secrets` in the task definition**. `ssm:GetParameters` on the **task** role does nothing for injected secrets, because the container is not running yet when they are read. Symptom when wrong: the task dies at `PENDING` with a `ResourceInitializationError` and no application log line ever appears, because logging is on the same role. | Phase 1 | `REQUESTED` | — | — |
| 16 | **The ALB's subnet CIDR ranges, written down and given to the application.** `SRC-002 §8.4.1` requires the rate limiter to key on **per-user AND per-IP**. Behind an ALB the peer address is the ALB, so without the trusted-proxy CIDRs every customer on earth shares one bucket and the limiter appears to work while protecting nothing (`GOTCHAS.md`). This is a value the client must supply, not something the application can discover. | Phase 7 | `REQUESTED` | — | — |
| 17 | **RDS automated backups, at the free-tier maximum retention, and one rehearsed restore.** Ruled by `FR-ADR-070`. `SRC-003 OPEN-OPS-02` says nothing is ever deleted — that is a *retention* guarantee and it is not a *recovery* guarantee; they are different promises and only backups deliver the second. **A restore that has never been rehearsed is not a recovery.** Note that a point-in-time restore produces a **new instance with a new endpoint**, so it changes `DATABASE_URL` and needs a redeploy. | Phase 2 | `REQUESTED` | — | — |
| 18 | **ECS service deployment configuration: minimum-healthy-percent `0`, maximum-percent `100`.** With one `t3.micro` and a fixed host port, two tasks cannot run at once — so the default deployment configuration waits forever for a healthy new task that can never start, and the deploy hangs rather than failing. Setting minimum-healthy to 0 accepts **a hard downtime window on every deploy**, which is the real trade and should be a deliberate choice rather than a surprise. *(reasoned, not observed)* | Phase 1 | `REQUESTED` | — | — |
| 19 | **A one-off seed task, and the secret it needs.** `P-XCT-30`'s seed is the only artefact that writes to every table without going through an endpoint, and **no seeded account can sign in without it**: `SEED_DEFAULT_PASSWORD` is seed-only by `S7.9`, so it **cannot ride in on the API task definition's SSM secrets**. Needed: its own task definition family, entrypoint `seed`, the parameter as an SSM `SecureString` scoped to that family alone, and the **execution** role granted `ssm:GetParameters` on it — the execution role, not the task role (see row 15). | Phase 2 | `REQUESTED` | — | *(owed by `GOAL_14`)* |

### Deleted rows — recorded, not silently dropped

| Was | Item | Why it is gone |
|---|---|---|
| 1 | TMDB developer API key | `SRC-002 §10` withdrawn in full. No external movie API. *(`SRC-003 OPEN-TMDB-01`)* |
| 12 | EventBridge rule for the daily sync | There is no sync, and nothing else in the system runs on a schedule. *(`SRC-003 OPEN-PROC-01`, `OPEN-TMDB-01`)* |

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
