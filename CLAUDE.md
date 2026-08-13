# FrontRow — Claude Code Project Guide

> A movie ticket booking platform, built end to end from documents, by LLMs.
> **The build session writes application code. The client builds all AWS by hand.**
>
> Gate: `CONSTITUTION.md` · Frozen sources: `docs/00 SourceOfTruth/` ·
> Decisions: `docs/01 ADR/ADR_DECISION_RELEASE_LEDGER.tsv`

## Read at the start of EVERY session

1. **`GOTCHAS.md`** — the trap ledger. Before writing code, not after debugging.
2. **`PROGRESS.md`** — the last session block. What was done, what is half-done.
3. **`handoffs/`** — the newest `HANDOFF_<stamp>_<user>.md`. The previous session's own account.
4. **`COORDINATION.md`** — only if the DevOps session is running in parallel.

`/ss` does all four and reconciles them against git. **Start every session with `/ss`. End every
session with `/tt`.** A session that ends without `/tt` has lost its memory.

## Mission

A website where a customer browses what is playing, picks a cinema and a showtime, sees a live seat
map, chooses seats, pays, and arrives with a ticket on their phone. **A seat is never sold twice.**
Movie data arrives from TMDB on a schedule and appears only after a human publishes it.

The client is also the developer and the operator. **This project exists so that deploying and
operating it teaches DevOps** (`SRC-002 §1`). Where two designs are equally correct and one forces
the operator to confront a real infrastructure concern, that one wins — and the reason is recorded.

## Status — 2026-08-14

**Stage 0.** The repository spine, the frozen sources and the root canon exist. **No ADRs are filed,
no derivation document exists, and no application code exists — and none should yet.** The
derivation chain reaches code at `06 DataModel`, not before.

**Thirty of the client's own questions are unanswered** (`SRC-001 §10`, mirrored as `OPEN-*` rows in
`CONSTITUTION.md` Article X). Until they land as `SRC-003`, nothing downstream may guess at them.

## The document set — what to read for what

Numbered in **dependency order**, not generation order. Each is derived from the ones above it and
**cites them**.

| Folder | What it holds | State |
|---|---|---|
| `00 SourceOfTruth/` | `SRC-001` the product requirement + `SRC-002` the build mandate — **frozen and SHA-256 hashed**. `SRC-003` (client rulings) not yet received. | **written** |
| `01 ADR/` | Decision records + the fail-closed ledger. | empty |
| `02 BRD/` | Business requirements, each citing a source. | empty |
| `03 PRD/` | **The document the code is written from.** Plus the API contract. | empty |
| `05 Bible/` | Stories and binary acceptance criteria. The scope arbiter. | empty |
| `05 B DesignSystem/` | Tokens + real CSS. Every contrast figure computed, not claimed. | empty |
| `06 DataModel/` | A **package**: `datamodel.json` (spec of record) → generated `schema.sql`, `TRACEABILITY.tsv`. | empty |
| `07 Architecture/` | `for_llm/` to orient a session · `for_humans/` to decide from, including the accepted weaknesses. | empty |
| `08 SIT/` · `09 NegativeTesting/` | Positive cases (one per acceptance criterion) + the cases that try to break it. | empty |
| `10 EngineeringLedger/` | Derived from the Bible. **`/ss` reads this for the frontier.** Only `Status` is hand-edited. | empty |
| `11 Journeys/` | Persona journeys, each walk naming the seam it crosses. | empty |
| `12 DesignReview/` | **The gate before code.** | empty |
| `13`–`40` | Lifecycle. `30 Deployment` holds the client's AWS prep queue. | empty |

**Authority on conflict** (`CONSTITUTION.md` Art II.1): raw `SRC-001` → raw `SRC-002` → a client
ruling → an `APPROVED` ADR → PRD → BRD → Bible → everything else. **Stricter always wins.**

**Where `SRC-001` and `SRC-002` disagree, neither wins** (Art II.2). That is a contradiction in the
client's own instructions and it becomes an Article X row. Five are known already: payment, the role
count, cancellation, reporting, and the queue technology.

## Stack — fixed by `SRC-002 §4`. Do not substitute, even for something better.

**Frontend** React + Vite + TypeScript
**Backend** Python 3.12 · FastAPI
**Database** PostgreSQL — RDS in AWS, a container locally
**Cache and locks** Redis — ElastiCache in AWS, a container locally
**Async** a separate worker process consuming SQS *(see `OPEN-QUEUE-01` — `§5.4.1` contradicts this)*
**Scheduled** a scheduler process, or Lambda invoked by EventBridge
**Migrations** Alembic · **Auth** own email + password with JWT, **never Cognito**
**Storage** S3, for movie posters we cache ourselves
**Runtime** Docker on **ECS backed by EC2** · **ALB** · **SSM Parameter Store** for secrets

**Forbidden and not to be designed around** (`§5.3`): EKS, Fargate, NAT Gateway, Secrets Manager,
Managed Grafana, OpenSearch. Kubernetes, service meshes and anything outside `§4` need the client's
permission first (`§4.12`).

## The shape (`SRC-002 §11`)

```
backend/app/{api,core,domain,models,workers,jobs}/ · backend/migrations/ · backend/tests/
frontend/src/  ·  scripts/{seed.py,stress_seats.py}  ·  docker-compose.yml (local dev only)
```

A monorepo with obvious boundaries, because each service gets its own Dockerfile.

## Non-negotiable invariants — enforce in CODE, never via a prompt

- **A seat is never sold twice** (`SRC-001 §2.2`, `§7.1`). Enforced **twice, in two systems**: a
  Redis lock provides the hold, a **unique constraint on `(showtime_id, seat_id)`** plus
  `SELECT ... FOR UPDATE` provides the truth. **The database guard may not be waived** — Redis being
  wrong must never oversell.
- **Locks are atomic, carry a token, and expire on their own.** Two users clicking one seat in the
  same millisecond produce exactly one winner. A client can only release a lock it owns. Expiry needs
  no cleanup job.
- **Red-proof the guard.** Drop the constraint on purpose, watch the stress script produce two
  winners, restore it, verify the restore. A gate nobody has watched fail is decoration.
- **If Redis is down, return an error.** Never fall back to the database for locks (`§7.9`). A silent
  fallback turns a visible outage into an invisible correctness risk.
- **Integer minor units for money. Never a float.** Decimal at the boundary, int in persistence,
  formatted string at render time only. **The currency is not yet ruled** (`OPEN-LOCALE-01`) — do not
  hardcode a symbol, a ratio, or a rounding rule.
- **`Idempotency-Key` on booking confirmation.** The same key returns the original result, never a
  second booking and never a second charge.
- **No card data anywhere** — not a log, not a column, not a fixture, not a seed script.
- **Authorisation once, on the router**, as a dependency — never per handler.
- **A manager sees only their own cinema.** Test it with a non-empty result for their own and a
  denied result for another; a test asserting only "denied" passes against a query that returns
  nothing for anybody.
- **Every privileged action writes its audit row in the same transaction as the change.**
- **Containers are stateless.** No local session state, no local file writes. Killing one mid-request
  must not corrupt data.
- **Migrations never run on boot** (`§7.8`).
- **`/health/live` and `/health/ready` behave differently on purpose** (`§7.4`). Ready returns 503
  when Postgres or Redis is unreachable. Collapsing them defeats why they exist.
- **On SIGTERM: stop accepting, drain in-flight, release this instance's Redis locks, exit** (`§7.5`).
- **JSON logs to stdout, never a file**, with a request id propagated into worker jobs (`§7.6`).
- **TMDB attribution in the footer** (`§10.2`). It is a licence condition, not a design choice.

## Roles

`SRC-001 §4` names **five** — guest, customer, staff, manager, administrator. `SRC-002 §3.1` names
**one**. That is a source conflict (`OPEN-ROLE-01`) and the build session may not pick.

Until it is ruled: **model five in the schema, expose only what a ruled phase needs.** Expanding a
role set later is a rewrite; collapsing one is a migration.

## Status law — the rule that matters most

| Status | Meaning |
|---|---|
| `RULED` | decided, with a citation |
| `PROVISIONAL` | written down, a ruling outstanding |
| `OPEN` | genuinely unruled — **escalate, never invent** |
| `ASSUMED` | inference; never hardens into a constraint |

An agent that hits `OPEN` and fills in something sensible has committed the cardinal sin of this
project. Open items live in `CONSTITUTION.md` Article X. **All 34 are currently `OPEN`.**

Watch for the specific failure this project has already produced once: `SRC-001 §10.9` asks "we
assumed 7 minutes" and `SRC-002 §8.1.1` states 7 minutes as a requirement. **An assumption hardened
into a specification without ever being confirmed.** That is `OPEN-HOLD-01`.

## Reserved — no model decides these, at any confidence

Money · anything irreversible or public · secrets · legal and data protection · amending
`CONSTITUTION.md` · what the product is and what "done" means · scope changes · **waiving any
quality check** · anything marked `[HUMAN]`.

No timeout defaults past these. Adopting a *stricter* option is **not** a waiver and needs no
signature.

The build session decides non-reserved technical questions and logs each as one `[JUDGMENT CALL]`
line. Reversible reserved matters are decided then **batched** for the client to reverse.
Reserved-and-irreversible stops and waits.

## Honesty floor (`CONSTITUTION.md` Art VII)

**No invented evidence** — unverified means writing the word unverified · **worst number first**,
every rate carries its count · **a gap stays a gap** · **respect one-way doors** · **the log is the
memory** · **scope as written** · **the writer never verifies its own work** — where no second human
exists the substitute is a fresh zero-context session, and the substitution is recorded.

Plus two the client asked for by name: **say it when something will not fit in 1 GB** rather than
quietly working around it (`§13.6`), and **explain at the level of someone who can code but has never
run production infrastructure, with no analogies or metaphors** (`§2`).

## Definition of Done

Failing test first, from the acceptance criterion. Then minimal code. Then edge and negative cases.
Done only when the acceptance criterion passes, tests are green, **the concurrency gate is still
green**, and a handover is written.

**Never fake, skip, `xfail`, comment out or delete a test to reach green.** A red gate blocks — mark
it `Blocked` with a note and surface it.

**A test that reads the wall clock is a defect.** Time is injected.

## The concurrency proof — never waivable

`scripts/stress_seats.py` fires **50 simultaneous requests for one seat and asserts exactly one
succeeds** (`SRC-002 §9.1`). It runs against local Docker and against the deployed environment by
changing a base URL. Then the unique constraint is dropped on purpose, the script is watched
producing more than one winner, the constraint is restored, and the restore is verified.

## Zones — who writes what (`SRC-002 §6`)

**Zone A — the build session writes it completely.** Backend, frontend, seat locking, the TMDB sync
job, tests, seed scripts, `docker-compose.yml` for local development only, the load test.

**Zone B — the build session writes it, heavily commented, because the client must edit it.**
Production Dockerfiles, entrypoints, health and readiness endpoints, environment configuration and
validation, graceful shutdown. **Every line that exists for a production reason carries a comment
saying what breaks without it.**

**Zone C — the client's homework. The build session writes none of it.** Terraform and
CloudFormation, ECS task and service definitions, ALB / target group / listener / security group
configuration, VPC and subnet layout, GitHub Actions and any CI/CD, CloudWatch alarms and dashboards,
any `aws` command that creates infrastructure.

Instead, `docs/30 Deployment/` gets a specification per Zone C item: what to build, what the
application expects of it, acceptance criteria, and two or three common mistakes.
**`SRC-002 §6.5`: do not give the answer. Give the specification and let the client fail against it.**

## AWS

**The build session creates nothing in AWS.** As of 2026-08-14 the client has supplied credentials
for **read-only inspection** — describe, list, get — so the build session can check what the client
built against the specification. **No create, no modify, no delete, until the client says so in
writing.**

In exchange for Zone C, the build session owes **advance notice**: every AWS dependency goes into
`docs/30 Deployment/AWS_PREP_QUEUE.md` with a *needed by* stage **and** is said in chat, early enough
to prepare while code is still being written. Never announce a dependency on the day it blocks.

Consequence, stated every time it matters: this session **has never observed the app running in
AWS**, so every claim about AWS behaviour is **reasoned, not observed**, and is labelled that way.

## The memory budget — say it now, not in month two

Roughly **1 GB total** on a `t3.micro` (`§5.4.1`), shared with an operating system, a Docker daemon
and an ECS agent. `SRC-002 §12` implies four long-running processes: API, worker, scheduler,
frontend. That does not fit comfortably.

Recommendation on the record (`OPEN-PROC-01`): fold the scheduler into an EventBridge trigger against
the admin sync endpoint that `§10.6.1` already requires, and serve the built frontend from a small
static container. Three processes, not four. Final image under **250 MB** with a multi-stage build,
because ECR's free tier holds 500 MB total. *(reasoned, not observed)*

## Win condition — define victory, then stop

A guest browses current movies, picks a cinema and a showtime, sees a live seat map, selects seats,
holds them, pays through the simulated provider, and gets a booking reference and a scannable
ticket; **50 concurrent requests for one seat produce exactly one winner, proved at the database
layer**; TMDB data syncs on a schedule and appears only after a human publishes it; and it runs on
AWS from containers the client deployed by hand.

## Out of scope — do not build (`SRC-001 §6`)

No native mobile app · no food and beverage ordering · no loyalty points or membership tiers · no
multi-language interface · no point-of-sale integration.

**Excluded is not blocked** (`§6.6`). The client may ask for any of these later, so no design
decision may make one impossible.
