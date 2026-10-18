# 04 — Deployment topology and the memory arithmetic

> **compressed per SRC-004 R-1.** This file describes what the application **expects** of the
> infrastructure. It is not the infrastructure. Task definitions, services, the load balancer, security
> groups and the VPC are Zone C — the client builds them (`SRC-002 §6.5`, `FR-ADR-004`).
>
> **This session has never seen this application run in AWS, or anywhere.** Every sentence below
> about how AWS behaves carries an `[AWS-04-nn]` id and the label, and is reasoning. **The deployed
> environment is never called by the other name while it runs without TLS** (Art VIII.14,
> `OPEN-TLS-01`).

## Topology

```
                     internet  (HTTP only until OPEN-TLS-01 is ruled)
                         │
                ┌────────▼─────────┐
                │ ALB  listener :80 │──── path /api/*  ──► target group "api"      ──► host port → api :8000
                │                   │──── default      ──► target group "frontend" ──► host port → frontend :8080
                └───────────────────┘          (/metrics is never routed; /health/* need not be routed)
                         │
        ┌────────────────▼──────────────────────────────────────────┐
        │ one EC2 t3.micro · ECS agent · Docker                     │
        │   api       (service A, 1 task)   limit 200 MiB           │
        │   worker    (service B, 1 task)   limit 150 MiB  :8001 /metrics, not routed
        │   frontend  (service C, 1 task)   limit  15 MiB           │
        │   migrate | seed   one-off task, exits                    │
        └──────┬──────────────┬──────────────┬──────────────────────┘
               │              │              │  outbound only, from a public subnet (no NAT, FR-ADR-065)
        RDS PostgreSQL   ElastiCache Redis   SQS · SES · S3 · SSM · ECR · CloudWatch Logs
```

`[JUDGMENT CALL]` **three services, not one task with three containers.** `SRC-002 §7.2` requires the
API and the worker to be separate containers that scale independently; one task holding both would
restart both together on any change to either. The alternative (one task) halves the number of
things to configure and loses that property. Zone C — the client chooses; this is what the
application expects.

## Ports, health checks, and which endpoint goes where

| Process | Container port | Who calls what | Must be | If wired the wrong way round |
|---|---|---|---|---|
| api | `API_PORT` = 8000 | **load balancer target group health check → `GET /health/ready`** | 200 when PostgreSQL `SELECT 1` and Redis `PING` both succeed within their timeouts; 503 naming the failed dependency | pointing the load balancer at `/health/live` keeps routing to an instance that cannot reach its database |
| api | 8000 | **container-level health check (if one is configured) → `GET /health/live`** | 200 whenever the process can serve HTTP; touches nothing | pointing a restart trigger at `/health/ready` turns every Redis or RDS blip into a restart loop |
| worker | `WORKER_METRICS_PORT` = 8001 | nothing routes to it | `/metrics` only; reachable from the host | routing it publicly discloses internal route names and volumes (`P-XCT-13`) |
| frontend | 8080 `[JUDGMENT CALL]` | frontend target group health check → any static file, e.g. `/` | 200 | — |

**`/health/ready` is cached for `READINESS_CACHE_TTL_SECONDS` (3)** so polling does not run a query per
poll. **SQS, SES and S3 are deliberately not probed** (`FR-ADR-055`): the api can serve almost
everything without them.

- [AWS-04-01] With one api task, a Redis or RDS outage turns `/health/ready` to 503, the load balancer marks the only target unhealthy, and requests to `/api/*` then fail at the load balancer even though browsing could have been served from PostgreSQL alone — `FR-ADR-028` accepts this on purpose. *(reasoned, not observed)*

## What the application expects of the infrastructure (the specification, not the answer)

These are requirements with their failure modes. The resources are in `docs/30 Deployment/AWS_PREP_QUEUE.md`.

1. **Same origin for the browser and the API.** The frontend calls relative `/api/...` with the cookie;
   the load balancer must send `/api/*` to the api and everything else to the frontend.
   - [AWS-04-02] A load balancer listener can route by path pattern to different target groups, which is what makes one hostname serve both containers without CORS. *(reasoned, not observed)*
2. **The real client IP.** The api trusts `X-Forwarded-For` from exactly the addresses in
   `FORWARDED_ALLOW_IPS` (the load balancer's subnet ranges, prep-queue row 16). A wildcard makes the
   rate limiter protect nothing while appearing to work.
   - [AWS-04-03] The load balancer appends the connecting client's address to `X-Forwarded-For`, so the right-most entry added by a trusted hop is the real client and anything to its left can be forged. *(reasoned, not observed)*
3. **Shutdown ordering** (`FR-ADR-033`): the requirement is `ECS stop timeout >
   SHUTDOWN_DRAIN_TIMEOUT_SECONDS (20)` plus release-and-exit time, because the deregistration delay
   runs before SIGTERM (AWS-04-12, below). The stricter safe bound is `stop timeout > deregistration delay + 20`.
   If the stop timeout is too short, SIGKILL lands mid-drain and this instance's holds are not
   released (they still expire within 180 s). Prep-queue row 23.
   - [AWS-04-04] The target group's deregistration delay defaults to 300 seconds while the ECS container stop timeout is capped at about 120 seconds, so the default delay fails the strict bound until the delay is lowered. *(reasoned, not observed)*
   - [AWS-04-12] When ECS stops a service task registered with a target group, it deregisters the target and waits out the deregistration delay before it sends SIGTERM, so the stop timeout, which counts from SIGTERM, does not include the delay. *(reasoned, not observed)*
4. **One task per service at a time, and a deploy is a downtime window** (prep-queue row 18).
   - [AWS-04-05] With one `t3.micro`, a fixed host port and minimum-healthy-percent 0, ECS stops the old api task before starting the new one, so every api deploy is a window in which `/api/*` returns errors from the load balancer. *(reasoned, not observed)*
5. **Bridge networking on the instance.**
   - [AWS-04-06] A `t3.micro` supports two network interfaces, one of which the instance itself uses, so the `awsvpc` network mode would fit only one task on the host and the other two services would fail to place. *(reasoned, not observed)*
6. **Outbound reach with no NAT Gateway**: SQS, SES, S3, SSM, ECR and CloudWatch Logs, from a public
   subnet (`FR-ADR-065`). No inbound rule other than the load balancer to the host ports.
   - [AWS-04-07] Without a NAT Gateway, a task in a public subnet reaches those AWS endpoints only through the instance's public IPv4 address, so an instance without one cannot pull images, read SSM parameters, send to SQS or write logs, and the task fails before the application logs anything. *(reasoned, not observed)*
7. **Secrets injected by the task definition from SSM** (`FR-ADR-054`), read by the **execution** role
   (prep-queue row 15). The application reads environment variables only and never calls SSM itself.
8. **Two queues** — `receipts` with long retention and a dead-letter queue; `resets` with retention no
   longer than `PASSWORD_RESET_TTL_SECONDS` (1800 s) and **no** dead-letter queue — see `06` §Password
   reset. Receipt orderings from `P-TKT-05`: visibility timeout `< RECEIPT_CLAIM_STALE_SECONDS` (900),
   `maxReceiveCount > ceil(900 / visibility)`.
   - [AWS-04-08] SQS deletes a message when its retention period elapses whether or not it was ever received, so a receipt queue whose retention is shorter than a worker outage loses receipts whose outbox rows are already marked sent. *(reasoned, not observed)*
9. **A read-only root filesystem** is the intended runtime mode for all three images (`FR-ADR-063`).
   A container that needs a writable filesystem has a bug.
10. **Memory hard limits on every container** — the values in the next section.
    - [AWS-04-09] A container that exceeds its ECS hard memory limit is killed by the kernel's out-of-memory handler without warning, so the symptom is a task restart with no application log line explaining it. *(reasoned, not observed)*

## The 1 GB memory arithmetic (`SRC-002 §5.4.1`, `§13.6`, `FR-ADR-064`, `P-XCT-21`)

**Every number in this section is an estimate from typical figures unless it says measured.** The
Phase 1 stack has run locally (image sizes and idle RSS measured, see prep-queue rows 21-22); nothing
has run in AWS. Phase 1 replaces each one with a measured resident set size, idle
and under load, and **if a measured figure breaks the sum, the client is told with the number** — no
limit is shaved to make the table balance.

The block below is the source of truth for the gate: `check_architecture.py` re-adds it and fails if
any stated total disagrees with the sum of its rows. Units are MiB.

```memory
# kind   | item                                                     | best | worst
host     | kernel, firmware and hypervisor reservation              |  60  |  80
host     | OS userland: systemd, journald, sshd, chronyd, SSM agent |  110 |  140
host     | Docker daemon, containerd, per-container shims           |  80  |  110
host     | ECS agent container                                      |  50  |  70
limit    | api (uvicorn, one worker, FastAPI, SQLAlchemy, boto3)    |  200 |  200
limit    | worker (same libraries, no HTTP server)                  |  150 |  150
limit    | frontend (static server and built assets)                |  15  |  15
physical | t3.micro RAM                                             | 1024 | 1024
oneoff   | migrate OR seed (never both; same image as worker)       |  150 |  150
stated   | host_total                                               |  300 |  400
stated   | limits_total                                             |  365 |  365
stated   | steady_committed                                         |  665 |  765
stated   | steady_headroom                                          |  359 |  259
stated   | oneoff_headroom                                          |  209 |  109
```

Read as a sum:

```
                           best case        worst case
OS + Docker + ECS agent      300 MiB          400 MiB      (host rows)
api + worker + frontend      365 MiB          365 MiB      (hard limits, not usage)
committed, steady            665 MiB          765 MiB
headroom, steady             359 MiB          259 MiB      of 1024
one-off migrate/seed task   +150 MiB         +150 MiB
headroom during a one-off    209 MiB          109 MiB
```

**Verdict: it fits, on estimates, with 259–359 MiB of steady headroom and 109–209 MiB while a
migration or seed task runs.** Nothing here is known not to fit in 1 GB (`SRC-002 §13.6`). Three things
make the headroom smaller than it looks, and none is in the table because none is measurable yet:

- **The headroom is not free memory.** The kernel needs page cache for the executables and Python
  libraries every process maps; a host with zero page cache thrashes before anything is killed.
- **A limit is a ceiling, not usage.** If the api measures 300 MiB under load, its limit must rise to
  ~320 and steady headroom falls to 139–239 MiB, and **109 − 120 = −11 MiB in the worst case during a
  one-off task — which would not fit.** That is the scenario Phase 1's measurement exists to rule in
  or out, and it would be reported, not absorbed.
- **There is no swap.** An over-committed host does not slow down; a container is killed.
- [AWS-04-10] ECS places a task by comparing task memory limits against the memory the agent registered for the instance, which does not subtract what the OS, Docker and the agent itself use, so a placement that succeeds is not evidence that the host has room. *(reasoned, not observed)*

**What the budget has already decided** (recorded so it is not re-argued): three processes, not four;
a static frontend server, not Node; **one** uvicorn worker; `DB_POOL_SIZE=5` + overflow 2 per process
against `db.t3.micro`'s ~110 connections; bcrypt in a 2-thread pool; posters redirected to S3, never
proxied through the api; no local S3 or SMTP container.

## Images (`FR-ADR-063`)

| Image | Base | Target size | Measured (local, 2026-10-18) |
|---|---|---|---|
| `backend` | multi-stage; wheels built in a build stage; `python:3.12.15-slim-trixie` runtime; non-root user | < 250 MB | **239 MB** by `docker images`; **56.5 MB** compressed (56,498,125 bytes in the image manifest, what a push uploads). Under the target by 11 MB; `JC-R6-04` expects boto3 in Phase 5 to push it over |
| `frontend` | multi-stage; Node builds Vite bundle; final stage `nginx:1.27.5-alpine`; non-root | well < 50 MB | **73.9 MB** by `docker images`, **over** the target; **21.0 MB** compressed (21,046,395 bytes), under it. Almost all of it is the nginx base image (74.5 MB on its own) |

These are image sizes, not memory. Nothing here was measured in AWS; which of the two figures ECR
counts against its 500 MB is stated in `docs/30 Deployment/P1_ECR.md` §2.

Tagged by git commit SHA; a task definition never references a moving tag. ECR's free tier is 500 MB
in total, so an ECR lifecycle policy keeping a few recent images per repository is required.

- [AWS-04-11] Without a lifecycle policy every push accumulates in ECR, and the first visible symptom is a push rejected or billed during a deploy rather than a warning beforehand. *(reasoned, not observed)*

## One-off commands

- **`migrate`** — never on boot (`FR-ADR-062`, `SRC-002 §7.8`). Run by hand as a one-off task with the
  owner credentials, before the api task that needs the new schema. **Alembic takes no advisory lock**
  (`GOTCHAS.md`, unproven here); running it as one hand-started step is what removes the race, so
  never start two.
- **`seed`** — Phase 2 onward; its own task definition family and its own SSM parameter
  (`SEED_DEFAULT_PASSWORD`, prep-queue row 19).
