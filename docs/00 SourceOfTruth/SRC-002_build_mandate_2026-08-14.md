# SRC-002 — FrontRow build mandate, as given by the client

```
Source type ....... Client build mandate (written)
Received .......... 2026-08-14
Author ............ the client (also the developer and the DevOps operator)
Original file ..... CLAUDE_CODE_BRIEF.md
Status ............ FROZEN — never edited
Citation form ..... SRC-002 §n
```

> **FROZEN INPUT. DO NOT EDIT.** This is the second frozen source. `SRC-001` says *what the product
> must do*; `SRC-002` says *how it must be built, what it may be built from, and who builds which
> part*. `CONSTITUTION.md` and `CLAUDE.md` are derived from this file and cite it clause by clause.
>
> The **only** permitted modification is a clearly-marked `ERRATUM` block appended at the foot.
> No errata exist yet.
>
> Clause anchors `§n` were added when the text was filed. **No wording was changed.**

> **A note on numbering (build session, not client text).** SpendWise, the prior project on this
> method, used `SRC-002` for the client's *rulings*. FrontRow has two written inputs rather than
> one, so `SRC-002` is the build mandate and the client's answers to `SRC-001 §10` will be filed as
> **`SRC-003`**. Recorded as a `[JUDGMENT CALL]` under `FR-ADR-002` rather than left as a silent
> divergence from the prior convention.

---

## §1 — Who I am and what I am trying to achieve

**§1.1** I am a developer learning **DevOps** and **systems design**. I am not building this product
to sell it. I am building it so that deploying and operating it teaches me real infrastructure
skills.

**§1.2** My split of work is deliberate:

**§1.2.1** **You write the application.** I do not want to spend my time on business logic, React
components, or SQL schemas.

**§1.2.2** **I do the deployment.** Docker builds, ECR pushes, ECS services, load balancers,
networking, CI/CD pipelines, monitoring. That is the part I want to struggle with.

**§1.3** So your job is not only to produce working code. Your job is to produce an application
whose **shape forces me to learn DevOps properly** when I deploy it.

**§1.4** You have full autonomy over implementation choices inside the constraints below. If you
believe a different approach teaches me more, take it, but write down why in `docs/decisions.md`.

## §2 — How I want things explained to me

**§2.1** Explain at the level of a 22 year old who can code but has never run production
infrastructure.

**§2.2** No figures of speech, no analogies, no metaphors. Say the literal thing.

**§2.3** Prefer short paragraphs over long bulleted instruction dumps.

**§2.4** When you finish a phase, write a short explanation file in `docs/` covering what you built,
why it is built that way, and what will break in production if I get the deployment wrong.

## §3 — The product in one paragraph

**§3.1** A movie ticket booking website. Users browse movies currently showing, pick a cinema, pick
a showtime, see a live seat map for that show, select seats, and confirm a booking. Selected seats
are locked for a short window while checkout happens, and released automatically if checkout is
abandoned. Movie data is pulled automatically from a public movie API on a schedule, so the site
always shows current releases. Admins manage cinemas, screens, showtimes, and pricing.

## §4 — Technology stack (fixed)

| Layer | Choice |
|---|---|
| **§4.1** Frontend | React + Vite, TypeScript |
| **§4.2** Backend | Python 3.12, FastAPI |
| **§4.3** Database | PostgreSQL (AWS RDS in production, container locally) |
| **§4.4** Cache and locks | Redis (AWS ElastiCache in production, container locally) |
| **§4.5** Async work | A separate worker process consuming AWS SQS |
| **§4.6** Scheduled jobs | A scheduler process, or a Lambda invoked by EventBridge |
| **§4.7** Migrations | Alembic |
| **§4.8** Auth | Own email + password with JWT. Do not use Cognito |
| **§4.9** Object storage | S3 for movie posters we cache ourselves |
| **§4.10** Container runtime | Docker, run on ECS backed by EC2 |
| **§4.11** Load balancing | AWS Application Load Balancer |

**§4.12** Do not introduce Kubernetes, Fargate, service meshes, or any managed service outside this
list without asking me first.

## §5 — Hard constraint: AWS Free Tier

**§5.1** Everything must be able to run inside AWS Free Tier limits.

**§5.2 Available to me for free:**

**§5.2.1** One `t3.micro` EC2 instance, 750 hours a month, 1 GB RAM.

**§5.2.2** One `db.t3.micro` RDS PostgreSQL instance, 20 GB storage.

**§5.2.3** One `cache.t3.micro` ElastiCache Redis node, 750 hours.

**§5.2.4** Application Load Balancer, 750 hours.

**§5.2.5** S3 5 GB, ECR 500 MB, SQS 1M requests, SNS, Lambda 1M requests.

**§5.2.6** CloudWatch basic metrics and 5 GB of logs.

**§5.3 Not available, do not design around them:** EKS, Fargate, NAT Gateway, AWS Secrets Manager,
Managed Grafana, OpenSearch.

**§5.4 What this means for your code:**

**§5.4.1** Total memory budget across all my containers is about 1 GB. Set explicit memory limits.
Keep the Python image slim. Prefer `RQ` or `Dramatiq` over Celery.

**§5.4.2** ECR only stores 500 MB, so use multi-stage Docker builds and a slim base image. Target a
final image under 250 MB.

**§5.4.3** Use **SSM Parameter Store** for secrets, not Secrets Manager.

**§5.4.4** Because I have no NAT Gateway, design the app so it can run in a public subnet with
strict security groups, and note anywhere the app needs outbound internet access.

**§5.4.5** Log to stdout as JSON. Do not write log files to disk.

## §6 — Work zones

> "this is the most important section"

### §6.1 Zone A — You build this completely

**§6.1.1** All backend application code, routers, services, models, migrations.

**§6.1.2** All frontend code and styling.

**§6.1.3** The seat locking and booking logic.

**§6.1.4** The movie sync job that calls the third party API.

**§6.1.5** Unit and integration tests.

**§6.1.6** Database seed scripts with sample cinemas, screens, and showtimes.

**§6.1.7** `docker-compose.yml` for **local development only**.

**§6.1.8** A load testing script (see section 9).

### §6.2 Zone B — You write it, but heavily commented, because I must understand and edit it

**§6.2.1** The production `Dockerfile` for each service.

**§6.2.2** Container entrypoint scripts.

**§6.2.3** Health check and readiness endpoints.

**§6.2.4** Environment variable configuration and validation.

**§6.2.5** Graceful shutdown handling.

**§6.2.6** Every line in Zone B that exists for a production reason gets a comment saying what
breaks without it.

### §6.3 Zone C — Do NOT write these. This is my homework.

**§6.3.1** Terraform or CloudFormation.

**§6.3.2** ECS task definitions and service definitions.

**§6.3.3** ALB, target group, listener rule, or security group configuration.

**§6.3.4** VPC and subnet layout.

**§6.3.5** GitHub Actions or any CI/CD pipeline.

**§6.3.6** CloudWatch alarms and dashboards.

**§6.3.7** Any `aws` CLI commands that create infrastructure.

**§6.4** Instead of writing these, produce **`docs/deployment-tasks.md`** containing, for each Zone C
item:

**§6.4.1** What I need to build.

**§6.4.2** What the application expects from it (ports, health check paths, env vars, IAM
permissions needed).

**§6.4.3** Acceptance criteria so I know when I got it right.

**§6.4.4** Two or three common mistakes people make on that step.

**§6.5** Do not give me the answer. Give me the specification and let me fail against it.

## §7 — Application design requirements that exist purely to teach me DevOps

> "Build the app so that it is impossible to deploy without learning these things."

**§7.1 Twelve-factor config.** Every setting comes from environment variables. The app must crash on
startup with a clear message if a required variable is missing.

**§7.2 Separate processes.** The API and the background worker must be different containers from the
same or different images, scaled independently.

**§7.3 Stateless containers.** No local session state, no local file uploads. Killing any container
mid-request must not corrupt data.

**§7.4 Health endpoints.** `/health/live` returns 200 if the process is alive. `/health/ready`
returns 503 if the database or Redis is unreachable. These must behave differently, because the load
balancer treats them differently.

**§7.5 Graceful shutdown.** On SIGTERM, stop accepting new requests, finish in-flight ones, release
Redis locks held by that instance, then exit.

**§7.6 Structured logging.** JSON to stdout, with a request ID propagated through every log line,
including worker jobs triggered by that request.

**§7.7 A `/metrics` endpoint** in Prometheus format, exposing request counts, latency, seat lock
counts, and queue depth.

**§7.8 Database migrations run as a separate step**, never automatically on app boot. I need to learn
why that distinction matters.

**§7.9 Fail loudly on dependency loss.** If Redis is down, do not silently fall back to the database
for locks. Return an error. I need to see the failure.

## §8 — Systems design requirements

> "These are the concepts I want to learn by operating this app."

### §8.1 Seat locking

**§8.1.1** When a user selects seats, place a lock in Redis with a TTL of 7 minutes, keyed per
showtime and seat.

**§8.1.2** The lock must be acquired atomically. Two users clicking the same seat at the same
millisecond must produce exactly one winner.

**§8.1.3** Use a lock token so a client can only release a lock it owns.

**§8.1.4** On lock expiry, the seat becomes available again with no cleanup job needed.

**§8.1.5** Confirming a booking must also take a database-level guard, so that Redis being wrong
cannot oversell a seat. Use a unique constraint on `(showtime_id, seat_id)` plus optimistic locking
or `SELECT ... FOR UPDATE`.

### §8.2 Caching

**§8.2.1** Cache the seat map per showtime with a short TTL, invalidated on any booking or lock
change. Use cache-aside.

**§8.2.2** Cache the movie list and showtime list, which are read constantly and change rarely.

**§8.2.3** Document in code where a cache stampede could happen and how you prevented it.

### §8.3 Idempotency

**§8.3.1** The booking confirmation endpoint takes an `Idempotency-Key` header. Retrying the same key
returns the original result rather than creating a second booking.

### §8.4 Rate limiting

**§8.4.1** Token bucket in Redis on seat selection and booking endpoints, per user and per IP.

**§8.4.2** Return 429 with a `Retry-After` header.

### §8.5 Queueing

**§8.5.1** After a booking is confirmed, push a message to SQS. The worker sends the confirmation
email and generates the ticket QR code.

**§8.5.2** Handle retries and configure a dead letter queue path. Make failures visible.

### §8.6 Live seat map

**§8.6.1** Start with polling every 3 seconds, because it is simple and works behind any load
balancer.

**§8.6.2** Structure the code so I can switch to WebSockets later as a second exercise, and write a
note in `docs/` explaining what changes on the load balancer when I do.

## §9 — Concurrency proof

**§9.1** Write a script, `scripts/stress_seats.py`, that fires 50 simultaneous requests for the same
seat and asserts exactly one succeeds. This must run against local Docker and against my deployed
environment by changing a base URL.

**§9.2** Also write a light load test I can point at the ALB to see autoscaling behaviour.

## §10 — Movie data sync

**§10.1** Use **TMDB** (The Movie Database).

**§10.2** Free developer API key, and it is free for non-commercial use provided TMDB is credited as
the data and image source. Put that attribution in the site footer.

**§10.3** Base URL `https://api.themoviedb.org/3`.

**§10.4** Useful endpoints: `/movie/now_playing`, `/movie/upcoming`, `/movie/{id}`,
`/discover/movie`. Support a `region` parameter so I can point it at one country.

**§10.5** Read the key from an environment variable. Never commit it.

**§10.6 Requirements for the sync job:**

**§10.6.1** Runs on a schedule, roughly daily. Implement it so it can be triggered three ways: a CLI
command, an HTTP endpoint protected by an admin token, and a scheduled trigger. That way I can wire
it to EventBridge or a cron container and compare the two.

**§10.6.2** Upsert by TMDB movie ID. Running it twice must not create duplicates.

**§10.6.3** Download posters once, store them in S3, and serve our own URLs. Do not hotlink.

**§10.6.4** Handle TMDB rate limits with backoff, and log every sync run with counts of created,
updated, and skipped records.

**§10.6.5** New movies land in a `pending` state. An admin publishes them before they appear.
Showtimes are never created automatically.

**§10.6.6** If TMDB is unreachable, the sync fails cleanly and the site keeps working with existing
data.

## §11 — Repository layout

**§11.1** Use a monorepo. Make the boundaries obvious, because I need to be able to point a
Dockerfile at each service independently.

```
.
├── backend/
│   ├── app/
│   │   ├── api/            # routers
│   │   ├── core/           # config, logging, security
│   │   ├── domain/         # booking, locking, pricing logic
│   │   ├── models/
│   │   ├── workers/        # SQS consumer
│   │   ├── jobs/           # TMDB sync
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   └── Dockerfile
├── scripts/
│   ├── seed.py
│   └── stress_seats.py
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── deployment-tasks.md
│   └── runbook.md
├── docker-compose.yml       # local development only
├── .env.example
└── README.md
```

## §12 — Build order

**§12.1** Do not build everything at once. Stop at the end of each phase and tell me what to test.

**§12.2 Phase 1** — Repo skeleton, config loading, health endpoints, structured logging, local
docker-compose with Postgres and Redis. Nothing else. I deploy this to ECS before we go further, so I
learn the pipeline against something trivial.

**§12.3 Phase 2** — Data model, migrations, seed data, admin CRUD for cinemas, screens, showtimes,
and pricing.

**§12.4 Phase 3** — Public browsing pages, movie list, showtime list, seat map read path, with
caching.

**§12.5 Phase 4** — Seat locking, booking confirmation, idempotency, the concurrency test.

**§12.6 Phase 5** — SQS worker, confirmation emails, QR tickets, dead letter handling.

**§12.7 Phase 6** — TMDB sync job and admin publishing flow.

**§12.8 Phase 7** — Metrics endpoint, rate limiting, load testing script, runbook.

## §13 — Rules

**§13.1** Ask me before adding any dependency that is not obviously necessary.

**§13.2** Do not run any `aws` command.

**§13.3** Do not write anything listed in Zone C.

**§13.4** Do not commit secrets. Ship a complete `.env.example`.

**§13.5** When you make a decision I did not specify, record it in `docs/decisions.md` with the
reason and the alternative you rejected.

**§13.6** If a requirement in this file will not fit in 1 GB of RAM, tell me instead of quietly
working around it.

---

## §E — Errata

**Six errata, all filed 2026-08-14 from `SRC-003`.** The clause text above is never struck where it
stands; the erratum governs over it.

**`E-1` — `§8.1.1`, a lock TTL of 7 minutes.** The hold is **3 minutes**, read from a configuration
value rather than a constant. *(`SRC-003 OPEN-HOLD-01`)*

> This erratum is the one the method was built to catch. `SRC-001 §10.9` asked how long seats should
> be held and answered "we assumed 7 minutes". `§8.1.1` above then stated 7 minutes as a firm
> requirement. The assumption had become a specification without anyone deciding it. When it was
> finally put to the client it came back **different**.

**`E-2` — `§10`, the TMDB section, every clause.** Withdrawn **in full**. No TMDB, no external movie
API, no API key, no `region` parameter, no rate-limit backoff, no upsert-by-external-id, no
pending/publish import state, no three trigger routes, no "TMDB unreachable" path. The administrator
creates movies by hand. **`§10.6.3` survives in effect**: posters live in S3 and we serve our own
URLs, we simply upload them instead of downloading them. *(`SRC-003 OPEN-TMDB-01`)*

**`E-3` — `§12.7`, Phase 6.** Phase 6 becomes **admin movie management** — create a movie, upload a
poster, set the display window, publish. A **new Phase 8** adds the manager and admin dashboard.
Phases 1–5 and 7 are unchanged. *(`SRC-003 OPEN-TMDB-01`, `OPEN-SCOPE-01`)*

**`E-4` — `§4.6`, a scheduler process or a Lambda invoked by EventBridge.** Withdrawn. With the sync
gone, **nothing in this system runs on a schedule.** Three long-running processes remain: the API,
the worker, and a static frontend container. *(`SRC-003 OPEN-PROC-01`, `OPEN-TMDB-01`)*

**`E-5` — `§8.5.1`, the worker generates the ticket QR code.** The worker **sends the receipt
email**, carrying the unique booking reference, the seat numbers, the hall and the showtime. No QR
code is generated anywhere. *(`SRC-003 OPEN-TICKET-01`)*

**`E-6` — `§4`, the approved service list.** **Amazon SES is added.** `§4.12` required the client's
permission before a service outside the list entered the design; it was asked for and granted. SES
is now load-bearing rather than incidental: the emailed receipt is the customer's only proof of
purchase and their only way into the hall. *(`SRC-003 OPEN-EMAIL-01`, `OPEN-BOOK-02`)*
