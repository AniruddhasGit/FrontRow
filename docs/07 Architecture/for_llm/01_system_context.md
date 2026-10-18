# 01 — System context

> **compressed per SRC-004 R-1.** For a code session starting cold. Read this, then `03`, then the
> file for the flow you are building. Authority on conflict: `SRC-001` → `SRC-002` → a client ruling
> (`SRC-003`, `SRC-004`) → an `APPROVED` ADR → PRD → everything else, stricter wins
> (`CONSTITUTION.md` Art II.1). **This folder is below the PRD.** If it disagrees with
> `docs/03 PRD/`, the PRD wins and this folder has a defect.

## What the system is

One theatre (`cinema` row, kept in the schema per `FR-ADR-010`) with six halls (`screen`). A guest
browses published movies, showtimes and a live seat map. A signed-in account holds up to ten seats
for 180 seconds, pays through a **simulated** provider, and gets a booking reference on screen and by
email. An admin creates every movie by hand. A manager reads a dashboard scoped to the halls assigned
to them. **A seat is never sold twice** (`SRC-001 §2.2`, `FR-ADR-024`).

## Actors

| Actor | Account | Reaches | Ruling |
|---|---|---|---|
| guest | none | browse, showtimes, seat map; **stopped at the hold** | `FR-ADR-009`, `FR-ADR-046` · `PROVISIONAL` (`SRC-003 C-1`) |
| customer | `users.role = 'customer'` | holds, confirm, own bookings, resend, password reset | same |
| manager | `users.role = 'manager'` | **read-only** reports for `manager_screen_assignment` halls. The contract also admits a manager to hold and confirm; whether that is right is `OPEN-MGRBOOK-01` | same |
| admin | `users.role = 'admin'` | every write in the product, every report, the audit log | `SRC-003 OPEN-OPS-03` |
| door staff | **no account, no software** | reads a reference aloud and compares it by hand | `P-TKT-08`; how they verify it is `OPEN-DOORVERIFY-01` |

`guest` is not a stored role — it is the absence of a session. The `users.role` CHECK holds three
values.

## External systems

| System | Local (docker-compose, `FR-ADR-066`) | Deployed | Used by | If it is gone |
|---|---|---|---|---|
| PostgreSQL 16 | container | RDS `db.t3.micro` | api, worker, migrate, seed | `08` row P |
| Redis | container | ElastiCache `cache.t3.micro`, one node | api (locks, cache, rate limit, instance registry); worker (lock-count reconcile scan) | `08` row R |
| Queue | ElasticMQ container | SQS standard queue(s) | api (send), worker (receive/delete) | `08` row Q |
| Mail | `MAIL_PROVIDER=stub` writes to stdout | SES (`SRC-003 OPEN-EMAIL-01`) | worker only | `08` row S — **read first** |
| Object storage | real S3 with your own credentials, or none (`FR-ADR-061`) | S3 private bucket | api (poster upload, presigned redirect) | `08` row O |
| Secrets | `.env` file, never committed | SSM Parameter Store, injected by the task definition (`FR-ADR-054`) | every process at boot | the process refuses to start |
| Logs | stdout | stdout → `awslogs` → CloudWatch Logs | every process | nothing is recorded |

## What does not exist — do not build it, do not design around its absence

- **No external movie API.** TMDB is withdrawn in full (`SRC-003 OPEN-TMDB-01`, `FR-ADR-006`).
- **Nothing runs on a schedule** (`SRC-003 OPEN-PROC-01`, `P-XCT-22`). No cron, no EventBridge, no
  periodic task in a process. Work that would have been a timer runs on the worker's existing receive
  loop (`FR-ADR-031`).
- **No real payment provider, ever** (`SRC-003 OPEN-PAY-01`). `PAYMENT_PROVIDER=simulated` is the
  only accepted value (`FR-ADR-041`).
- **No QR code, no scanner, no validation endpoint, no cancellation, no refund, no CSV export**
  (`SRC-003`). The schema keeps `booking.status` and `booking.cancelled_at` so excluded is not
  blocked (`FR-ADR-013`).
- **No card data anywhere** — no column, no log field, no fixture (`P-PAY-08`).

## Rulings received 2026-10-18 that change code (`SRC-004`)

| Ruling | What the code must do | Where it lands |
|---|---|---|
| `SRC-004 R-3` · `OPEN-RESETTOKEN-01` | The plaintext reset token travels **in the queue message body only**. PostgreSQL holds only `token_sha256`. No column — **including `outbox_message.payload`** — ever holds the plaintext. The logger redacts it. Queue retention for it is short. | `06` §Password reset, `02` §Logging |
| `SRC-004 R-4` · `OPEN-SEATLABEL-01` | `seat.row_label` is stored as `upper(btrim(input))` and the database enforces it with `CHECK (row_label = upper(btrim(row_label)))`, so `C12` and `c12` cannot both exist | `domain/venue`, the Phase 2 migration |
| `SRC-004 JC-R6-03` | `row_label` is **ASCII `A`–`Z` only**. Python's `str.upper` and PostgreSQL's `upper()` disagree on `ı` and `ß`; restricting the input to ASCII makes them agree. The R-4 `CHECK` does **not** enforce it (it passes any character that is its own upper case, e.g. Cyrillic `С`), so the API's validation is the guard | `domain/venue` validation (Phase 2); no database guard (`docs/09 NegativeTesting` F-7) |
| `SRC-004 R-4` · `OPEN-SEATALPHA-01` | The letter `I` is a permitted row label. The seed's habit of skipping it binds nothing | `domain/venue` validation |
| `SRC-004 R-5` · `OPEN-REFCHAR-01` | Reference alphabet is `SRC-003 OPEN-TICKET-01`'s 30 characters **minus `Z S B G`** → 26 characters `23456789ACDEFHJKMNPQRTVWXY`, plus **one trailing check character** from the same alphabet | `domain/reference`, see below |
| `SRC-004 R-1` | `OPEN-PRDCLOSE-01` and `GOAL_07`'s gate waived; `GOAL_09`–`13` compressed. **Not waived:** test-first DoD, the 50-request proof and its red-proof, every invariant | process only |

**The reference under `R-5`.** Seven random characters from the 26-character set, then one check
character: **8 stored characters**, displayed `FR-XXXX-XXXX` exactly as before. The random space is
`26^7 = 8,031,810,176` (computed, not estimated). The length is `SRC-004 R-5`'s own `[JUDGMENT CALL]`
("the length stays 8"); the rejected reading, 8 random + 1 check = 9, would have changed the printed
format read at the door. `P-TKT-01`'s length-8 validation and the datamodel's column constraint stand
unchanged.

**The check algorithm — `[JUDGMENT CALL]`, and a correction to `SRC-004`'s filed note.** `SRC-004 R-5`'s
"Filed as" text (the build session's words, not the client's) names "a weighted mod-N over the
alphabet's index, which catches every single-character substitution and every adjacent transposition".
**With N = 26 no weighted sum can do both.** Catching every substitution needs every weight to be a
unit mod 26 (odd, not 13); then two adjacent weights differ by an even number, and swapping two
characters whose indices differ by 13 changes the sum by `13 × even ≡ 0 (mod 26)` — undetected. An
exhaustive search in scratch found **0 of 676** weight pairs that catch both classes.
**Adopted instead:** a Verhoeff-type check over the dihedral group D13 (26 elements, so one element
per alphabet character), with the anti-symmetric map `σ(r^k) = r^(−k)`, `σ(r^k·s) = r^(k+1)·s` found
by search. Checked in scratch over 3,000 random 8-character references: **0 of 600,000** single
substitutions and **0 of 20,212** adjacent transpositions went undetected; an exhaustive check of every
ordered pair of distinct characters at each of the 7 adjacent position pairs found **0 of 4,550**
undetected. The code owns the final implementation and
must carry an exhaustive test of both classes. The filed note in `SRC-004` needs an `ERRATUM` (the
file permits only that) — requested of the governance lane, not done here.

**Where a check character helps and where it does not.** It is verified only where software reads a
typed reference: `EP-TKT-01`, `EP-ACC-08`, `EP-TKT-02`. A reference that fails the check is rejected
as not-a-reference before any database read. **At the door there is no software** (`P-TKT-08`), so
there it detects nothing unless a person computes it. Recorded in `for_humans/03`.

## The invariants, and the one place each is enforced

| Invariant | Enforced by | Record |
|---|---|---|
| A seat is never sold twice | `UNIQUE (showtime_id, seat_id)` on `booking_seat`, total, no partial predicate; Redis lock is the hold only | `FR-ADR-024`, `03` |
| Locks atomic, tokened, self-expiring | `SET NX PX` one command; Lua compare-and-delete | `FR-ADR-025` |
| Redis down → error, never DB locking | `domain/locking` raises `DependencyUnavailable`; `/health/ready` 503 | `FR-ADR-028` |
| Integer paise, ratio 100 named | one money module in `domain/pricing`; `CURRENCY_MINOR_UNIT_RATIO` | `FR-ADR-036`, `FR-ADR-038` |
| Hold 180 s from config, cap 10 server-side | `SEAT_HOLD_TTL_SECONDS`, `MAX_SEATS_PER_BOOKING`, checked at hold | `FR-ADR-026`, `FR-ADR-027` |
| `Idempotency-Key` on confirm | `idempotency_record` inserted first in the transaction, never expired | `FR-ADR-020`, `P-PAY-09` |
| Authorisation once, on the router | FastAPI router-level `dependencies=[...]`; no handler checks a role | `P-XCT-05` |
| Manager sees only own halls | one scope dependency resolving `manager_screen_assignment`; every report query takes the resolved set | `FR-ADR-011` |
| Audit row in the same transaction | `domain/audit.write()` takes the open session; never commits | `FR-ADR-019` |
| Stateless containers | no disk writes; uploads streamed to S3; registry of holds in Redis | `P-XCT-18` |
| Migrations never on boot | `migrate` is a separate entrypoint and a separate one-off task | `FR-ADR-062` |
| live ≠ ready | `/health/live` touches nothing; `/health/ready` checks PostgreSQL and Redis only | `FR-ADR-055` |
| JSON logs to stdout, request id into jobs | `core/logging`; `request_id` in every queue payload | `FR-ADR-056` |
| No wall clock in tests | a `Clock` dependency injected everywhere a time is read | Art IX.5 |

## Status words

`RULED` decided with a citation · `PROVISIONAL` written down, ruling outstanding · `OPEN` unruled —
**escalate, never invent** · `ASSUMED` inference that never hardens. Three `ASSUMED` rulings matter to
code: `OPEN-SCALE-02` hall sizes, `OPEN-SCALE-03` peak concurrency, `OPEN-SEAT-01` category names.
