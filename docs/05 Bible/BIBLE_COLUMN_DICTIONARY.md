# `FrontRow_Bible.csv` — column dictionary

```
Produced by ....... GOAL_07 (goals/GOAL_07_bible.txt)
Written ........... 2026-08-22
Derived from ...... docs/03 PRD/sections/ · docs/11 Journeys/ · docs/01 ADR/
                    SRC-001 + §E · SRC-002 + §E · SRC-003
Authority ......... CONSTITUTION.md Art II.1. The Bible never outranks the PRD. Where a
                    story and the PRD disagree, the story is the defect.
```

> **This is the scope arbiter.** After `GOAL_07`, **no scope exists beyond an `AcceptanceCriteria`
> cell.** A story nobody asked for is scope creep with a story id, and a capability with no cell is
> not in this product.

> **Nothing here was executed.** No application code exists yet. Every criterion is a specification
> for a test that does not exist, written from the PRD — **not an observation.** Where a criterion
> mentions AWS, the behaviour is **reasoned, not observed**.

---

## The file

| | |
|---|---|
| Rows | **211** — 10 epics and 201 stories (S-ADM-30 added 2026-11-07, `SRC-008 ROLE-1`) |
| Encoding | UTF-8, no BOM, LF line endings |
| Quoting | RFC 4180. Fields containing a comma, a quote or a newline are double-quoted; a literal quote is doubled |
| Cells | **no raw newline inside any cell.** Clauses inside a criterion are separated by `; ` |
| Story points | 862 |

**Regenerate and re-validate** with the merge script recorded in the session scratch; it refuses to
write on any failure. What it checks is listed under *The checks* below.

---

## The columns

| Column | Meaning and legal values |
|---|---|
| `Type` | `Epic` or `Story`. Nothing else. |
| `ID` | `E-<CODE>` for an epic, `S-<CODE>-nn` for a story, zero-padded. The nine lane codes are `BRW` `SEA` `PAY` `TKT` `ACC` `ADM` `RPT` `XCT` `SCP`. **`ADM` carries two epics** — `E-ADM-A` and `E-ADM-B` — because its rows split across two phases. |
| `ParentID` | For a story, its epic id. **Empty for an epic**, and checked. |
| `Title` | Short imperative. No trailing full stop. |
| `Description` | What and why, in one or two sentences. **Where a story touches an open Article X row, this is where that is said** — the criterion states only what is specified. |
| `AcceptanceCriteria` | **Binary, self-contained, and it names the command or observation that decides.** Empty for an epic, and checked. See *What binary means* below. |
| `Priority` | `MustHave` · `ShouldHave` · `CouldHave` |
| `Estimate` | Story points: `1` `2` `3` `5` `8` `13`. **Empty for an epic** — an epic's estimate is the sum of its stories, and a second number on the epic row is drift waiting to happen. |
| `Milestone` | `1`–`8`, the phases of `SRC-002 §12` **as revised by `SRC-003`**. See below. |
| `Labels` | Space-separated, from: `backend` `frontend` `data` `infra` `security` `concurrency` `money` `email` `a11y` `test` `scope-guard` |
| `Status` | **`Backlog` on every row.** `GOAL_07` sets scope, not progress. `GOAL_12` owns `Status` from here on, and it is the only column edited by hand afterwards. |
| `DependsOn` | Space-separated ids. **Every token resolves to a real row, and no story may depend on a row in a later milestone** — both checked. |
| `SourceRef` | Space-separated. Carries **every `P-XXX-nn` the story covers**, and may also cite `FR-ADR-nnn`, a PRD section (`E3 S4`), or a frozen clause (`SRC-001 §2.2`). Coverage is computed from this column. |

---

## The eight milestones — `SRC-002 §12` as revised by `SRC-003`

| Phase | Delivers | Stories |
|---|---|---|
| 1 | skeleton | 19 |
| 2 | data model and admin CRUD | 52 |
| 3 | browsing and the seat-map read path | 31 |
| 4 | seat locking, booking, idempotency, **the concurrency test** | 44 |
| 5 | SQS worker and the receipt email | 14 |
| 6 | **admin movie management** *(this was the TMDB sync; the sync is deleted)* | 8 |
| 7 | metrics, rate limiting, load test, runbook | 10 |
| 8 | **the manager and admin dashboard** *(added by `SRC-003`)* | 23 |

**A story may not sit in a phase earlier than the phase providing what it depends on**, and the
merge enforces it against `DependsOn`. Three phasing calls are deliberate and would look wrong to a
naive rule:

- **`S-ACC-10`** (the `booking.user_id` foreign key) is **phase 2, not 4.** The column is written by
  the phase-2 migration, and its rule has to exist at the moment the migration author writes it —
  which is the defect `J-XCT-05` was filed for. A check reading "mentions booking → phase 4" would
  wrongly move it.
- **`S-XCT-04`** (the seat-occupancy unique constraint) is **phase 2** for the same reason: moving it
  to 4 opens a window in which bookings are written with no unique constraint.
- **`S-PAY-01`** (integer paise) is **phase 2**, because the `*_paise` columns *are* the data model.

---

## What binary means

A criterion passes or fails, and it names the thing that decides. The bar the lanes were held to:

- ❌ "The seat map works." · "Holds expire correctly." · "The dashboard shows accurate figures."
- ✅ `GET /api/showtimes/7/seats` returns 240 seats, of which `A-12` reads `sold` and `A-13` reads
  `available`.
- ✅ `scripts/stress_seats.py --showtime 41 --seat 312 --n 50` reports exactly 1 HTTP 201 and exactly
  49 HTTP 409, and `SELECT count(*) FROM booking_seat WHERE showtime_id=41 AND seat_id=312` returns 1.

**Time is injected, never read from the wall clock.** A criterion says "with the clock advanced to
`T+181s`", never "wait three minutes" — `CONSTITUTION.md` makes a test that reads the wall clock a
defect.

**Where a criterion asserts a number, the number is in the cell.** Money is **integer minor units** (the `*_paise` names), USD cents since `SRC-006 CUR-1`,
`Asia/Kolkata`.

**A scope guard proves absence.** The `E-SCP` epic asserts that excluded capabilities have no
surface — a 404, a route enumeration, a dependency manifest. Those stories carry the `scope-guard`
label. **`SRC-001 §6.6` says excluded is not blocked**, so a scope guard must never assert that a
*preserved affordance* is absent: the `cinema` entity, the booking status and `cancelled_at` exist
on purpose and are exposed by no endpoint. Asserting those away would break the product's future.

---

## The checks the merge enforces

| Check | Result at close |
|---|---|
| header and column count on every lane file | pass |
| enum legality: `Type` `Priority` `Estimate` `Milestone` `Status` `Labels` | pass |
| id uniqueness; `ParentID` resolves; epics carry no criteria, no parent, no estimate | pass |
| `DependsOn` resolves — no dangling id, no invented cross-lane story id | pass |
| **no story depends on a story in a later milestone** | pass |
| **`no-gap`** — every P-row in the PRD covered by at least one story | **0** |
| **`no-creep`** — every `P-XXX-nn` cited actually exists | **0** |

**163 of 163 P-rows are covered.** The universe is harvested from `docs/03 PRD/sections/`, not typed.

---

## What a reader should be sceptical about

- **Table names are unconfirmed.** Criteria cite `users`, `booking`, `booking_seat`,
  `password_reset_token`, `outbox_message`, `showtime`, `audit_log`, taken from the PRD's own SQL.
  **`docs/06 DataModel/` is empty** — there is no schema of record, and a rename in `GOAL_08` breaks
  every `SELECT` in this file. `GOAL_08` inherits these names as a constraint rather than a free
  choice.
- **Estimates have no velocity behind them.** Nothing on this project has been built. They are
  shaped by how many distinct assertions a cell carries and nothing else.
- **Priority carries little information** — 194 `MustHave` to 6 `ShouldHave`. Four lanes reported
  this and declined to manufacture a spread by demoting stories they believed were required. That is
  the honest reading of a product whose PRD rows are almost all `RULED`.
- **Two criteria depend on test-harness capability that no document specifies**: `S-ACC-13` and
  `S-ACC-08` need query logging. Without it those clauses become *unrunnable* rather than failing,
  which is worse than weak.
- **`S-SEA-20`** asserts the 145-pair state machine against a lifecycle state **no endpoint
  exposes**; it is binary only if a test-only inspection seam exists, which the PRD does not specify.
- **`S-SEA-15`** asserts a 503 arriving "in under 2× the configured timeout" — a wall-clock
  measurement inside a test, which brushes the rule above. A client timeout cannot be proved with an
  injected clock.
