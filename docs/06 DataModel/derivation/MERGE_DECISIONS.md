# GOAL_08 merge — decisions, with the evidence for each

Five cluster readers returned independently. Where they agreed, the agreement is recorded once.
Where they disagreed, or where a reader found a document contradicting another document, the
decision and its authority are written here BEFORE datamodel.json is assembled — so that the model
is the consequence of a decision rather than the place one gets made silently.

## D1 — Primary keys are `bigint GENERATED ALWAYS AS IDENTITY`, not uuid

**My brief was wrong and all five readers overrode it.** `FR-ADR-017` (APPROVED, ADOPTED):
*"Primary keys are `bigint` identity columns, and no internal id appears in a public URL."* Its own
file rejects UUIDv4/v7/ULID by name and gives the deciding reason: *"two 8-byte integers make a
16-byte key; two UUIDs make a 32-byte key on the single most contended index in the system"* — that
index being `(showtime_id, seat_id)`, the product's central promise.

`IDENTITY` over `serial` is deliberate in the same ADR. Every id in every criterion is a small
integer (`showtime 41`, `movie 11`), and `GET /api/movies/abc` returns 422.

**Consequence for `FR-ADR-017`'s second half**: private objects are never *addressed* by the
sequential key. That is why `booking.reference` exists and why no booking id appears in a URL.

**A PRD inconsistency this exposes, not fixed here:** `P-ACC-09` spells `booking.user_id integer`.
`integer` and `bigint` are different types and a foreign key must match its target. The ADR outranks
the PRD (Art II.1), so the model is `bigint` throughout and the PRD's `integer` spellings are filed.

## D2 — The seat guarantee: `booking_seat`, TOTAL, no `WHERE`

Five sources agree: `FR-ADR-024`, `P-PAY-11`, and `S-XCT-02/03/04`, which read `pg_get_constraintdef`
back and require no `WHERE`; `S-PAY-09` requires *exactly one* unique index on the table.

**A cancelled booking's seats are NOT freed, and that is the ruled answer.** Both records carry the
same revisit trigger: *"If cancellation is ever added, this constraint has to be revisited first."*

**`showtime_seat` carries the same column pair and is NOT the guard.** `P-ADM-14`: *"That unique
index is not the oversell guard, and nothing may treat it as one… Two tables, two constraints, two
different jobs."* This invalidated my first consistency rule, which failed whenever two relations
carried the pair — it would have gone red against a correct schema. The rule now checks WHICH
relation guards and requires every other carrier to be declared with its job.

## D3 — Every foreign key is `ON DELETE RESTRICT`

`S-XCT-09` asserts `pg_constraint WHERE contype='f' AND confdeltype <> 'r'` returns **zero rows**,
and `P-XCT-04` states it as a precondition. Not a preference: a test that will be run. Encoded as a
rule so a later cascade cannot be added quietly.

## D4 — No column takes a default from the database clock

`FR-ADR-018` plus Art IX.5 (time is injected; a test reading the wall clock is a defect). Two readers
reached this from opposite directions: `S-ACC-07` needs `expires_at = created_at + 1800` on the
**injected** clock, and `S-TKT-07` sweeps the worker for `now()` requiring zero hits. A `DEFAULT
now()` is read inside the database where no harness can move it. Encoded as a rule.

## D5 — `audit_log` is the one table without `created_at` — [JUDGMENT CALL]

The conflict: `P-XCT-04` (RULED) says *"Every table carries `created_at`"*, and `S-XCT-09` sweeps
`information_schema` for it across all of `public`. But `S7.3` **enumerates `audit_log`'s ten
columns** and `created_at` is not among them; its instant is `occurred_at`.

**Decision: `audit_log` keeps `occurred_at` alone, and `S-XCT-09` gains a named exemption.** The
specific declaring table beats the general precondition. Adding a `created_at` that always equals
`occurred_at` — the row is inserted in the same transaction as the event it records — creates two
columns that must agree forever, and columns that must agree forever eventually do not.

Every other table, lookups included, carries `created_at` per `P-XCT-04`.

**This is a build-session technical call, logged as one. It is reversible** — adding the column later
costs a migration and nothing else.

## D6 — Tables beyond the fifteen

The fifteen came from harvesting `table.column` references out of the Bible, which can only see
tables written that way. Readers found more, each required by a document:

- `seat_category` — a LOOKUP TABLE, not an enum. `FR-ADR-016` rejects a PostgreSQL enum by name;
  `P-ADM-11` repeats it. `seat.seat_category_id` is a NOT NULL foreign key, so `seat` cannot exist
  without it. Category names remain `ASSUMED` (`OPEN-SEAT-01`) — a lookup row is exactly the right
  home for an assumed value, because changing one is an UPDATE rather than a migration.
- `manager_screen_assignment` — `FR-ADR-011`, `P-ADM-17`, and four Bible stories. `UNIQUE
  (user_id, screen_id)`, asserted by name in `information_schema` by `S-ADM-18`.
- `movie_genre` — the catalogue reader's join table.
- `certification`, `language`, `genre`, `format` — lookup vocabularies the catalogue FKs point at.

## D7 — Reserved rows: modelled, never decided

- `OPEN-RESETTOKEN-01` (secrets) — `token_sha256` only. No plaintext column, none proposed, and no
  payload column shaped to carry one. The flow stays unbuildable until the client rules.
- `OPEN-REFCHAR-01` (irreversible, Phase 4) — `booking.reference` is modelled and UNIQUE. **No CHECK
  on the alphabet.**
- `OPEN-SEATLABEL-01` + `OPEN-SEATALPHA-01` (irreversible, Phase 2) — `seat.row_label` is modelled
  raw. No `citext`, no `lower()`/`upper()` index, no CHECK. The unique index is on RAW columns, which
  deliberately contradicts every other unique name in the product (all `lower(trim(name))`).
- `OPEN-DUPREF-01` (product) — no redemption column. `S-TKT-12` asserts
  `used_at|admitted_at|scanned_at|checked_in_at|entry_at` all return zero.
- `OPEN-HOLDRECOVER-01` (scope) — no holds table. `S-PAY-08` asserts
  `seat_hold|hold|seat_lock|lock` returns zero.

## D8 — `payment.idempotency_key` is NOT unique

`S-PAY-15` leaves two `failed` payment rows sharing one key. A unique constraint there breaks the
fail-retry-succeed drill. Noted because it is the opposite of the `idempotency_record` rule and the
two are easy to conflate.

---

# Cross-document defects found, and where each must be fixed

**Not fixed in the schema.** Each is a defect in another document that the schema exposed. Fixing
them in the model would encode the defect instead of the requirement.

| # | Defect | Fix belongs in | Verified |
|---|---|---|---|
| 1 | `S-ACC-03` queries `audit_log WHERE user_id` — no such column; the PRD says `actor_user_id` 32 times and `user_id` never. Raises `UndefinedColumn` rather than returning 0. | Bible | yes, by me |
| 2 | `S-SCP-04` sweeps `table_name='user'` (singular) against a table named `users`. Matches nothing and **passes vacuously** — a silent test. | Bible | yes, by me |
| 3 | `S-XCT-34`, `S-XCT-44` query `seat.label`. `FR-ADR-016` rejects a single label string by name; every other criterion uses `row_label` + `seat_number`. | Bible | reader |
| 4 | `S-XCT-42`, `S-XCT-44` query `movie.poster_key`. PRD, `FR-ADR-021`, `FR-ADR-061`, `contract.json`, `S-ADM-25` and `S-ADM-29` all say `poster_object_key`. | Bible | reader |
| 5 | `S-XCT-32`, `S-XCT-45` join `payment p ON p.booking_id = b.id`. `S-PAY-05` and `S-SCP-12` assert that column must not exist. `S-XCT-45` also says `p.status` where the column is `p.state`. | Bible | reader |
| 6 | `S-XCT-09` requires `created_at` on every table in `public`; `audit_log` has `occurred_at` by enumeration. | Bible (exemption) — see D5 | yes, by me |
| 7 | `FR-ADR-032` says the WORKER inserts the `receipt_dispatch` row; `P-TKT-04`/`P-TKT-05` say the booking transaction does and *"the worker never inserts it"*. Same columns either way, so the schema is unaffected — but the readings differ and three criteria test the PRD's. | escalate / record | reader |
| 8 | `P-ACC-09` spells `booking.user_id integer` against `FR-ADR-017`'s `bigint`. | PRD | yes, by me |

**`S-BRW-11`'s `screen.rows` / `screen.cols` are NOT a defect** — they are JSON response fields, not
columns. `screen` has no `rows`/`cols` column; the grid extent is derived per response. They go in
`bible_reference_exceptions` so the reference rule does not report them.
