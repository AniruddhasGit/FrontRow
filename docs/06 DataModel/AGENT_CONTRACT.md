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
| `schema.sql` applies to an empty PostgreSQL 16 database | exit 0, 75 objects, zero errors, on PostgreSQL 16.14 |
| `generate.py --check` produces no diff | PASS |
| `consistency_check.py` | **13 rules, 13 pass** |
| Every rule has been watched failing | `--selftest`: **14 of 14 went red**, then restored |
| **The seat guarantee** | the four-stage drill was run and all four stages are recorded below |

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

> **No document in the repository contains a single `CREATE ROLE`, `GRANT` or `REVOKE`.** The role
> names here are a `[JUDGMENT CALL]` and are reversible. The *two-role split* is not a judgment
> call — it is the only design that passes `S-XCT-07`.

**AWS consequence, owed as advance notice:** RDS needs two database users, not one. This is in
`docs/30 Deployment/AWS_PREP_QUEUE.md`.

## Reserved questions this schema models but does not answer

Each is modelled as a column and cited. **None is expressed as a constraint**, because a constraint
would decide it. `consistency_check.py` fails if one appears.

| Row | What the schema does | What it must not do |
|---|---|---|
| `OPEN-RESETTOKEN-01` *(secrets)* | `token_sha256` only | no plaintext token column, and no payload column shaped to carry one. **The reset flow is unbuildable as specified** — three PRD passages are jointly unsatisfiable — and it stays that way until the client rules |
| `OPEN-REFCHAR-01` *(irreversible, Phase 4)* | `booking.reference`, UNIQUE | **no CHECK on the alphabet**, no check character |
| `OPEN-SEATLABEL-01` + `OPEN-SEATALPHA-01` *(irreversible, Phase 2)* | `seat.row_label`, raw | no `citext`, no `lower()`/`upper()` index, no CHECK. Its unique index is on **raw** columns, deliberately unlike every other name in the product |
| `OPEN-DUPREF-01` *(product)* | nothing | no redemption / admitted / scanned column |
| `OPEN-HOLDRECOVER-01` *(scope)* | nothing | **no holds table.** A live hold is Redis-only; a table would put the guarantee in two places |

## What is NOT done — the next session's list

1. **`checks/verify_invariants.sql` is not written.** The invariants are proved today by the drill
   above and by `consistency_check.py`, not by a runnable SQL file. **This is a DoD line that is
   not met.**
2. **`seed/expected_summary.json` and `fingerprints.json` are not written.** DoD lines, not met.
3. **The ADR ledger's `included_in_datamodel` column is not flipped.** DoD line, not met.
4. **The schema has been applied only as a superuser.** The `GRANT`s are emitted and applied, but
   the application has never connected *as* `frontrow_app`, so a missing grant would not yet have
   been noticed. The guardrail says build against the restricted role from the first line; that is
   half done.
5. **66 gaps and 107 notes** from the six cluster reads are preserved verbatim in `derivation/` and
   have not all been triaged. Several are real questions. `derivation/MERGE_DECISIONS.md` records
   the eight decisions the merge rests on and the cross-document defects found.
6. **`FR-ADR-032` vs `P-TKT-04/05` is unresolved**: the ADR says the *worker* inserts the
   `receipt_dispatch` row, the PRD says the booking transaction does and *"the worker never inserts
   it"*. Same columns either way, so the schema is unaffected — but three criteria test the PRD's
   reading and Art II.1 ranks the ADR higher. **Recorded, not decided.**
7. **`uplift_basis_points` is `bigint` on purpose.** `S-ADM-13` asserts the value
   `368934881464190` is *accepted*; that overflows `integer`. Built narrower, the criterion dies on
   numeric overflow instead of returning its specified 201/422 split.

## Provenance

`derivation/` holds the six independent cluster reads this model was assembled from — 22 tables,
152 columns, every one citing a PRD row, an ADR or a Bible story. They are kept because they carry
the reasoning and the verbatim SQL behind each column, and re-deriving them costs six full agent
runs.
