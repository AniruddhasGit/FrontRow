# `06 DataModel` — how a code session must use this package

> **`datamodel.json` is the spec of record. `schema.sql` and `TRACEABILITY.tsv` are generated from
> it and must never be hand-edited.** `py generate.py --check` re-derives both and exits 1 on any
> difference, so an edit is caught rather than absorbed.

## State — read this first

**This package is COMPLETE ENOUGH TO BUILD AGAINST and is NOT finished.** What is proved is listed
below with the evidence. What is missing is listed after it, honestly. Nothing here should be read
as a closed document.

### Proved, by running it

| Claim | Evidence |
|---|---|
| `schema.sql` applies to an empty PostgreSQL 16 database **as `frontrow_owner`**, not a superuser | exit 0, zero errors: 22 tables, 19 `CREATE INDEX`, 24 `GRANT`, on PostgreSQL 16.15 (`checks/RUN_LOG.md`, fix wave 2026-10-18) |
| `checks/verify_invariants.sql` passes **as `frontrow_app`**, logged in with a scram-sha-256 password | **37 PASS, 0 FAIL**; it reads `pg_catalog`, so a table the app cannot see cannot pass vacuously |
| The app role holds exactly the least-privilege matrix | `roles_local.sql` §3 = `datamodel.json` `roles[].grants`; A3 fails on a missing grant, A4 on an excess one |
| `generate.py --check` produces no diff | PASS; `--selftest` **12 of 12** |
| `consistency_check.py` | **15 rules, 15 pass** |
| Every rule has been watched failing | `--selftest`: **26 of 26 went red**, then restored |
| **The seat guarantee** | the four-stage drill below (2026-08-23), re-run against the applied schema on 2026-10-18 in `checks/RUN_LOG.md` |
| The SRC-004 CHECKs refuse what they must | as `frontrow_app`: lower-case and padded `row_label` and four bad references refused by the CHECKs; `I` and a valid 8-character reference accepted |

### The concurrency drill, run 2026-08-23 against the applied schema

```
STAGE 1  guard in place, two customers one seat   -> second INSERT refused
         ERROR: duplicate key value violates unique constraint
                "uq_booking_seat__showtime_id_seat_id"
         DETAIL: Key (showtime_id, seat_id)=(1, 1) already exists.
         winners = 1
STAGE 2  constraint DROPPED on purpose            -> the same INSERT succeeded
         winners = 2          <- the oversell, watched happening
STAGE 3  oversold row deleted, constraint restored
STAGE 4  the same INSERT refused again            -> winners = 1
         pg_get_constraintdef -> UNIQUE (showtime_id, seat_id)      (TOTAL, no WHERE)
```

**This is the database half of the guarantee and it may not be waived.** Redis provides the hold;
this provides the truth. The application half — the Redis lock and the 50-request stress script —
is Phase 4 and does not exist yet, so the *product's* promise is not yet proved end to end.

## The rules a code session may not break

1. **Never hand-edit `schema.sql` or `TRACEABILITY.tsv`.** Change `datamodel.json` and regenerate.
2. **Never widen the seat guarantee.** `uq_booking_seat__showtime_id_seat_id` is TOTAL. Making it
   partial — `WHERE cancelled_at IS NULL` is the tempting one — frees the pair for every excluded
   row and is an oversell by design. `consistency_check.py` fails on exactly that, and the failure
   has been watched.
3. **`showtime_seat` carries the same column pair and is NOT the guard.** `P-ADM-14`: *"That unique
   index is not the oversell guard, and nothing may treat it as one. Two tables, two constraints,
   two different jobs."* It is declared in `non_guard_seat_pairs` so nobody has to guess.
4. **Money is `bigint` in the minor unit.** Never a float, never `NUMERIC(x,2)` — a driver hands
   that back as a `Decimal` and one careless layer makes it a float. The ratio (100) is
   configuration and appears in no column name, comment or constraint.
5. **Primary keys are `bigint GENERATED ALWAYS AS IDENTITY`** (`FR-ADR-017`), which also refuses an
   application-supplied value. No internal id appears in a public URL — that is what
   `booking.reference` is for.
6. **`created_at` / `updated_at` default to `now()` at the database; nothing else does**
   (`FR-ADR-018`). A decision-bearing instant with a database default is unreachable by an injected
   clock, so a test that moves time cannot move it.
7. **Every foreign key is `ON DELETE RESTRICT`.** `S-XCT-09` asserts zero exceptions.
8. **The ORM mirrors this schema; it never defines it.** If SQLAlchemy models and `schema.sql`
   disagree, `schema.sql` wins and the model is the defect.
9. **Migrations never run on boot** (`SRC-002 §7.8`).

## Two database roles, and why it is not a style choice

`frontrow_owner` owns every table and runs migrations. `frontrow_app` is what the application
connects as — never a superuser, never the owner.

**This is forced by a test, and the forcing was observed, not reasoned.** `S-XCT-07` asserts that
`information_schema.table_privileges` for `audit_log` and `current_user` returns **exactly two**
rows. On PostgreSQL 16.14 a table's *owner* sees **seven** — `DELETE, INSERT, REFERENCES, SELECT,
TRIGGER, TRUNCATE, UPDATE` — so a single-role design cannot satisfy that criterion at all. With a
separate owner, the same query returns exactly `INSERT` and `SELECT`.

`audit_log` is append-only **because the UPDATE and DELETE grants do not exist**, not by convention
(`FR-ADR-019`).

> **No source document contains a single `CREATE ROLE`, `GRANT` or `REVOKE`.** The role
> names here are a `[JUDGMENT CALL]` and are reversible.
>
> **`schema.sql` creates no role** (fix wave 2026-10-18). Roles belong to the operator: run
> `checks/roles_local.sql` as a superuser locally; the client creates them on RDS. Then apply
> `schema.sql` **as `frontrow_owner`**. If a role is absent its `GRANT`s fail and the whole file
> rolls back. The grants are the least-privilege matrix of `roles_local.sql` §3, 63 table
> privileges: no `UPDATE` or `DELETE` on `booking` / `booking_seat`, no `DELETE` on `payment` or
> `users`. The *two-role split* is not a judgment
> call — it is the only design that passes `S-XCT-07`.

**AWS consequence, owed as advance notice:** RDS needs two database users, not one. This is in
`docs/30 Deployment/AWS_PREP_QUEUE.md`.

## Reserved questions — four ruled by `SRC-004`, two still open

`SRC-004` (2026-10-18) rules four of the rows this schema was carrying. A ruled row may appear as a
constraint **only as the exact constraint its ruling files, citing that ruling**.
`consistency_check.py` `reserved-not-decided` fails on any other constraint on the same subject,
and on a missing ruled one. The two unruled rows are still modelled and **not** answered.

| Row | Status | What the schema does | What it must not do |
|---|---|---|---|
| `OPEN-RESETTOKEN-01` *(secrets)* | **RULED, `SRC-004 R-3`** | `token_sha256` only. The plaintext rides in the queue message only; `ck_outbox_message__payload_keys_exact` keeps it out of the outbox payload | no plaintext token column anywhere, and no payload key that could hold one (`verify_invariants` O2, O5). The relay cannot copy the token from an outbox row, so the reset path must put it on the queue by a route that touches no table. That is a consequence for the code lane |
| `OPEN-REFCHAR-01` *(irreversible)* | **RULED, `SRC-004 R-5`** | `booking.reference` UNIQUE + `ck_booking__reference_charset` = `^[23456789ACDEFHJKMNPQRTVWXY]{8}$`: `OPEN-TICKET-01`'s alphabet minus `Z S B G`, 7 random characters + 1 check character = 8, display `FR-XXXX-XXXX` unchanged | the CHECK cannot verify the check character's arithmetic; that algorithm is a code-lane `[JUDGMENT CALL]` (`SRC-004 R-5`). `P-TKT-01` and the Bible state the same alphabet and length |
| `OPEN-SEATLABEL-01` *(irreversible)* | **RULED, `SRC-004 R-4`** | `ck_seat__row_label_upper` = `row_label = upper(btrim(row_label))`. It refuses, never rewrites; the app normalises | no `citext`, no expression index. Every stored label is already normalised, so the raw unique constraint is the case-insensitive guard |
| `OPEN-SEATALPHA-01` *(irreversible)* | **RULED, `SRC-004 R-4`: `I` allowed** | nothing | **no CHECK bans any letter** (`verify_invariants` O4). The seed's skip of `I` binds only the seed |
| `OPEN-DUPREF-01` *(product)* | open | nothing | no redemption / admitted / scanned column |
| `OPEN-HOLDRECOVER-01` *(scope)* | open | nothing | **no holds table.** A live hold is Redis-only; a table would put the guarantee in two places |

## The seed expectations and the fingerprints — two more generated files

Both are written by `generate.py`, both carry a `_GENERATED` banner as their first key, and
`--check` fails on any byte of drift in either. **Never hand-edit them.**

### `seed/expected_summary.json` — what a correct seed must produce

**Expectations, never seed data.** Nothing in it is a row to insert; `scripts/seed.py` belongs to a
code goal. The inputs live in `datamodel.json` → `seed_expectations`, each one transcribed from
`P-XCT-30` / `P-XCT-32` / `S-XCT-44` / `S-XCT-45` and labelled with its status.

- **`generate.py` runs the seed's arithmetic, not a copy of its numbers.** It re-derives every count
  the PRD publishes — 720 showtimes, 960 seats, 115,200 `showtime_seat` rows, 58,800 booked seats,
  11,003 bookings, 220–221 per customer, 51.04% occupancy, the three FR-ADR-038 prices — and
  **refuses to emit if a published figure disagrees with its own rule.**
- **One published figure does disagree, and it is recorded, not adjusted.** `P-XCT-30`'s occupancy
  worked example puts `k = 399` on Screen 5 (80 seats booked). Under the row's own
  `(day, slot, screen)` ordering — the one its `k = 231` example confirms — `k = 399` is Screen 4,
  72 seats. It sits in `seed_expectations.known_disagreements`; if it is ever fixed, `generate.py`
  fails until the record is removed, so the record cannot go stale.
- **`rows: null` means no document states the figure** (`idempotency_record`,
  `password_reset_token`, the `outbox_message` total). A gap stays a gap; it is not an inferred 0.
- **`ASSUMED` inputs never harden.** Hall sizes (`OPEN-SCALE-02`), category names and uplifts
  (`OPEN-SEAT-01`), the lookup vocabulary and the schedule are demonstration inputs.
  `consistency_check.py`'s `seed-expectations` rule fails if one is relabelled as ruled; if a seeded
  name, row-letter string, base price or uplift appears in any `CHECK` or `DEFAULT`; or if a hall
  size or grid dimension appears in a `CHECK` or `DEFAULT` on `screen`, `seat`, `showtime` or
  `showtime_seat`. Hall numbers are checked on those four tables only, because bare numbers
  collide with unrelated constraints elsewhere (the `{8}` in the reference CHECK, `BETWEEN 1 AND 60`).
- **Use it as a test oracle.** A seed test reads the row counts and `invariants` from this file and
  asserts them against a freshly seeded database. It must not copy the numbers into the test.

### `fingerprints.json` — drift detectors for the ORM

- `files` — SHA-256 of `datamodel.json`, `schema.sql`, `TRACEABILITY.tsv` and
  `seed/expected_summary.json` (UTF-8, CRLF normalised to LF). `fingerprints.json` is excluded from
  hashing itself.
- `tables.<name>.signature` — the sorted column / type / nullability / default / identity /
  constraint / index lines for that table, in the PostgreSQL spellings `schema.sql` uses.
  `tables.<name>.sha256` is over `table <name>` followed by those lines, joined by LF.
- **Prose is not drift.** Citations and notes are excluded, so rewording a citation moves no table
  fingerprint, and a type change moves exactly one. `generate.py --selftest` proves both.
- **How a code session uses it:** a test builds the same signature lines from the SQLAlchemy
  metadata (or from `information_schema` on a migrated database) and compares them with
  `tables.<name>.signature`. A mismatch means the ORM or a migration drifted from the schema of
  record; `schema.sql` wins (rule 8).
- **Any edit to `datamodel.json` changes its digest.** Run `py generate.py` after every model edit,
  or `--check` fails on `fingerprints.json` — on purpose.

## What is NOT done — the next session's list

1. **`seed/expected_summary.json` has never been checked against a real seed run**, because no seed
   script exists yet. Six seed gaps no document answers stay in `seed_expectations.unspecified`,
   among them what the seed writes into the `NOT NULL` `payment.idempotency_key`, and the seeded
   `booking.created_at` for past showtimes.
2. **`P-TKT-01` and the Bible still describe the pre-`SRC-004` reference** (8 characters over 30).
   The schema follows `SRC-004 R-5` (9 over 26). Any criterion asserting `length(reference) = 8`
   now fails against a correct schema until the PRD and the Bible are updated.
3. **66 gaps and 107 notes** from the six cluster reads are preserved verbatim in `derivation/` and
   have not all been triaged. Several are real questions. `derivation/MERGE_DECISIONS.md` records
   the eight decisions the merge rests on and the cross-document defects found.
4. **`FR-ADR-032` vs `P-TKT-04/05` is unresolved**: the ADR says the *worker* inserts the
   `receipt_dispatch` row, the PRD says the booking transaction does and *"the worker never inserts
   it"*. Same columns either way, so the schema is unaffected — but three criteria test the PRD's
   reading and Art II.1 ranks the ADR higher. **Recorded, not decided.**
5. **`showtime_seat` carries a PRIMARY KEY and an identical UNIQUE constraint on
   `(showtime_id, seat_id)`.** Both are constraints, so the fix wave's de-duplication kept both:
   `S-ADM-08` asserts the named unique exists, and the primary key is the table's identity.
6. **RDS is not observed.** Everything said here about the two roles on RDS is reasoned, not
   observed.

**Closed by the 2026-10-18 fix wave:** `checks/verify_invariants.sql` exists and passes as
`frontrow_app`; the ledger's `included_in_datamodel` column is derived and checked
(`ledger-datamodel`); the application role has logged in with a real password; the grants are
least-privilege; the duplicate `ix_` unique indexes are gone; and
`booking_seat.uplift_basis_points_applied` is `bigint`, like the `seat_category.uplift_basis_points`
it copies. `uplift_basis_points` is `bigint` on purpose: `S-ADM-13` asserts `368934881464190` is
accepted, which overflows `integer`.

## Provenance

`derivation/` holds the six independent cluster reads this model was assembled from — 22 tables,
152 columns, every one citing a PRD row, an ADR or a Bible story. They are kept because they carry
the reasoning and the verbatim SQL behind each column, and re-deriving them costs six full agent
runs.
