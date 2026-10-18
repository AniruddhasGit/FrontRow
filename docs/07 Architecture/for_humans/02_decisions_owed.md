# 02 — Decisions owed

> **compressed per SRC-004 R-1.** Every `CONSTITUTION.md` Article X row still open, what each one
> blocks, and the phase where it starts to cost something. Then the rows `SRC-004` closed, the
> questions this goal raised, the judgment calls you may reverse, and the AWS additions.
>
> **Counted from the files, not typed.** `check_architecture.py` reads Article X (sections X.0–X.0g)
> and the `## R-` headings of `SRC-004`, and fails unless the two tables below are exactly
> *Article X minus SRC-004* and *Article X ∩ SRC-004*. At the time of writing: 28 rows in Article X,
> 5 closed by `SRC-004`, **23 still open**. Article X itself has not yet been updated for `SRC-004`;
> that edit belongs to the governance lane, not this goal.

## Still open — what each blocks

| Row | Class | What it blocks | Bites in |
|---|---|---|---|
| `OPEN-TLS-01` | reserved: product | `COOKIE_SECURE` stays false; the deployed environment cannot be given the other name (Art VIII.14); prep-queue row 14 (ACM) stays `BLOCKED` | Phase 1, and every phase after |
| `OPEN-ATTRIB-01` | reserved: legal | whether posters/titles from a licensed source may be shown and with what attribution; the presigned-redirect endpoint is the one place a check could live | Phase 6 |
| `OPEN-SHOWCANCEL-01` | reserved: money, irreversible | any admin action that withdraws a showtime that has bookings; `FR-ADR-023`. No such endpoint is built until ruled | Phase 2 (showtime admin) |
| `OPEN-EMAILFAIL-01` | reserved: product | what the customer is told when SES definitively fails after capture (`P-TKT-10`); whether a DLQ alarm is needed | Phase 5 — `08` row F-01 |
| `OPEN-PRICEBOUND-01` | reserved: money | an upper bound on base price and uplift; **a mistyped ₹25,000 is accepted today** | Phase 2 |
| `OPEN-RPTSCOPE-01` | reserved: access to financial data | whether a manager's scope has a start date; today a new manager reads a hall's full history | Phase 8 |
| `OPEN-RPTIMMUT-01` | reserved: reporting integrity | whether a showtime edited after bookings rewrites reported history | Phase 2 (edit), Phase 8 (reports) |
| `OPEN-ADMINCOUNT-01` | reserved: access control | how a second admin is created; none can be, today | Phase 2 |
| `OPEN-MGRBOOK-01` | reserved: access control | whether the hold/confirm routers admit `manager` (the contract says yes); one dependency changes on a ruling | Phase 4 |
| `OPEN-CINEMA-01` | reserved: scope | a second venue (re-opens the cinema filter and manager scoping) | not v1 |
| `OPEN-TURNAROUND-01` | product | the minimum gap between showtimes in one hall; the overlap check uses zero today | Phase 2 |
| `OPEN-ADMINRATE-01` | product | rate limits on admin endpoints, incl. poster uploads into a 5 GB allowance | Phase 6–7 |
| `OPEN-SEATBATCH-01` | product | a seat-layout generator; without one a hall is laid out seat by seat and a typo is permanent once a showtime exists | Phase 2 |
| `OPEN-FORMAT-01` | product | what a "format" is and its values | Phase 2–3 |
| `OPEN-SORT-01` | product (scope) | which sort orders a customer may choose | Phase 3 |
| `OPEN-BRWVIS-01` | product | whether showtimes keep selling after their film's display window ends | Phase 3 |
| `OPEN-CACHE503-01` | build session, escalated | a superseding ADR for two `APPROVED` ADRs that disagree about one endpoint (`docs/03 PRD/` §S8.7); the stricter reading is built meanwhile | Phase 3 |
| `OPEN-DOORVERIFY-01` | reserved: scope | **how the door tells a real reference from an invented one** — nothing in the product exposes a showtime's references to staff. This is where the win condition's "gets them in at the door" is redeemed | before the first real customer |
| `OPEN-DUPREF-01` | reserved: product | who is admitted when one reference is presented twice | before the first real customer |
| `OPEN-HOLDRECOVER-01` | reserved: scope | a customer who closes the tab cannot see or reuse their own live hold for up to 180 s | Phase 4 |
| `OPEN-BULKBUY-01` | reserved: scope | nothing limits one customer buying a whole hall in ten-seat instalments | Phase 4 |
| `OPEN-EMAILOWN-01` | reserved: product | registering someone else's address has no route back; email is permanent | Phase 2 (accounts) |
| `OPEN-PAYDEMO-01` | reserved: product | a browser-reachable simulated payment failure; today only a hand-set `Idempotency-Key` prefix reaches it | Phase 4 |

## Closed by `SRC-004` since Article X was last written

| Row | Closed by | Effect on this architecture |
|---|---|---|
| `OPEN-PRDCLOSE-01` | `SRC-004 R-1` (waiver) | the PRD is the source to build from; its last guess-count reading (10) stays on the record |
| `OPEN-RESETTOKEN-01` | `SRC-004 R-3` | token in the queue message only; second short-retention queue; relay skips reset rows — `../for_llm/06` §6 |
| `OPEN-SEATLABEL-01` | `SRC-004 R-4` | `row_label = upper(btrim(input))`, database `CHECK`; the Phase 2 deadline is met if the migration carries it |
| `OPEN-SEATALPHA-01` | `SRC-004 R-4` | `I` permitted in row labels |
| `OPEN-REFCHAR-01` | `SRC-004 R-5` | 26-character alphabet, 7 random + 1 check character = 8 stored, displayed `FR-XXXX-XXXX`; the Phase 4 deadline is met if the first booking uses it |

## Questions this goal raised — decided by the build session under `SRC-004 R-6`

These used a `PROPOSED-` prefix so they could not be mistaken for filed Article X rows. Under
`SRC-004 R-6` build questions are decided in the build lane instead of being put to you, and each
decision is batched for you to reverse. All three below are recorded in `SRC-004` as `JC-R6-01..03`:
**closed by the build session, reversible by you**; one message from you reverses any of them.

| ID | Question | Decided | Rejected | Undo cost |
|---|---|---|---|---|
| `PROPOSED-ARCH-01` → `JC-R6-01` | A reset request whose queue send fails can never be retried, because under `SRC-004 R-3` the token is stored nowhere the system can re-read | **Not retried.** The customer sees the same 202 sentence and asks again (5 per hour per IP). The stricter option on secrets, so not a waiver | storing the token encrypted in the outbox under a key held in SSM — a credential back in the database, which R-3 exists to avoid | one relay change plus a managed key |
| `PROPOSED-ARCH-02` → `JC-R6-02` | Article X.0g reaches password reset in Phase 2 (`P-XCT-32`); reset needs the worker, a queue and SES, which the prep queue lists for Phase 5 | **Reset ships in Phase 5.** Phase 2 builds the reset tables only; SQS (row 9) and SES (row 10) stay at Phase 5 | bringing SQS, SES and the worker forward to Phase 2 | a phase reorder; nothing irreversible |
| `GOAL_11 Q-2` → `JC-R6-03` | Python's `str.upper` and PostgreSQL's `upper()` disagree on `ı` and `ß`, so the `row_label` CHECK of `SRC-004 R-4` could reject what Python normalised | **`row_label` is ASCII `A`–`Z` only**. The stricter choice | accepting any Unicode letter and normalising in one place only | one validation rule |

## Corrections requested of other lanes (not decisions)

1. **`SRC-004 R-5` needs an `ERRATUM`.** Its "Filed as" note says a weighted mod-N sum over the
   26-character alphabet catches every substitution and every adjacent swap. That is impossible for
   N = 26 (0 of 676 weight pairs, exhaustive). The adopted method is in `../for_llm/01`.
2. **`P-TKT-04` and `P-TKT-12`** say the reset token never travels in the queue; `SRC-004 R-3`
   reversed that. Their relay must filter `topic='receipt.send'`, and `S7.9` needs `RESET_QUEUE_URL`.
3. **`docs/06 DataModel/datamodel.json`** still records `OPEN-SEATLABEL-01` / `OPEN-SEATALPHA-01` as
   unruled and forbids the `row_label` CHECK that `SRC-004 R-4` now requires.

## Judgment calls this goal made — each reversible, each yours to reverse

| # | Call | Alternative | Undo cost |
|---|---|---|---|
| JC-1 | Two queues: `receipts` (long retention + DLQ) and `resets` (≤ 1800 s, no DLQ); new `RESET_QUEUE_URL` | one queue with short retention — loses receipts in any longer worker outage | one variable, one queue |
| JC-2 | No dead-letter queue on `resets` | a DLQ with the same short retention: evidence of failed resets, plus a second copy of a live token | one queue |
| JC-3 | Hold record key `hold:{hold_token}` | any other name | one constant |
| JC-4 | Check character: Verhoeff-type over dihedral group D13 | Damm over a quasigroup of order 26; a prime-modulus scheme cannot keep the check in the alphabet | one module, before Phase 4's first booking (after it: a one-way door) |
| JC-5 | *(superseded)* Reference length is `SRC-004 R-5`'s own judgment call: 7 random + 1 check = 8 stored characters, `FR-XXXX-XXXX` unchanged | 8 + 1 = 9, which would change the printed format (rejected in `R-5`) | before the first booking only |
| JC-6 | Browser and API on one origin; one listener rule for `/api/*` | CORS with credentials across two hostnames | one listener rule vs. a CORS config |
| JC-7 | api, worker and frontend as three ECS services | one task with three containers | Zone C reconfiguration |
| JC-8 | frontend container port 8080 | any port ≥ 1024 | one variable |
| JC-9 | `backend/app/jobs/` holds per-topic worker handlers | delete `jobs/`, put handlers in `workers/` | one move |
| JC-10 | Log redaction in the formatter by key name; AWS SDK loggers pinned at `WARNING` | redaction at call sites | none needed |
| JC-11 | Worker re-hashes the token and refuses to mail one that does not match its row | trust the message | one check |
| JC-12 | One-off migrate/seed task estimated at 150 MiB | any measured figure | replaced in Phase 1 |

## AWS dependencies this goal found — mapped to `docs/30 Deployment/AWS_PREP_QUEUE.md` rows

Each need this goal found, and the `AWS_PREP_QUEUE.md` row that now carries it. Where an existing row
covered only part of it, the missing part was added as a new row (29–31).

| # | Item | Needed by | Prep-queue row |
|---|---|---|---|
| A-1 | **A second SQS standard queue, `resets`**: retention ≤ `PASSWORD_RESET_TTL_SECONDS` (1800 s), visibility timeout < 900 s, **no DLQ**, server-side encryption on. Task role: send for the api, receive/delete for the worker | Phase 5, the phase that ships password reset (`JC-R6-02`) | **25** (retention, no DLQ, encryption, task role) · **31** (visibility timeout < 900 s, the part 25 lacked) |
| A-2 | Row 3 extended: **two target groups** (api on 8000 with health check `/health/ready`; frontend on 8080 with a static-file check) and a listener rule `/api/*` → api, default → frontend; **no rule for `/metrics`** | Phase 1 | **3** (api target group) · **30** (frontend target group and the `/api/*` rule, the part 3 lacked) · **28** (no `/metrics` route) |
| A-3 | **Shutdown ordering values**: ECS stop timeout > the 20 s drain (the deregistration delay runs before SIGTERM, `04_deployment.md` AWS-04-12); the stricter safe bound, stop timeout > deregistration delay + 20 s, means lowering the deregistration delay from its default | Phase 1 | **23** |
| A-4 | **An ECR lifecycle policy** per repository keeping a few recent images, to stay inside 500 MB | Phase 1 | **21** |
| A-5 | **Container hard memory limits** in each task definition: api 200, worker 150, frontend 15, migrate/seed 150 MiB — estimates, replaced by measurements | Phase 1 | **22** (api, frontend) · **29** (worker, migrate/seed, the part 22 lacked) |
| A-6 | **A one-off `migrate` task definition** connecting with the owner credentials (its own SSM parameter, read by the execution role), distinct from the app user in row 20 | Phase 1 | **24** |
| A-7 | *(withdrawn)* rows 9 (SQS) and 10 (SES) would have moved to Phase 2; `JC-R6-02` keeps them at Phase 5 | — | — |
