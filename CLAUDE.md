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

A website where a customer browses what is playing at **one theatre with six halls**, picks a
showtime, sees a live seat map, chooses seats, pays through a **simulated** provider, and receives an
**emailed receipt carrying a unique booking reference** that gets them in at the door.
**A seat is never sold twice.**

**An admin creates every movie by hand** — title, poster, and a display window. There is no external
movie API and **nothing in this system runs on a schedule.**

The client is also the developer and the operator. **This project exists so that deploying and
operating it teaches DevOps** (`SRC-002 §1`). Where two designs are equally correct and one forces
the operator to confront a real infrastructure concern, that one wins — and the reason is recorded.

## Status — 2026-08-14

**All three frozen sources exist.** `SRC-003` carries the client's rulings on all 40 Article X rows.
**Sixteen errata** were filed as a result — ten against `SRC-001`, six against `SRC-002` — and the
product changed materially. **No application code exists, and none should yet.** The derivation chain
reaches code at `06 DataModel`.

**Four rows remain open**, all reserved: `OPEN-TLS-01` (deferred, the client is sourcing a domain),
`OPEN-ATTRIB-01`, `OPEN-SHOWCANCEL-01`, `OPEN-EMAILFAIL-01`.

### ⚠ Three rulings are `PROVISIONAL` — read `SRC-003` before relying on any of them

They required the build session to reconcile two of the client's own answers, and each records the
reading it rejected. **One message from the client reverses any of them.**

1. **Four roles, not one** (`SRC-003 C-1`). `OPEN-ROLE-01` said "do not make more personas"; the very
   next answer described two managers per hall with a dashboard.
2. **One cinema with six screens** (`C-2`), with the `cinema` entity kept in the schema anyway.
3. **Sales close 15 minutes *after* the advertised start** (`OPEN-BOOK-03`). The answer — "yes 15
   minutes" — was ambiguous between before and after.

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
**Async** a worker consuming **SQS** in AWS, **ElasticMQ** locally — one queue interface over both
**Scheduled** **nothing.** The scheduler is deleted; there is nothing left to schedule
**Email** **Amazon SES** — added to the approved list by `SRC-003 OPEN-EMAIL-01`
**Migrations** Alembic · **Auth** own email + password with JWT, **never Cognito**
**Storage** S3, for movie posters **the admin uploads**
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
- **Integer paise. Never a float.** Currency is **INR**, minor unit ratio **100**, timezone
  **Asia/Kolkata** (`SRC-003 OPEN-LOCALE-01`). Decimal at the boundary, int in persistence, formatted
  string at render time only. **The ratio is a one-way door** — bookings are permanent, so
  reinterpreting the unit later rewrites what every past customer paid. It stays a named
  configuration value, never a literal scattered through the code.
- **Pricing is a base price per showtime plus a fixed percentage uplift per seat category**, applied
  uniformly across every hall and show (`SRC-003 OPEN-PRICE-01`). **A percentage of an integer number
  of paise does not divide evenly — the rounding rule is specified with a worked example**, because
  an unstated one is how two screens disagree about a total.
- **The hold is 3 minutes**, from configuration (`SRC-003 OPEN-HOLD-01`, superseding the 7 minutes in
  `SRC-002 §8.1.1`). Maximum **10 seats** per booking, enforced server-side.
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
- **No card data anywhere.** Payment is simulated and no provider is ever integrated
  (`SRC-003 OPEN-PAY-01`), so the rule is trivially satisfiable — keep it satisfied, so nobody adds
  a card-shaped fixture out of habit.
- **The emailed receipt is the customer's only proof of purchase and their only way into the hall.**
  If SES fails after payment is captured, the customer has paid and cannot enter. That failure path
  is `OPEN-EMAILFAIL-01` and it is still open — the booking screen shows the reference on screen too.

## Roles — ruled, `PROVISIONAL` (`SRC-003 C-1`)

| Role | Account | Can |
|---|---|---|
| **guest** | none | browse movies, showtimes and the seat map. **Cannot hold or book.** |
| **customer** | required | hold seats, pay, view their own bookings and receipts |
| **manager** | required | **read only** — the dashboard for their assigned screens. 2 per hall, 12 total. |
| **admin** | required | everything, including everything a manager can do |

**No cinema-staff role and no door scanner.** Entry is a manual human check of the booking reference.

**Every privileged write belongs to the admin alone** (`SRC-003 OPEN-OPS-03`). A manager endpoint
that writes anything is a defect, not a feature.

## Status law — the rule that matters most

| Status | Meaning |
|---|---|
| `RULED` | decided, with a citation |
| `PROVISIONAL` | written down, a ruling outstanding |
| `OPEN` | genuinely unruled — **escalate, never invent** |
| `ASSUMED` | inference; never hardens into a constraint |

An agent that hits `OPEN` and fills in something sensible has committed the cardinal sin of this
project. Open items live in `CONSTITUTION.md` Article X. **Four remain open**, all reserved:
`OPEN-TLS-01`, `OPEN-ATTRIB-01`, `OPEN-SHOWCANCEL-01`, `OPEN-EMAILFAIL-01`. The other 40 were ruled
on 2026-08-14 and live in `SRC-003`. Count them from the file, never from this sentence.

**The specific failure this project already produced, and what came of it:** `SRC-001 §10.9` asked
"how long should seats be held? We assumed 7 minutes" and `SRC-002 §8.1.1` then stated 7 minutes as a
requirement. An assumption hardened into a specification without anyone deciding it. When it was
finally put to the client it came back **3 minutes** — a different answer. That is the argument for
the whole mechanism, and it is why `ASSUMED` may never become a `MUST`.

**Five rulings are `ASSUMED`, not `RULED`** — the client said "you pick" on hall sizes, peak
concurrency and seat category names. They never harden into constraints. Flag them each time they
matter.

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
and an ECS agent — call it 300–400 MB gone before anything of ours starts.

**Ruled** (`SRC-003 OPEN-PROC-01`): **three long-running processes, not four.** The scheduler is
deleted, and with TMDB gone there is nothing left for it to run. The frontend is served from a small
static container, not a Node process.

| Process | Budget |
|---|---|
| API | ~200 MB |
| Worker | ~150 MB |
| Static frontend | ~15 MB |

Final image under **250 MB** with a multi-stage build, because ECR's free tier holds 500 MB total.
*(reasoned from typical figures, not observed — this has never run in AWS.)* **Measure it in Phase 1
and replace these numbers with real ones.**

## Win condition — define victory, then stop

A guest browses current movies, registers, picks a showtime, sees a live seat map, holds seats for 3
minutes, pays through the simulated provider, and receives an emailed receipt carrying a unique
booking reference; **50 concurrent requests for one seat produce exactly one winner, proved at the
database layer**; an admin creates a movie by hand and it appears to customers; a manager sees their
own halls' numbers and not anyone else's; and it runs on AWS from containers the client deployed by
hand.

## The phases (`SRC-002 §12`, revised by `SRC-003`)

1 skeleton · 2 data model and admin CRUD · 3 browsing and the seat-map read path · 4 seat locking,
booking, idempotency, the concurrency test · 5 SQS worker and the receipt email ·
**6 admin movie management** *(was the TMDB sync)* · 7 metrics, rate limiting, load test, runbook ·
**8 the manager and admin dashboard** *(new)*.

## Out of scope — do not build

From `SRC-001 §6`: no native mobile app · no food and beverage ordering · no loyalty points or
membership tiers · no multi-language interface · no point-of-sale integration.

Added by `SRC-003`: **no external movie API** · **no scheduled job of any kind** · **no QR code** ·
**no ticket scanner or validation endpoint** · **no customer cancellation and no refunds** · **no
real payment provider, ever** · **no accessible-seat marking, no couple seats, no gap rule** · **no
upcoming-releases section** · **no CSV export**.

**Excluded is not blocked** (`§6.6`). The client may ask for any of these later, so no design
decision may make one impossible — which is why the schema keeps a `cinema` entity, a booking status
and a `cancelled_at` column that v1 exposes through no endpoint.
