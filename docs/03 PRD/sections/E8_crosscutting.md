# E8 — cross-cutting floors

This epic is everything that is true on every request, every screen and every process, and that no
single feature owns. The two-layer seat guarantee. Integer money. The audit row. The rate limiter.
Sessions and authorisation. The cache. Health and readiness. Logging. Configuration. Graceful
shutdown. Migrations. The memory budget. Accessibility. What nobody is watching. Recoverability. The
zone boundary. Scope governance. The phase plan. Nothing here is a feature a customer asks for, and
every one of these is a defect a customer eventually meets.

**The one thing that will be got wrong.** These floors read as a checklist of good practice, and they
are not. Each one is here because a specific frozen clause or a specific recorded trap put it here,
and each one has a wrong implementation that passes ordinary tests. A rate limiter behind a load
balancer limits the load balancer. A health check that touches the database restarts every container
on a database blip. An audit row written after the commit is missing exactly the rows that crashed. A
lock released without a token comparison frees somebody else's seat. **A floor that looks satisfied
because nothing has failed yet is not satisfied.** Where a rule below has a wrong implementation, the
wrong implementation is named, because naming it is the only thing that stops it being written.

---

## S4 — Product specifications

Thirty-two rows. Each is a floor: it constrains code that other lanes write, and it is enforced in
one place rather than repeated at every call site. `## S7` is the reference material behind these
rows — the two must agree, and where S7 goes into more mechanism it does not restate the rule.

---

### `P-XCT-01` · Enforce the seat guarantee in two systems and never waive the database half · `RULED`
`[SRC: SRC-001 §2.2 · SRC-001 §7.1 · SRC-002 §8.1.5 · SRC-002 §9.1 · FR-ADR-024 · FR-ADR-034]`
`[BRD: R-QLY-03 · R-CON-11]`

**Behaviour.** A seat is never sold to two customers. The guarantee is enforced twice, in two
independent systems: a Redis lock provides the hold, and a unique constraint on
`(showtime_id, seat_id)` on the seat-occupancy table plus row locking in the confirm transaction
provides the truth. **The database half may not be waived, at any confidence, for any reason** —
waiving a quality check is reserved to the client, and this is the check.

**Who may do it.** Nobody may waive it. The constraint is created in the Phase 2 migration, before
any code can write a booking, so no window exists in which bookings are written without it. Removing
it is a schema change, and the only permitted removal is the red-proof drill in the local
environment.

**Preconditions.**
- The unique constraint exists on the seat-occupancy table and is total, with no `WHERE` clause.
- Every code path that writes seat occupancy goes through that table. There is no bulk-insert path
  and no `ON CONFLICT DO NOTHING` anywhere near it.
- `scripts/stress_seats.py` exists and fifty distinct authenticated customers are seeded
  (`P-XCT-30`), each with a password that works (`P-XCT-32`).
- **The script holds fifty access tokens before the measured window opens. How it obtains them —
  an untimed warm-up phase that signs in through the real sign-in endpoint, and why the login rate
  limiter therefore cannot touch the result — is `P-XCT-07`'s, and the arithmetic is written there
  once rather than in every row that depends on it.**
- **Stage B of the drill additionally needs direct command access to the Redis instance under test
  and a non-zero `PAYMENT_SIMULATED_DELAY_MS`.** Both hold in the local compose stack and neither
  holds in AWS, which is one more reason the drill is local only.

**Happy path.**
1. A customer holds seats. Redis grants the lock atomically, one winner per seat.
2. The customer confirms. The confirm transaction re-validates the hold, then inserts the
   seat-occupancy rows.
3. The unique constraint accepts them. The booking commits.
4. Fifty simultaneous **hold** requests for one seat produce exactly one HTTP 201 and forty-nine 409
   `SEAT_UNAVAILABLE`, and — once the winner confirms — **exactly one row in the seat-occupancy table
   for that `(showtime_id, seat_id)`, read directly from PostgreSQL.** **All forty-nine are refused by
   the Redis lock at `SET … NX`; the unique constraint fires zero times in a passing run of that gate.**
   `P-HLD-13` owns the gate and this row does not redefine it.

**Which layer refuses whom — and why the drill cannot fire at the hold.**

**The two layers are not two chances at the same event. They catch different events, and only one of
them is reachable from the fifty-request gate.**

| Layer | Refuses | Reached by |
|---|---|---|
| The Redis lock, `SET … NX` | a second customer asking for a seat **while a first customer holds it** | every one of the forty-nine losers in the fifty-request gate |
| The unique constraint at insert | a second customer **confirming** a seat that already has a committed `booking_seat` row — which can only happen when **Redis was wrong**: an eviction, a restart, a clock difference or a bug in the release path | **nothing in the fifty-request gate.** Only one caller ever reaches `P-PAY-10` step 7, and they reach it uncontended |

**So dropping the unique constraint changes nothing observable at the hold endpoint.** Redis still
grants one lock, one customer still confirms, and `SELECT count(*)` still returns `1`. **A drill that
drops the constraint, re-runs the fifty-request gate and expects more than one winner is asking the
wrong endpoint a question it cannot answer** — and, worse, the specification then classifies a correct
implementation as a stop-the-line finding. That defect was real and is corrected here: **the red-proof
drill runs in two stages, and only the second one touches the constraint.** The stages are below, and
`S7.1` carries the procedure.

**The two-system guarantee is unchanged and is not weakened by this.** A Redis lock still provides the
hold, the unique constraint plus row locking still provides the truth, and **the database half may
still not be waived.** What changed is which endpoint the proof fires at, and the change is **stricter**
— the gate as it stood exercised the constraint zero times, and it now exercises it explicitly and
watches it fail. Adopting a stricter option needs no signature (`CONSTITUTION.md` Art III.10).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The unique constraint fires at insert — another booking took the seat first. **This is the confirm path** (`P-PAY-10` step 7), never the hold | 409 `SEAT_UNAVAILABLE`, the whole confirm transaction rolled back | **`P-HLD-14` row 4 (one seat lost) or row 4b (two or more) — the *at confirm* sentences. This row publishes none of its own** (`P-PAY-11`) |
| 2 | The hold is gone at confirm | 409 `HOLD_EXPIRED` | "The hold on your seats has ended and they have been released. You have not been charged." |
| 3 | Redis is unreachable on the hold or confirm path | 503 `DEPENDENCY_UNAVAILABLE` | "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes." |
| 4 | The stress script's fifty request start instants span more than the configured threshold | the script exits non-zero with "not concurrent" | *(no user-facing surface — this is a build gate)* |
| 5 | **Stage B** of the drill runs with the constraint dropped and still produces exactly **one** `booking_seat` row for the pair | the drill is recorded as **failed** and the whole proof is void — the run did not reach the constraint | *(no user-facing surface — this is a stop-the-line finding)* |
| 5a | **Stage A** — the fifty-request gate — is run with the constraint dropped and produces one winner | **that is the expected result and it is not a finding.** Stage A fires at the hold, where Redis decides the winner and the constraint is never reached. **A drill that reads Stage A as the red proof has proved nothing**, and reading it as a failure blocks a story for a defect that is not there | *(no user-facing surface)* |

**Why exception 1 publishes no sentence of its own, when it used to.** It previously carried
`"C12 and C13 were taken by another customer. No seats were held. Your other choices are still
selected."` — which is `P-HLD-14` row 3, the ***at hold*** sentence, on a trigger that fires at
**confirm**. A customer who held seats, paid, and had the whole transaction rolled back was being told
that no seats were held and that their other choices were still selected: both halves untrue, and
`P-SEA-03` states in terms that a message on that path may never say *held* where the customer's seats
were only *selected*. `P-HLD-14` declares itself the complete message set for these codes and gives
the confirm case rows 4 and 4b; `P-PAY-11` defers to them by name and so does this row.

**Server-side validation.** The constraint is a database object, not a check in code. A pre-insert
`SELECT` to see whether a seat is free is **not** validation and must not be written: a
`SELECT ... FOR UPDATE` on rows that do not exist locks nothing, so two transactions both find no
row, both proceed and both insert. The violation is caught at insert and translated; it is never
retried, and it is logged as an expected outcome with a counter, not as an exception.

**Worked example — Stage A, the fifty-request gate** (`SRC-002 §9.1`, `P-HLD-13`). Fifty concurrent
**hold** requests for showtime `41`, seat `312`.

```
HTTP 201 responses ............ 1        (exactly one, never "at most one")
HTTP 409 SEAT_UNAVAILABLE ..... 49       all forty-nine refused by Redis at SET … NX
rows in booking_seat where (showtime_id, seat_id) = (41, 312) ....... 1   (after the winner confirms)
request start-instant spread .. 38 ms    (threshold 100 ms — the script trusts its own result)
unique-constraint violations .. 0        <- the figure that makes Stage B necessary
```

**Worked example — Stage B, the red-proof drill.** Stage B has to produce **two live holders of one
seat**, because that is the only state from which two confirms both reach `P-PAY-10` step 7. It
produces it by injecting the exact Redis failure the database half exists to survive — **the loss of a
lock key** — inside the confirm window that `PAYMENT_SIMULATED_DELAY_MS` opens.

```
PAYMENT_SIMULATED_DELAY_MS = 1500        the window step 6 spends, and the drill's working room

t = 0.00 s   A: POST hold (41, 312)          -> 201, token tA, key lock:seat:41:312 = tA
t = 0.10 s   A: POST confirm, async          -> step 2 re-validates tA and passes; step 6 begins
t = 0.30 s   drill: DEL lock:seat:41:312     <- an eviction, injected by hand, in Redis
t = 0.40 s   B: POST hold (41, 312)          -> 201, token tB.  SET … NX succeeds, the key is gone;
                                                P-HLD-01 step 7 reads booking_seat and finds nothing,
                                                because A has not committed.  TWO LIVE HOLDERS.
t = 0.50 s   B: POST confirm, async          -> step 2 re-validates tB and passes; step 6 begins
t ≈ 1.6-2.0  both reach P-PAY-10 step 7 and insert
```

| The constraint | What Stage B produces | What it proves |
|---|---|---|
| **present** | exactly one `201`, exactly one `409 SEAT_UNAVAILABLE`, and **one** `booking_seat` row for `(41, 312)` | **the constraint firing, observed.** The 409 here is the database half, not Redis |
| **dropped** | **two `201`s and two `booking_seat` rows for `(41, 312)`** — the seat sold twice, to two customers who both paid | **the red proof.** This is the outcome the drill exists to watch |
| **restored** | one row again, and the constraint read back from `pg_constraint` | the restore verified rather than assumed |

**Deleting a lock key is not disabling a control, and the distinction is the same one `P-XCT-07`
draws about bucket sizes.** Nothing is switched off: the lock layer runs normally throughout, both
holds go through the real `SET … NX`, and both confirms re-validate their token exactly as
`P-PAY-10` step 2 requires. What is injected is a **fault** — a key disappearing — which is a thing
Redis does on its own under memory pressure and does wholesale on a restart, and it is precisely the
event `S7.1` names as the reason the database half may not be waived. **Dropping a constraint on
purpose and evicting a key on purpose are the same kind of act**, and both are local-environment only.

Recorded with who ran it and when, for both stages. **An undated claim that it was run is not
evidence.**

---

### `P-XCT-02` · Compute and store money as integer paise, through one function · `RULED`
`[SRC: SRC-003 OPEN-LOCALE-01 · SRC-003 OPEN-PRICE-01 · SRC-001 §7.6 · FR-ADR-036 · FR-ADR-038]`
`[BRD: R-QLY-08 · R-CON-11]`

**Behaviour.** Currency is INR. Money is an integer number of paise everywhere: `Decimal` at the
parsing boundary, `bigint` in persistence, a formatted string at render time only. The minor-unit
ratio is `100`, held as the named configuration value `CURRENCY_MINOR_UNIT_RATIO` and never as a
literal on the money path. **One function computes a seat price and every caller uses it** — the
seat map, the checkout total, the receipt, the dashboard and the seed script.

**Who may do it.** No role. This is a code-level floor. Changing `CURRENCY_MINOR_UNIT_RATIO` is
reserved to the client and is a one-way door: bookings are permanent, so reinterpreting the unit
later silently rewrites what every past customer paid, and no migration fixes it because no row
records which interpretation it was written under.

**Preconditions.**
- `CURRENCY_CODE` and `CURRENCY_MINOR_UNIT_RATIO` are loaded and validated at boot and logged once.
- Every money column is `bigint` and every money identifier carries a `_paise` suffix.

**Happy path.**
1. A money value arrives as text or JSON. It is parsed to `Decimal`, validated, and converted to an
   integer number of paise before it travels any further.
2. Every price computation calls the single pricing function, which takes two integers and returns
   one integer.
3. The value is stored as `bigint`.
4. The presentation layer formats it, in `--fr-font-mono` with Indian digit grouping, at render.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A money field arrives that is not a valid decimal, or is negative | 422 `VALIDATION_FAILED` | "Enter an amount as a number, for example 250.00." |
| 2 | A money field arrives with more than two decimal places | 422 `VALIDATION_FAILED` | "An amount can have at most two decimal places." |
| 3 | `CURRENCY_MINOR_UNIT_RATIO` is not `100` while `CURRENCY_CODE` is `INR` | the process exits non-zero at boot | *(no user-facing surface — the application does not start)* |
| 4 | A caller attempts to persist an unrounded value | the column type rejects it — a `bigint` cannot hold a fraction | *(no user-facing surface)* |

**Server-side validation.** Amount fields: `Decimal`, non-negative, at most two decimal places,
maximum `92,233,720,368,547,758` paise (the `bigint` ceiling), converted to `int` before use. A
`float` anywhere on the money path is a defect regardless of whether a test caught it. `SUM()` over a
`bigint` column returns `numeric` in PostgreSQL and arrives in Python as `Decimal`; it is cast back
to `BigInteger` in the query.

**Worked example.** The rounding rule and its four worked examples live in `FR-ADR-038` and are
written into lane E3's section; they are not restated here. **The invariant a reviewer checks is
this:** the sum of the per-seat prices displayed on the seat map equals the booking total to the
paisa, because the total is the sum of already-rounded per-seat prices and **the total is never
rounded**. Three Recliner seats at `33333` paise each total `99999` paise. A total computed by
rounding once would read `99998` — one paisa apart, and the customer was shown `33333` three times.
If those two numbers ever differ, a second implementation of the formula exists somewhere and that is
the defect.

---

### `P-XCT-03` · Write the audit row in the same transaction as the change · `RULED`
`[SRC: SRC-001 §7.6 · SRC-003 OPEN-OPS-03 · SRC-003 OPEN-OPS-02 · FR-ADR-019 · FR-ADR-012]`
`[BRD: R-QLY-08]`

**Behaviour.** Every privileged write inserts one row into `audit_log` **in the same database
transaction as the change itself.** Either both land or neither does. The table is append-only at the
database-role level: the application role holds `INSERT` and `SELECT` on it and no `UPDATE` and no
`DELETE`.

**Who may do it.** Only the admin performs privileged writes, so every audit row names an admin. The
row records the role the actor held **at the time**, copied rather than joined, because a role can
change. The screen that reads the table is Phase 8; the rows are written from Phase 2, because an
audit trail that starts when its reader is built has a hole exactly as long as the build took.

**Preconditions.**
- `audit_log` exists with the columns in S7 §3 and the restricted grant is applied.
- The acting user id and the request id are available in the request context.
- The `action` value is a member of the controlled vocabulary. **That vocabulary is published by the
  administration section and it is closed** (`FR-ADR-019`): **no section may coin an action string of
  its own.** A value outside it is a defect, and — worse than a loud one — a *filter* written against
  a non-member returns an empty list while looking entirely correct. A base-price change is
  **`showtime.base_price_changed`** — that exact string is the published member, and a shortened
  paraphrase of it is not one.

**Happy path.**
1. An admin submits a privileged write.
2. The handler opens one transaction.
3. It applies the change.
4. It inserts the audit row, carrying `actor_user_id`, `actor_role`, `action`, `entity_type`,
   `entity_id`, `before`, `after` and `request_id`.
5. It commits. Both rows are visible together or neither is.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The audit insert fails | the whole transaction rolls back; the change does not land | "The server could not complete this request. If you need help, quote `a1b2c3d4`." — the registry's one published sentence for the code, as exception 3. **No variant is minted for the audit path** |
| 2 | The change fails | the transaction rolls back; no audit row exists for a change that did not happen | *(the change's own error is shown)* |
| 3 | Code attempts `UPDATE` or `DELETE` on `audit_log` | the database refuses — the grant does not exist | 500 `INTERNAL_ERROR`, and the customer sees "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| 4 | An `action` value outside the controlled vocabulary is used | 500 `INTERNAL_ERROR` at the boundary check, before the transaction opens | as above |

**Server-side validation.** `actor_user_id` is non-null and is a real user row — never a role name
and never a service account. `action` is checked against the controlled list before the transaction
opens. `before` and `after` carry **only the fields that changed**, not the whole row; a full-row
snapshot on every edit makes this the largest object in the database and buries the field that moved.
`before` is null for a creation.

**Worked example.** An admin changes a showtime's base price from `25000` paise to `28000` paise
during request `a1b2c3d4`.

```
audit_log row:
  occurred_at    2026-08-14T14:07:11Z          (timestamptz, UTC)
  actor_user_id  17
  actor_role     admin
  action         showtime.base_price_changed
  entity_type    showtime
  entity_id      41
  before         {"base_price_paise": 25000}
  after          {"base_price_paise": 28000}
  request_id     a1b2c3d4
```

Both the showtime update and this row commit together. If the process dies between them, neither
exists.

---

### `P-XCT-04` · Answer "who booked this seat and when" for any seat, at any time · `RULED`
`[SRC: SRC-001 §7.6 · SRC-001 §1.1 · SRC-003 OPEN-OPS-02 · FR-ADR-012 · FR-ADR-019 · FR-ADR-039]`
`[BRD: R-QLY-08]`

**Behaviour.** For any seat of any showtime, at any time, the system can say who booked it, when, and
what they paid. This is answered by the permanent booking record, not by the audit log: a customer
booking a seat is the product working, not a privileged write.

**Who may do it.** Admin, through the Phase 8 dashboard and directly against the database. A manager
sees this only for their assigned screens. A customer sees only their own bookings.

**Preconditions.**
- **Nothing on a path that can reach a booking is ever deleted.** No pruning job, no retention
  window, no `ON DELETE CASCADE` on any such path; the default is `ON DELETE RESTRICT`. *(The product
  is not delete-free in general — `P-XCT-11` scopes that claim, and the two deletions that do exist
  are unreachable from a booking by their own preconditions.)*
- The booking's `user_id` foreign key is non-null.
- The per-seat price is snapshotted onto the booked-seat row at hold acquisition and never
  recomputed.
- Every table carries `created_at`; tables that mutate carry `updated_at`.

**Happy path.**
1. The question is asked for `(showtime_id, seat_id)`.
2. The seat-occupancy row for that pair resolves to exactly one booking — the unique constraint
   guarantees at most one, and its absence means the seat was never sold.
3. The booking resolves to a user row, a `created_at` instant, and a snapshotted price in paise.
4. The answer is rendered in Asia/Kolkata.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The seat was never sold | 200 with an empty result — this is a valid answer, not an error | "This seat has not been booked." |
| 2 | A manager asks about a screen they are not assigned to | 403 `FORBIDDEN` | "This account does not have access to that hall." |
| 3 | A customer asks about a booking that is not theirs | 403 `FORBIDDEN` | "This account does not have access to that booking." |
| 4 | An entity the booking references has been removed | cannot occur — `ON DELETE RESTRICT` prevents it, and the attempted delete fails | *(no user-facing surface)* |

**Server-side validation.** `showtime_id` and `seat_id` are positive integers. The manager scope
check runs on the router as a dependency, never in the handler. **The test shape is fixed:** assert a
**non-empty** result for the manager's own screens and a denied result for another's. A test
asserting only "denied" passes against a query that returns nothing for anybody.

**Worked example.** Seat `312` of showtime `41`.

```
booking_seat  → booking_id 9008, price_paise 28124   (snapshotted, not recomputed)
booking       → user_id 4471, created_at 2026-08-12T18:41:03Z
rendered      → "Booked by nikhil@example.invalid on 13 Aug 2026 at 00:11 (Asia/Kolkata) for ₹281.24"
```

`18:41:03Z` on 12 August is `00:11` on 13 August in Asia/Kolkata. The date boundary is always taken
in the cinema's zone, never in the container's, which is UTC.

---

### `P-XCT-05` · Apply authorisation once, on the router, as a dependency · `PROVISIONAL`
`[SRC: SRC-001 §7.4 · SRC-003 C-1 · SRC-003 OPEN-OPS-03 · FR-ADR-009 · FR-ADR-011]`
`[BRD: R-QLY-06]`

> ⚠ **`PROVISIONAL`.** The four-role set is a build-session reading that reconciles two of the
> client's own answers (`SRC-003 C-1`). One message from the client reverses it. If it reverses to
> three roles, the manager role value, the assignment table and the manager router are removed and
> the dashboard is served to admins with a screen filter.

**Behaviour.** Every endpoint's access rule is declared once, on the router it belongs to, as a
dependency. **Never per handler.** Four routers exist: public, customer, manager and admin. A handler
contains no role check.

**Who may do it.**

| Role | Account | May reach |
|---|---|---|
| **guest** | none | the public router only. Cannot hold and cannot book. |
| **customer** | required | the public and customer routers |
| **manager** | required | the public, customer and manager routers. **Read only** — a manager endpoint that writes anything is a defect, not a feature. |
| **admin** | required | every router, including everything a manager can do |

**Preconditions.**
- The session cookie is present and its JWT verifies, for anything above the public router.
- The user row carries exactly one role value in a single column. Roles are mutually exclusive; admin
  is a superset of manager by capability, not by composition.
- For the manager router, the `(manager, screen)` assignment table is populated.

**Happy path.**
1. A request arrives at a router.
2. The router's dependency resolves the session, loads the user and their role, and compares it
   against the router's permitted set.
3. On the manager router — **mounted at `/api/reports`**, which is where the dependency is attached —
   the dependency additionally narrows every query to the caller's assigned screens, **resolved from
   the session, never from a parameter in the request.**
4. The handler runs, having performed no authorisation of its own.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session on a non-public router | 401 `AUTH_REQUIRED` | "Sign in to continue." — **this row's generic default. On the reports surface `P-RPT-02` row 1's sentence ships instead** |
| 2 | The session's JWT is expired or does not verify | 401 `AUTH_REQUIRED` | "You were signed out. Sign in again to continue." |
| 3 | A signed-in user reaches a router their role does not permit | 403 `FORBIDDEN` | "This account does not have access to that page." — **generic default; on the reports surface `P-RPT-02` row 2's sentence ships instead** |
| 4 | A manager requests data for a screen they are not assigned to | 403 `FORBIDDEN` | "This account does not have access to that hall." — **generic default; on the reports surface `P-RPT-02` row 3's sentence ships instead** |
| 5 | A manager reaches a write endpoint **on the manager router** | cannot occur — **the manager router mounts no write route at all**, which is the control (`P-RPT-09`) | *(no user-facing surface)* |
| 5a | A manager addresses a write endpoint **on the admin router** — a hand-made request, or a client bug | **403 `FORBIDDEN`, refused by the admin router's role dependency before the body is parsed.** This case is entirely reachable and **it is the one `SRC-003 OPEN-OPS-03` exists to prevent, so it carries a test** | **`P-RPT-09` row 1 publishes it and this row publishes none** |
| 5b | A non-`GET` method is addressed at a path on the reports router | **405 `METHOD_NOT_ALLOWED`**, rendered by the global handler as the product envelope (`P-XCT-11`) — **not 404**, because the path exists for `GET` | `SCR-XCT-01`'s `METHOD_NOT_ALLOWED` string, published once and reused |
| 6 | A manager has no screens assigned yet | 200 with an empty dashboard — the correct state for a new account, not an error | "No halls are assigned to this account yet." — **generic default; on the reports surface `P-RPT-08` row 1's sentence ships instead** |

**Exception 5 used to read "a manager reaches *any* write endpoint — cannot occur", and that sentence
had a hole exactly where it mattered.** It is true of the **manager router**, which mounts no write
route; it is false of the **admin router**, which a manager can address directly and which refuses
them with 403. **A developer building the authorisation floor from this row alone would have written
no test for the single case `SRC-003 OPEN-OPS-03` exists to prevent**, because the floor row said the
case was impossible. Rows 5 and 5a now say which is which, and 5a says it carries a test.

**Why four of these sentences are defaults rather than the words that ship.** `P-RPT-01`, `P-RPT-02`
and `P-RPT-08` publish wording for the same four conditions on the reports surface, and two of the
four pairs are **different sentences rather than paraphrases** — *"Sign in to see the dashboard."*
against *"Sign in to continue."*, and *"That hall is not assigned to this account."* against *"This
account does not have access to that hall."* Both rows are rank 2, so `S1.2`'s ranking does not settle
it and `S1.2.1` case 1 makes an unresolved rank-2 tie a defect rather than the implementer's choice.
**It is settled the way `SCR-XCT-01` settles `FORBIDDEN` and `AUTH_REQUIRED`: the row that knows what
the caller could not reach owns the words.** A manager refused another hall's dashboard needs
different words from a customer refused another customer's booking, and a sentence that avoids saying
which serves neither. **This row's four sentences are the floor's generic restatement**, used on any
router whose own P-row publishes nothing, and they carry no authority over the reports surface. **A
lane that finds itself shipping one of them on a surface that has an owning P-row has found a gap in
that row**, not a finished string.

**Server-side validation.** The role is read from the database on every request, never from a claim
in the token, so a role change takes effect on the next request rather than at the next sign-in. The
screen scope is applied in the query's `WHERE` clause by the dependency, not by filtering results
after they are fetched.

**Worked example.** Manager `88` is assigned screens `2` and `5`. **The manager router is mounted at
`/api/reports`**, which is the real prefix and the place the authorisation dependency is attached — so
the path here is not cosmetic. A dependency mounted on a prefix nothing is served from protects
nothing.

```
GET  /api/reports/dashboard                → 200, non-empty   (screens 2 and 5, resolved from the session)
GET  /api/reports/dashboard?screen_id=2    → 200, non-empty   (a narrowing inside the resolved scope)
GET  /api/reports/dashboard?screen_id=4    → 403 FORBIDDEN    (not assigned — refused, never honoured)
POST /api/reports/dashboard                → 405 METHOD_NOT_ALLOWED   (the path exists for GET)
PATCH /api/admin/showtimes/101 as manager  → 403 FORBIDDEN    (the admin router's role dependency)
```

**Line four says 405 and not 404, and the difference is the whole of the negative test.** This row
previously read *"POST anything on the reports router → 404, no such route"*, which contradicts
`P-RPT-09` row 3, the `METHOD_NOT_ALLOWED` registry entry and `P-XCT-11` exception 3a — all three of
which give **405** for a path that exists under another method. **The negative test for the read-only
reports router is transcribed from one of these rows**, so a suite built from the old line asserts 404
and passes against a wrong implementation, while a suite built from the registry asserts 405 and fails
against a correct one. **404 was also the wrong answer on the merits**: `/api/reports/dashboard`
exists and serves `GET`, and a 404 denies that to the only audience that ever sees it.

**Line five is the case exception 5 used to call impossible.** It is a real request a manager can
make, it is refused at the admin router by the same dependency this row specifies, and it is the case
`SRC-003 OPEN-OPS-03` exists to prevent — so it is in the worked example rather than left to be
inferred from a row that said it could not happen.

**The scope comes from the session, not from the request.** Line one carries no `screen_id` at all and
still returns exactly screens 2 and 5, because the dependency reads the caller's assignments from
their session. A `screen_id` in the query string can only **narrow** that resolved set and can never
widen it: line two names a screen inside it and is honoured, line three names one outside it and is
**refused rather than served**. A handler that read `screen_id` and trusted it would hand manager `88`
screen `4`, which is the defect this row exists to prevent.

The first line is the assertion that matters. A test that only checks the third passes against a
query that returns nothing for anybody.

---

### `P-XCT-06` · Store credentials so they cannot be read back, and carry the session in a cookie · `RULED`
`[SRC: SRC-001 §7.4 · SRC-002 §4.8 · SRC-003 OPEN-BOOK-02 · SRC-003 OPEN-TLS-01 · FR-ADR-050 · FR-ADR-069]`
`[BRD: R-QLY-06 · R-CON-08]`

**Behaviour.** Email and password, our own, with a JWT. Never Cognito. The password is hashed with
bcrypt, off the event loop. The JWT travels in an `HttpOnly`, `SameSite=Lax` cookie, never in
`localStorage`. **`COOKIE_SECURE` is environment-driven, has no default, and is off in the deployed
environment** while `OPEN-TLS-01` is deferred.

**Who may do it.** Anyone may register and sign in. A guest may browse and select seats; the account
requirement is enforced at the hold.

**Preconditions.**
- `JWT_SECRET` and `COOKIE_SECURE` are loaded at boot; neither has a default.
- A unique index exists on `lower(email)`.
- bcrypt hashing runs in a thread, not inside an `async def`.

**Happy path.**
1. A customer registers with an email and a password of at least 12 characters.
2. The email is stored as entered and constrained on its lowercased form.
3. The password is hashed with bcrypt in a thread and the hash is stored. The plaintext is never
   logged, never returned and never stored.
4. On sign-in the hash is compared and a JWT is issued in an `HttpOnly`, `SameSite=Lax` cookie with
   `Secure` set from `COOKIE_SECURE`.
5. The session expires after `SESSION_TTL_SECONDS`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The password is shorter than 12 characters | 422 `VALIDATION_FAILED` | "Use a password of at least 12 characters." |
| 2 | The password is longer than 72 bytes | 422 `VALIDATION_FAILED` | "Use a password of 72 bytes or fewer. Some characters count as more than one byte." |
| 3 | The email is already registered | **409 `EMAIL_ALREADY_REGISTERED`** — a distinct code so the interface can offer the sign-in tab and the reset link, which a generic validation failure cannot (`P-ACC-01` owns it) | "That email address is already registered. Sign in instead." |
| 4 | The email or password is wrong at sign-in | 401 `CREDENTIALS_INVALID` — **not** `AUTH_REQUIRED`, which means "no session at all" and would render "sign in to continue" *on* the sign-in screen | "That email address and password do not match an account." |
| 5 | A password reset is requested for an address that is not registered | **202**, identical response and identical timing to the registered case (`P-ACC-07` owns the status) | "If that address has an account, a reset link has been sent to it." |
| 6 | The session expires mid-flow | 401 `AUTH_REQUIRED`, context preserved in `sessionStorage` | "You were signed out. Sign in again to continue. Your seat selection has been kept." |
| 7 | Sign-in is attempted past the rate limit, and the **per-IP** bucket is the one that refused | 429 `RATE_LIMITED` with `Retry-After`, **computed from that bucket's refill rate and never a constant** (`P-XCT-07`, S7.4). That bucket is 30 tokens per 900 s, so one token is earned every `900 / 30 = 30` s and the header is `Retry-After: 30` | "Too many attempts. Try again in 30 seconds." |
| 8 | Sign-in is attempted past the rate limit, and the **per-user** bucket is the one that refused | same code and header. That bucket is 10 tokens per 900 s, so `900 / 10 = 90` s and the header is `Retry-After: 90` | "Too many attempts. Try again in 90 seconds." |
| 9 | Registration or a password-reset request is attempted past the rate limit | same code and header. Both buckets are 5 per hour, so `3600 / 5 = 720` s and the header is `Retry-After: 720`, which S7.20 renders as minutes because it is at or above the 120-second threshold | "Too many attempts. Try again in 12 minutes." |

**On rows 7 to 9, and why there are three of them.** `900` was previously published here as the wait,
and `900` is the bucket's **window**, not its refill interval — the mistake S7.4's worked example
exists to prevent, and the reason this row now shows the division. **The endpoint-specific wording is
`P-ACC-01`, `P-ACC-02` and `P-ACC-07`'s** — "Too many sign-in attempts from this connection", and so
on — and those rows publish the same three figures. The sentences here are this row's generic
restatement of them and carry no authority over their wording; **the arithmetic, however, is
`P-XCT-07`'s and is the same in both places.** Every derivation in the product is tabulated once in
**S7.20**.

**Server-side validation.** Email: shape-validated and normalised, maximum 254 characters, unique on
`lower(email)`. Password: minimum `PASSWORD_MIN_LENGTH` characters, maximum 72 **bytes** enforced
explicitly and with its own message — **bcrypt silently truncates at 72 bytes**, and a truncation
nobody sees means two different long passwords authenticate the same account. The comparison runs
against a dummy hash even when the email is unknown, so response timing does not disclose whether an
account exists.

**Worked example.** The 72-byte boundary is bytes, not characters.

```
72 Latin characters      = 72 bytes  → accepted
25 Devanagari characters = 75 bytes  → rejected with message #2, not truncated
```

**`SameSite=Lax` is this product's only cross-site request defence, and this paragraph exists because
nothing said so.** The session cookie is attached by the browser to **every** request to this origin,
including one a different site caused. **There is no CSRF token, no double-submit cookie and no
`Origin` or `Referer` check anywhere in this specification** — the attribute was chosen and justified
here only on the ground that `Strict` would drop the cookie on the cross-site return from an emailed
link, which is a usability reason for a security control. **A defence nobody has named is a defence
somebody removes by accident.**

**What it buys.** A browser withholds a `SameSite=Lax` cookie on every cross-site request except a
**top-level navigation using a safe method**. So a cross-site `POST`, `PUT`, `PATCH` or `DELETE`, and
every cross-site `fetch` or `XMLHttpRequest` whatever its method, arrives with **no session**. Every
state-changing endpoint in this product is one of those, so every state change is covered.

**The two changes that remove it, named so that neither can be made without meeting this sentence:**

1. **A state-changing `GET`.** `Lax` sends the cookie on a top-level `GET` navigation, so an endpoint
   that writes on a `GET` is reachable cross-site with the customer's session attached. **This is the
   reason no endpoint in this product may change state on a `GET`** — a stated security reason, not
   REST tidiness, and the distinction matters because tidiness is negotiable and this is not.
2. **Relaxing the attribute to `SameSite=None`.** One line, and it is exactly what someone reaches for
   the first time a second origin is introduced. **There is nothing behind it**: with `None` set and no
   token, every authenticated write in the product is cross-site reachable.

**What it does not buy, stated rather than glossed.** `Lax` is a **browser** behaviour and not a server
check, so it binds only clients that implement it. **Nothing is added here** — no token, no
double-submit, no `Origin` check. The gap is recorded on the same terms as Argon2id in `P-XCT-23`:
this is a demonstration environment that carries no real customer data by ruling (`R-CON-08`,
`P-XCT-29`), and **a server-side CSRF check is the thing to add before it ever carries a real
person's booking.** Naming it is what turns a later removal into a decision instead of a discovery.

**Two accepted weaknesses, recorded rather than solved.** There is **no email-verification gate in
v1**, so a customer can register with a mistyped address and book; the mitigation is that the address
is shown back on the confirmation screen and the booking reference is on screen and in the bookings
list regardless. And **`COOKIE_SECURE` is off in the deployed environment**, so credentials cross the
network unprotected there. Both are named owners' decisions, not oversights: the second is
`OPEN-TLS-01` and is the reason that environment is never called production and carries no real
customer data.

---

### `P-XCT-07` · Rate-limit per user and per IP with a Redis token bucket, failing closed · `RULED`
`[SRC: SRC-002 §8.4.1 · SRC-002 §8.4.2 · SRC-002 §7.9 · SRC-002 §9.1 · FR-ADR-058 · FR-ADR-028 · FR-ADR-034]`
`[BRD: R-QLY-03 · R-QLY-06]`

**Behaviour.** A token bucket in Redis, evaluated by a Lua script so the read, the refill and the
decrement are one atomic operation. **Two independent buckets per limited request — one per user, one
per IP — and both must have a token.** On Redis being unreachable the limiter **fails closed**: 503,
not unlimited access.

**Who may do it.** Everyone is limited. The stress script is not exempted: it authenticates as fifty
distinct customers, which stays inside the per-user buckets, and **the per-IP bucket for seat holds
and the per-IP bucket for sign-in are both named configuration, and the environment under test sets
each to a value that admits the run** — the same treatment, stated in the same words, so that the two
are visibly one rule and not one rule and one favour. **Disabling a control to make a test pass is a
fake green**, and waiving a quality check is reserved to the client. **Setting a configured bucket
size is not disabling a control**: every request is still counted, still bucketed and still refused
when the bucket is empty; only the size differs, and the size was never a constant.

**Preconditions.**
- `REDIS_URL` and `FORWARDED_ALLOW_IPS` are loaded at boot. `FORWARDED_ALLOW_IPS` must not be `*`.
- The application runs behind exactly one proxy, the ALB, with `--proxy-headers` and an explicit
  `--forwarded-allow-ips`.
- Every bucket value is configuration, not a literal.

**Happy path.**
1. A request arrives at a limited endpoint.
2. The real client address is taken from `X-Forwarded-For`, counting from the right and skipping
   exactly one trusted proxy — **not the leftmost entry, which a client can forge by sending its own
   header.**
3. The Lua script refills and decrements the per-IP bucket, and the per-user bucket where the request
   is authenticated.
4. Both had a token. The request proceeds.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Either bucket is empty | 429 `RATE_LIMITED` with a `Retry-After` header in seconds, computed from that bucket's refill rate | "Too many requests. Try again in 3 seconds." |
| 2 | Redis is unreachable | 503 `DEPENDENCY_UNAVAILABLE` — never unlimited access | "That is unavailable right now. Try again in a few minutes." |
| 3 | A request carries a forged `X-Forwarded-For` | the forged entries are ignored; the request is counted in the bucket for its real peer | *(the limit applies as normal)* |
| 4 | A retry carries an already-seen `Idempotency-Key` | it still consumes a token — it is a real request arriving at the server | *(no user-facing surface unless the bucket empties)* |
| 5 | `FORWARDED_ALLOW_IPS` is set to `*` | the process exits non-zero at boot | *(no user-facing surface — the application does not start)* |
| 6 | A warm-up sign-in in `scripts/stress_seats.py` is refused with 429 | the script **waits the `Retry-After` and retries the same sign-in**; it does not fail, and it does not skip that customer. The warm-up is untimed, so waiting costs the proof nothing | *(no user-facing surface — this is a build gate)* |
| 7 | A request inside the **measured** window is refused with 429 | the script exits non-zero and the run is **void**, not degraded. A 429 there means the run measured the limiter instead of the lock | *(no user-facing surface — this is a stop-the-line finding)* |
| 8 | The script cannot read `RATE_LIMIT_LOGIN_IP_PER_15MIN` or `RATE_LIMIT_HOLD_IP_PER_MIN` to print them | it exits non-zero before the warm-up. **A run that cannot say what it ran against is not evidence** | *(no user-facing surface — this is a build gate)* |

**Server-side validation.** The bucket key is the user id or the resolved client address, both
server-derived. Nothing client-supplied selects a bucket. **This has a wrong implementation that is
silent**, so it needs its own test: assert that two requests carrying *different* forged
`X-Forwarded-For` values from the same peer are counted in the **same** bucket.

**Worked example.** `Retry-After` is computed, not constant. The seat-hold per-user bucket is 20 per
minute.

```
capacity      20 tokens
refill        20 / 60 s = 0.3333 tokens per second
time to earn one token = 1 / 0.3333 = 3.0 s
Retry-After   ceil(3.0) = 3        → "Try again in 3 seconds."
```

The login per-IP bucket is 30 per 15 minutes:

```
refill        30 / 900 s = 0.0333 tokens per second
time to one   = 30 s      → Retry-After: 30
```

**How the concurrency proof obtains its fifty sessions — the two phases, and the distinction is the
whole answer.** `SRC-002 §9.1` and `FR-ADR-034` require fifty **distinct authenticated** customers
issuing fifty hold requests inside `STRESS_CONCURRENCY_SPREAD_MS`. Every one of those sessions comes
from a sign-in, and sign-in is limited per IP. Fifty sign-ins from the script's one address exceed
`RATE_LIMIT_LOGIN_IP_PER_15MIN` at its default of 30. **Without the split below, the one gate this
project calls never-waivable does not run as written**, so the split is part of the gate rather than a
convenience of the script.

`scripts/stress_seats.py` runs in two phases:

1. **A warm-up, untimed and unmeasured.** It signs in fifty seeded customers (`P-XCT-32`'s
   deterministic addresses, `P-XCT-32`'s one password) through the **real** sign-in endpoint — no test
   hook, no injected token, no bypass — and holds their access tokens in memory. **Nothing about the
   warm-up is part of the proof**: not its wall time, not its request count, not its failures, which
   are retried rather than reported.
2. **The measured window.** Fifty concurrent hold requests for one seat, each carrying a token the
   warm-up already holds. **The measured window issues zero sign-ins**, so the login bucket cannot
   affect the result the gate asserts. The only bucket it touches is the per-IP hold bucket, which
   this row already configures to permit the run.

**Each of the fifty customers makes exactly one hold**, so the per-user hold bucket — 20 a minute —
is at one twentieth of its capacity and is never near its limit. **Only the per-IP hold bucket needs
the configured allowance**, and only the per-IP login bucket affects how long the warm-up takes.

**The script prints both configured bucket values in its run output**, before the warm-up starts:
`RATE_LIMIT_LOGIN_IP_PER_15MIN` and `RATE_LIMIT_HOLD_IP_PER_MIN`, read from the environment under
test. A run therefore records what it ran against, and a reader can tell a real green from a green
obtained by turning something off. **An undated, unlabelled "the stress test passed" is not
evidence** — the same standard `P-XCT-01` applies to the red-proof drill.

**And it runs even if the operator changes nothing.** The bucket is a refilling token bucket, so a
refused warm-up sign-in is a wait rather than a failure (exception 6 above). The arithmetic, at the
**unchanged** default:

```
fifty sign-ins from one address, RATE_LIMIT_LOGIN_IP_PER_15MIN = 30 (unchanged)
  first 30 sign-ins    ... immediate, the bucket starts full
  remaining 20         ... one token every 1 / 0.0333 = 30 s
  warm-up wall time    ... 20 x 30 s = 600 s = 10 minutes
  measured window      ... unaffected: 0 sign-ins, 50 holds inside 100 ms
```

So the gate runs under either configuration, and raising the bucket only makes the warm-up quick.
**Under neither configuration is a control disabled and no quality check is waived** — waiving one is
reserved to the client, and this decision does not touch that.

**The bucket values are estimates, not measurements.** They are named configuration, and Phase 7's
load test replaces them with observed numbers.

---

### `P-XCT-08` · Cache the seat map and the listings cache-aside, deleting after commit · `RULED`
`[SRC: SRC-002 §8.2.1 · SRC-002 §8.2.2 · SRC-002 §8.2.3 · SRC-001 §3.3 · FR-ADR-030]`
`[BRD: R-QLY-03]`

**Behaviour.** Cache-aside in Redis. The seat map is keyed `cache:seatmap:{showtime_id}` with a
10-second TTL; the movie and showtime lists have a 60-second TTL. **Invalidation is a `DEL` issued
after the booking transaction commits and after the Redis locks are released — never a `SET` of the
new value.** A per-key rebuild lock prevents a stampede.

**Who may do it.** No role. The cache is invisible to every caller. A cache outage is a cache miss:
reads fall through to PostgreSQL and **the movie list and the showtime list keep working**, slower.
**The seat-map read is the one exception**, and it is not a cache property: that read is rate-limited
(`FR-ADR-058`) and the limiter runs **before** the cache, so a Redis outage returns 503 there before
the fallback is ever reached. See `P-XCT-09`.

**Why the listings are the exception, and why the exception is not a hole in the rule.** A `DEL`
names a key. The seat map has exactly one key per showtime, so naming it is possible and the rule
above applies without qualification. **The listings are cached per filter combination, and a
combination is chosen by the caller**, so the key set is unbounded and **no `DEL` can name it** — an
invalidation that cannot enumerate what it must delete is not an invalidation, it is a hope. The
listings are therefore made unreachable rather than deleted: a generation value is embedded in every
listings key and an admin write that can change a listing moves it forward, after its transaction
commits. Old keys are then read by nobody and expire on their own `LISTING_CACHE_TTL_SECONDS`. **This
is the same idea as the `DEL`, not a relaxation of it** — make the old entry unreachable, never
overwrite it with a value the writer computed — and it is why a `SET` of the new value stays forbidden
here as everywhere: **the generation value publishes no content**, so it cannot be the stale value a
slower reader wrote. **The key format, the counter's name, the list of writes that move it and the
exception paths when the move fails are `P-BRW-12`'s and are written there once**; this row owns
single-key invalidation and the rule they are both instances of, and restates none of it.

**Preconditions.**
- `SEATMAP_CACHE_TTL_SECONDS`, `LISTING_CACHE_TTL_SECONDS` and `CACHE_REBUILD_LOCK_TTL_MS` are
  loaded at boot.
- The code carries a comment at the stampede site naming the scenario, as `SRC-002 §8.2.3` requires.

**Happy path.**
1. A read arrives. The cache is checked.
2. On a hit, the cached map is returned and the caller's own held seats are overlaid client-side from
   the hold token.
3. On a miss, one caller acquires `cache:seatmap:{id}:rebuild` with
   `SET NX PX <CACHE_REBUILD_LOCK_TTL_MS>` (default `2000`, never a literal), rebuilds from
   PostgreSQL, and writes the entry with its TTL.
4. A booking, a hold or a release commits. **After** the commit and **after** the lock release, a
   `DEL` is issued for that showtime's key.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The `DEL` fails | nothing is retried and nothing is rolled back; the entry expires within 10 seconds | *(no user-facing surface — a bounded, stated staleness)* |
| 2 | A caller does not get the rebuild lock | it waits briefly and re-reads the cache; on a second miss it reads PostgreSQL directly | *(no user-facing surface — nobody blocks on a lock they cannot get)* |
| 3 | Redis is unreachable | every read is a miss and falls through to PostgreSQL — **except the seat-map read, which is rate-limited and returns 503 before the fallback is reached** (`P-XCT-09`) | *(the movie and showtime lists work, slower; the seat map is unavailable)* |
| 4 | The map showed a seat as available and it has gone | the customer loses at the Redis lock or at the unique constraint | "C12 was taken by another customer." |

**Server-side validation.** None — the cache carries no user input. **Staleness never causes an
oversell.** The cache affects what someone sees, never what they get.

**Worked example.** Worst-case staleness, with the arithmetic.

```
seat-map cache TTL ............... 10 s      SEATMAP_CACHE_TTL_SECONDS
+ client poll interval ...........  3 s      SEATMAP_POLL_INTERVAL_SECONDS
= worst case a customer sees ..... 13 s
```

The 10 seconds is the ceiling for a **failed** `DEL`; a successful one takes effect immediately. The
3 seconds is the gap before the client asks again. `SRC-001 §3.3` asks for accuracy "within a few
seconds" and 13 is at the edge of that. It is stated rather than rounded down, and it is the number
to revisit if the client finds the map feels wrong.

---

### `P-XCT-09` · Behave differently for each of Redis's three jobs when Redis is gone · `RULED`
`[SRC: SRC-002 §7.9 · SRC-002 §7.4 · SRC-002 §8.2.1 · SRC-002 §5.2.3 · FR-ADR-028]`
`[BRD: R-QLY-03]`

**Behaviour.** Redis does three jobs and they have three different consequences. **Locks fail
loudly** — 503, never a fallback to the database for locking. **The cache degrades silently** to
PostgreSQL. **The rate limiter fails closed** — 503, not unlimited. And **`/health/ready` still
returns 503**, exactly as `SRC-002 §7.4` requires.

**The three jobs are not independent, and the order they run in decides one case.** The limiter runs
**before** the cache, so on a rate-limited endpoint the request never reaches the fallback the cache
would otherwise have provided. `FR-ADR-058` rate-limits the **seat-map read**
(`RATE_LIMIT_SEATMAP_IP_PER_MIN`), so **a seat-map read while Redis is unreachable returns 503
`DEPENDENCY_UNAVAILABLE`** — not 200 from PostgreSQL. `FR-ADR-028`'s "browsing keeps working" remains
true, and remains true exactly where it is not rate-limited: **the movie list and the showtime list
still fall through to PostgreSQL and still return 200.**

**The conflict this resolves, stated rather than left standing.** `FR-ADR-028` (the cache degrades to
PostgreSQL) and `FR-ADR-058` (the limiter fails closed) are both `APPROVED` and both reach the
seat-map read; **503 wins**, because the limiter runs first and because 503 is the stricter of the two
options, and adopting a stricter option needs no signature (`CONSTITUTION.md` Art III.10).

**Who may do it.** No role. This is the system's response to a dependency outage.

**Preconditions.**
- The Redis client has explicit connect and command timeouts. A default of no timeout turns an
  unreachable node into hung requests rather than a 503, and hung requests exhaust the connection
  pool.
- The failure path touches nothing that can fail. A Redis failure caught in an `except` block must
  not read Redis again to build the error message or to log.

**Happy path.** *(the degraded path is the specification here)*
1. Redis becomes unreachable.
2. Hold and confirm return 503 `DEPENDENCY_UNAVAILABLE` immediately, on the configured timeout.
3. The movie list, the showtime list and a customer's own bookings continue, served from PostgreSQL.
   **The seat-map read does not**, because it is rate-limited and the limiter fails closed.
4. Limited endpoints return 503 — **including the seat-map read**.
5. `/health/ready` returns 503 within `READINESS_CACHE_TTL_SECONDS`, and the load balancer removes
   the instance.

**Corrected 2026-08-23 — the hold-outage copy contradicted step 3 of this very walk.** The
published string read *"You can still look at showtimes and seat maps"* in all thirteen places it
appeared, while step 3 above and exception row 2 both say the seat-map read returns **503 in this
same outage**. The sentence was reassuring the customer about the one surface that is definitely
down. It now reads *"You can still browse showtimes"* — the phrasing `P-BRW-12` already used
correctly for the seat-map failure, and true because the movie list, the showtime list and a
customer's own bookings are served from PostgreSQL. **Both halves of the contradiction passed their
own tests**, which is why reading one row at a time never found it.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Hold or confirm while Redis is down | 503 `DEPENDENCY_UNAVAILABLE` | "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes." |
| 2 | A seat-map read while Redis is down | **503 `DEPENDENCY_UNAVAILABLE`** — the read is rate-limited, the limiter runs before the cache, and it fails closed. The PostgreSQL fallback is never reached | **the string owned by `P-BRW-12`. This row publishes none for this case** — see the note below |
| 3 | A limited endpoint while Redis is down | 503 `DEPENDENCY_UNAVAILABLE` | "That is unavailable right now. Try again in a few minutes." |
| 4 | Redis restarts | every live hold is lost; those customers re-select | "Your seats were released. Choose them again if they are still free." |
| 5 | Code falls back to the database for locking | forbidden — a defect, caught in review, not a runtime path | *(no user-facing surface)* |
| 6 | A movie-list or showtime-list read while Redis is down | **200**, served from PostgreSQL — these are not rate-limited, so `FR-ADR-028`'s degradation applies to them exactly as written | *(nothing — the lists render, slower)* |

**Who owns the sentence in row 2, and why this row stopped publishing one.** `P-BRW-12` **owns the
customer-facing message set for `DEPENDENCY_UNAVAILABLE` on the seat-map read**, and it says so on
itself, in the form `P-HLD-14` uses for the hold codes. It is where the underlying conflict was
adjudicated, so the sentence and the situation are decided in the same place. **This row and
`P-BRW-12` are both rank 2 under `S1.2`, which has no tie-break between two rank-2 rows** — and the
two had drifted, along with `SCR-BRW-03`, into three different sentences for one situation. Declaring
an owner is what resolves that; restating the owner's string here would only recreate the third copy.
**Row 3's sentence below is still this row's**: it covers every *other* limited endpoint, which
`P-BRW-12` does not reach.

**Server-side validation.** None. **The consequence is stated rather than softened:** with one EC2
instance, a Redis outage removes the only instance from the load balancer, so browsing is down
regardless of what the application would have served. That is the ruled behaviour and softening
readiness to keep a degraded site up would hide the outage the clause exists to reveal.

**Worked example.** Why the cache behaviour still matters even though readiness will pull the
instance — and where the limiter overrides it:

```
t = 0.0 s   Redis becomes unreachable
t = 0.4 s   a movie-list read arrives → not rate-limited → cache miss → PostgreSQL → 200
t = 0.5 s   a seat-map read arrives   → rate-limited → the bucket cannot be evaluated
                                      → 503 DEPENDENCY_UNAVAILABLE  (the fallback is never reached)
t = 0.6 s   a hold request arrives    → 503 DEPENDENCY_UNAVAILABLE
t ≤ 3.0 s   the cached readiness result expires; the next probe returns 503
t = 3–30 s  the load balancer's unhealthy threshold is reached and the instance is removed
```

There is a window of seconds in which requests arrive at an instance that has lost Redis, and a
longer window during a partial failure where some commands time out and others succeed. **The
listings continuing to work in that window** is what makes the failure a partial outage rather than a
corruption; the seat map is not part of that, and saying so is the point of the two lines above.
**These interval figures are reasoned, not observed** — the load balancer's thresholds are Zone C
values the client sets.

---

### `P-XCT-10` · Serve `/health/live` and `/health/ready` with deliberately different behaviour · `RULED`
`[SRC: SRC-002 §7.4 · SRC-002 §6.2.3 · SRC-002 §6.4.2 · FR-ADR-055 · FR-ADR-041]`
`[BRD: R-QLY-03 · R-CON-07]`

**Behaviour.** **`/health/live` touches nothing** — no database query, no Redis command, no disk, no
network — and returns 200 with a fixed body. **`/health/ready` checks PostgreSQL with `SELECT 1` and
Redis with `PING`, both with a short timeout, and returns 503 when either is unreachable**, with a
body naming which one. SQS, SES and S3 are deliberately not probed.

**Who may do it.** Public. Neither endpoint is authenticated and neither returns anything sensitive:
no version, no hostname, no connection string. `PAYMENT_PROVIDER` is the one deliberate disclosure —
an operator must be able to tell whether the payments are real without going through checkout, and it
is not a secret.

**Preconditions.**
- Both endpoints are Zone B files, every line carrying a comment saying what breaks without it —
  including, on `/health/live`, a comment saying why it deliberately does nothing.
- `READINESS_CACHE_TTL_SECONDS` is loaded.

**Happy path.**
1. The load balancer polls `/health/ready`. The cached result is fresh and reports both dependencies
   reachable. 200.
2. A container-level restart check polls `/health/live`. The process is running. 200.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | PostgreSQL is unreachable | `/health/ready` 503 naming `postgres`; `/health/live` still 200 | *(operator-facing only)* |
| 2 | Redis is unreachable | `/health/ready` 503 naming `redis`; `/health/live` still 200 | *(operator-facing only)* |
| 3 | Both are unreachable | `/health/ready` 503 naming both | *(operator-facing only)* |
| 4 | The readiness check hangs | it fails fast on its own timeout rather than timing out at the caller | *(operator-facing only)* |
| 5 | SES, SQS or S3 is unavailable | `/health/ready` still 200 — the API serves almost every request without them | *(nothing — booking still works; only the receipt send is delayed)* |
| 6 | A restart check is wired to `/health/ready` | every dependency blip restarts every container | *(a restart loop — this is the mistake the split exists to prevent)* |

**Server-side validation.** None. **Which endpoint goes where is Zone C and the client wires it.** The
specification in `docs/30 Deployment/` must say plainly: **the load balancer's target group health
check points at `/health/ready`; any container-level restart check points at `/health/live`.** Getting
them the wrong way round turns a recoverable dependency outage into a restart loop.

**Worked example.** The readiness cache interval and the load balancer's health check interval
interact, and the relationship must be stated in the Zone C specification.

```
READINESS_CACHE_TTL_SECONDS ............ 3 s
load balancer health check interval .... 10 s   (Zone C, the client sets it)
unhealthy threshold .................... 2 consecutive failures
worst case from outage to removal ...... 3 + (2 × 10) = 23 s
```

If the cache interval is ever longer than the unhealthy-threshold window, the load balancer reacts to
stale information. **These are reasoned figures, not observed** — this has never run in AWS.

**The worker has no HTTP surface and exposes neither endpoint.** Its liveness is the process running,
which ECS observes directly. **That is a real gap:** a worker that is running but wedged — not
polling, not failing — looks healthy. It is recorded rather than solved, and queue depth is the
signal that would reveal it.

---

### `P-XCT-11` · Return one error envelope with a stable code, and a request id on 5xx only · `RULED`
`[SRC: SRC-001 §5.2.6 · SRC-001 §8.2 · SRC-002 §2.2 · SRC-002 §7.6 · FR-ADR-052]`
`[BRD: R-CON-02]`

**Behaviour.** Every endpoint returns the same error envelope. **The interface branches on `code`,
never on `message`.** `request_id` is on every error response and is **shown to the customer on 5xx
only**.

```json
{"error":{"code":"SEAT_UNAVAILABLE","message":"…","details":{},"request_id":"a1b2c3d4"}}
```

**Who may do it.** No role. This is the shape of every failure the product can produce.

**Preconditions.**
- The request id exists in the request context before any handler runs.
- The framework's own validation error shape is replaced by this envelope; a default 422 body would
  break the contract on exactly the errors a form hits most.

**Happy path.** *(the failure path is the specification here)*
1. A handler raises a domain failure carrying a registry code.
2. The exception handler renders the envelope with that code, a literal message, optional structured
   `details`, and the request id.
3. The status code is the one the registry fixes for that code.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Any unhandled exception | 500 `INTERNAL_ERROR`, generic message, stack trace in the log only | "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| 2 | A request body fails validation | 422 `VALIDATION_FAILED` with the failing fields in `details` | *(the field's own message, beside the field)* |
| 3 | A path or resource does not exist for **any** method | 404 `NOT_FOUND` | "That page does not exist." |
| 3a | A path exists for some method but **not the one used**. Two cases: a `DELETE` addressed at one of the never-deleted entities, for which no `DELETE` route is mounted; and **any non-`GET` method addressed at a path on the read-only reports router** (`P-RPT-09`), every route of which is a `GET` | 405 `METHOD_NOT_ALLOWED`, rendered by **a global handler and not by any route** | "That action is not available. Nothing was changed." |
| 4 | A signed-in user reaches a router their role does not permit | 403 `FORBIDDEN` | "This account does not have access to that page." |
| 5 | A unique-constraint violation on seat occupancy | 409 `SEAT_UNAVAILABLE` — **not** `INTERNAL_ERROR`; it is the guard working | "C12 was taken by another customer." |
| 6 | A 4xx of any kind | the envelope carries `request_id`, and the interface does **not** display it | *(no id — it is noise on an error the customer can act on)* |

**The envelope without a route — how a `DELETE` is answered where no `DELETE` route exists.**

**First, the scope, because an earlier revision of this row got it wrong and the wrong version is the
tempting one.** This product is **not** delete-free. `EP-ADM-21` is a mounted `DELETE` on
`/api/admin/seats/{seat_id}`, and a `manager_screen_assignment` row is genuinely removed when an
assignment ends. **The rule below governs the never-deleted set and nothing else:**

| Never deleted — no `DELETE` route is mounted | Genuinely deleted — a `DELETE` route exists and succeeds |
|---|---|
| `movie`, `showtime`, `screen`, `cinema`, and the four lookup vocabularies `language`, `certification`, `genre`, `format` | `seat` (`EP-ADM-21`, permitted only while its hall has no showtime rows at all), and `manager_screen_assignment` |
| withdrawal replaces deletion (`P-ADM-20`, `FR-ADR-012`) | ordinary deletion, guarded by preconditions |

**The distinction is principled and is not an exception list**, and this is the sentence that carries
it: **a route that refuses a real request with a real reason has a case where it succeeds; a route
mounted only to say no does not.** `EP-ADM-21` refuses once a showtime exists and *succeeds* before
then, so it is a real capability with a guard. A `DELETE /api/admin/movies/{id}` would refuse every
caller, every time, forever — **and a route that returns the same refusal to everybody is a route
somebody will later make work.** That is why the absence is the control for the left column and why
the right column is not an inconsistency.

**Now the mechanism.** For the never-deleted set, `FR-ADR-052` still requires one envelope from
**every** response, and the framework's own method-not-allowed body is a different shape. **Both hold
at once through a handler rather than a route:**

- **One global exception handler**, mounted on the application and on no router, renders the
  framework's method-not-allowed as the envelope with `METHOD_NOT_ALLOWED` at **405**. It creates no
  route, it appears in no route table, and it cannot be "made to work" later because there is nothing
  there to make work.
- **The message is generic and entity-blind**, because the handler genuinely does not know what was
  addressed — routing failed before any handler ran, and the path is a string. **A sentence naming the
  entity would be a claim the code cannot support**, which is exactly the defect that produced this
  row: an unmounted route publishing a message it could never emit.
- **Every entity-specific "these are never deleted" sentence belongs on the screen**, in the note each
  admin screen already carries. That is where an admin actually reads it — there is no delete control
  to press, so nobody arrives at this 405 by using the interface. **Reaching it means a client bug or
  a hand-made request**, and the generic sentence is the right answer to both.
- **405 rather than 404**, because the address does exist: the same path serves `GET` and `PATCH`. A
  404 would deny that, and would misreport the situation to the one audience that ever sees it.
- **405 rather than 403**, because nothing about authorisation is involved. An admin has every
  permission the product grants and still gets this answer, so `FORBIDDEN` would name the wrong
  cause — and it would also be indistinguishable from the role check that `P-XCT-05` performs.

**A property of this toolchain that the next lane will otherwise trip over: a `newerrorcode` block
requests a code, it does not grant one.** `VALID_CODES` in `docs/03 PRD/api/generate_api.py` is
derived from two **hardcoded** constants, `REGISTRY_ADR` and `REGISTRY_EXT`, and the generator rejects
any endpoint block naming a code outside that set. **So `METHOD_NOT_ALLOWED` appears in no `errors`
array anywhere, in this section or any other, until the merge owner adds it to the generator's
registry** — a lane that adds it to an endpoint block first does not get a warning, it gets a build
that raises. **The block above is the declaration and the request; the registry entry is the grant**,
and the two are deliberately separate so that no lane can widen the error contract on its own.

**Server-side validation.** Nothing internal leaks: no stack trace, no SQL, no exception class, no
hostname, no table name. Three wording rules bind every message: **say what happened, not how it
felt**; **say what to do next where there is something to do**; **never blame the customer for a race
they lost.** **The 405 sentence deliberately has no "what to do next"** — there is nothing to do,
because the action does not exist and never will.

**Worked example.** The same HTTP status carries five different failures, which is why the interface
must branch on `code`:

```
409 SEAT_UNAVAILABLE       → name the lost seats, mark them sold, keep the rest of the selection
409 HOLD_EXPIRED           → return to the seat map with the selection re-applied
409 SALES_CLOSED           → disable the map and say sales have closed
409 IDEMPOTENCY_IN_FLIGHT  → wait and retry with the same key
409 VERSION_CONFLICT       → reload the record and re-apply the edit
```

Branching on `409` alone produces one screen for five situations.

---

### `P-XCT-12` · Emit JSON logs to stdout with a request id we generate · `RULED`
`[SRC: SRC-002 §5.4.5 · SRC-002 §7.6 · SRC-002 §7.3 · SRC-002 §5.2.6 · FR-ADR-056]`
`[BRD: R-CON-02 · R-QLY-08]`

**Behaviour.** JSON, one object per line, to stdout. **Never a file on disk.** One request id per
request, **generated by us** — an inbound `X-Request-Id` is never trusted — returned in the response
`X-Request-Id` header, and propagated into every worker job through the message payload.

**The request id's format, because roughly forty published strings end `If you need help, quote
a1b2c3d4.` and an example is not a specification.** It is **eight lowercase hexadecimal characters**,
`[0-9a-f]{8}`, generated per request from a random source. `a1b2c3d4` in every published string is
that format and not a placeholder for something longer.

| Where it appears | As |
|---|---|
| the JSON log line | the `request_id` field, on every line for that request, in both processes |
| the error envelope | `error.request_id`, on every error response, 4xx and 5xx alike (`P-XCT-11`) |
| the response header | `X-Request-Id`, on every response |
| the customer's screen | **5xx only**, quoted in the sentence — `P-XCT-11` exception 6 keeps it off 4xx |

**Eight characters is a length chosen for the one thing that makes it observable: a person reads it
aloud down a telephone, or types it from a screen into a message.** A 36-character UUID is a
different product experience, not a longer one — it is read wrong, transcribed wrong, and it takes the
whole width of a small screen in the middle of a sentence about a failed booking. Eight hexadecimal
characters are two groups of four and survive being read out.

**What that costs, stated rather than glossed:** eight hex characters is 4,294,967,296 values, so **it
is not unique and is not treated as one.** By the birthday bound two ids collide with probability
about a half once roughly 77,000 have been issued, which this product will pass. **It is a correlation
aid, never a key**: nothing joins on it, no column is unique on it, and an operator searching it
narrows by time window and by log group as well. **If it were ever used as an identifier this length
would be wrong**, and the rule is written here so that use is a deliberate change rather than a
discovery.

**Who may do it.** No role. Every process logs this way: the API, the worker, and the migration run.

**Preconditions.**
- `LOG_LEVEL` is loaded; the default is `INFO` in every environment.
- A redaction filter is installed on the logging pipeline, applying a denylist of field names
  centrally.
- The outbox row carries the originating `request_id`.

**Happy path.**
1. A request arrives. A fresh id is generated. If the client sent one it is recorded as
   `client_request_id`, a separate field, never the one used for correlation.
2. Every log line for that request carries `request_id`, plus `timestamp`, `level`, `logger`,
   `message`, `service` and `instance_id`.
3. One `INFO` line is written per completed request, with route, status and duration.
4. The booking's outbox row carries the same `request_id`; it travels in the queue message and is
   bound to the worker's logging context for the whole job.
5. One search across the log group answers "what happened to this booking" end to end.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A client sends its own `X-Request-Id` | it is recorded as `client_request_id` and ignored for correlation | *(no user-facing surface)* |
| 2 | An unhandled exception | `ERROR` with a stack trace **in the log**, never in the response | "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| 3 | A `SEAT_UNAVAILABLE` outcome | `INFO` with a counter, **not** `WARNING` — logging correct behaviour as a warning trains the operator to ignore warnings | *(no user-facing surface)* |
| 4 | A health check is polled | not logged at `INFO`; failures are logged | *(no user-facing surface)* |
| 5 | A field on the denylist appears in a log call | it is redacted centrally, not at the call site | *(no user-facing surface)* |

**Server-side validation.** **Never logged, at any level:** no card data ever — there is none in the
system and the rule stays stated so nobody adds a card-shaped log field out of habit; no password, no
password hash, no JWT, no session cookie, no `Authorization` header; **no booking reference in a line
that also carries the customer's email**, because together they are enough to walk into a hall; no
resolved secret values; no full request bodies.

**Worked example.** One booking, two processes, one search key.

```
{"timestamp":"2026-08-14T14:07:11.204Z","level":"INFO","service":"api","instance_id":"i-3f",
 "request_id":"a1b2c3d4","route":"/api/bookings","method":"POST","status_code":201,
 "duration_ms":812,"booking_id":9008}

{"timestamp":"2026-08-14T14:07:13.881Z","level":"INFO","service":"worker","instance_id":"w-91",
 "request_id":"a1b2c3d4","job_id":"7c2e","booking_id":9008,"message":"receipt sent"}
```

Searching `request_id = a1b2c3d4` returns both halves. Without the propagation, the second line would
be unfindable from the first.

**The single most important consequence, and it is Zone C.** **Container stdout dies with the
container unless a log driver is configured.** With the default driver, the record of a crash loop is
destroyed by the restart that caused it. Configuring the `awslogs` driver is the client's work, it
needs a prep-queue row with a needed-by phase of Phase 1, and **without it this entire specification
delivers nothing.**

---

### `P-XCT-13` · Expose `/metrics` in Prometheus format, and say that nothing scrapes it · `RULED`
`[SRC: SRC-002 §7.7 · SRC-002 §5.3 · SRC-002 §4.12 · FR-ADR-057]`
`[BRD: R-CON-04]`

**Behaviour.** A `/metrics` endpoint in Prometheus format, exposing request counts, latency, seat lock
counts and queue depth, plus four more the product's own failures need. It is a Phase 7 deliverable.
**Nothing in the approved stack scrapes it**, and that is said plainly rather than absorbed.

**Who may do it.** Nobody through the load balancer. **`/metrics` is not exposed through the ALB** —
it is served on the container's port and reachable from the host. It discloses traffic volumes and
internal route names and has no authentication in front of it. **Restricting the route is Zone C**, so
the specification must say that no listener rule routes `/metrics` and say what is disclosed if one
does.

**Preconditions.**
- The API runs a **single uvicorn worker per container**. Multiple workers would each hold their own
  counters and a scrape would return one worker's view, which is a wrong number.
- The worker exposes its own `/metrics` on a small HTTP listener, because worker-side counters have
  nowhere else to go. **That listener binds `WORKER_METRICS_PORT`, default `8001`** (`S7.9`), which is
  above 1024 for the same non-root reason as `API_PORT` and must differ from it, or whichever process
  starts second fails to bind and dies. **No listener rule routes it**, and nothing outside the host
  reaches it.

**Happy path.**
1. An operator with a terminal requests `/metrics` on the container's port during an incident.
2. The endpoint returns the current values in Prometheus text format.

| Metric | Type |
|---|---|
| `http_requests_total{route,method,status}` | counter |
| `http_request_duration_seconds{route}` | histogram |
| `seat_locks_held` | gauge |
| `queue_depth` | gauge |
| `seat_conflicts_total` | counter |
| `booking_confirmations_total{outcome}` | counter |
| `receipt_dispatch_total{outcome}` | counter |
| `outbox_pending` | gauge |

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A listener rule routes `/metrics` through the load balancer | the endpoint is publicly readable | *(traffic volumes and internal route names are disclosed to anyone)* |
| 2 | `seat_locks_held` is read by scanning Redis | rejected — the value comes from a Redis counter maintained by the acquire and release paths, O(1) per operation | *(a scan per scrape costs more under load than the traffic it measures)* |
| 3 | The counter drifts because a lock expired without a release | it is reconciled by a bounded `SCAN` on the worker's **existing** loop, at a long interval — **not on a schedule, because there is none** | *(no user-facing surface)* |
| 4 | SQS is unreachable when `queue_depth` is read | the last cached value is returned with its age; the scrape does not become an AWS API call each time | *(no user-facing surface)* |

**Server-side validation.** None. **The gap, stated:** nothing scrapes this endpoint, nothing stores
its history, nothing alerts on it. The one ruled alarm uses a different mechanism entirely and does
not read `/metrics`. What the endpoint is good for today is an operator with a terminal seeing the
numbers now, which against `SRC-001 §8.2` is genuinely useful and is much less than monitoring.
Adding Prometheus, Grafana Cloud or the CloudWatch agent's Prometheus scrape is a new managed service
and needs the client's permission first. **It is not added, and it is not designed around.**

---

### `P-XCT-14` · Alarm on one thing, and print the list of what nobody is watching · `RULED`
`[SRC: SRC-003 OPEN-OPS-01 · SRC-003 OPEN-NAME-01 · SRC-001 §8.2 · FR-ADR-068 · FR-ADR-049]`
`[BRD: R-CON-04]`

**Behaviour.** **One alarm:** CloudWatch on the ECS service's running task count below 1, delivering
through SNS to the operator's own address. The alarm, the topic and the subscription are Zone C — the
client builds all three. **The list of what nobody is watching is written down honestly**, worst
first.

**Who may do it.** The client. There is one operator and no backup decider, stated affirmatively
rather than left blank. **There is no escalation path and there cannot be.** If the alert email is
not read, nothing else happens.

**Preconditions.**
- The address is never committed. This repository is not the place for it; it lives in the SNS
  subscription the client creates and in local `.env`.
- The specification states one thing the alarm is useless without: **set missing data to
  `breaching`.** If the service is deleted or the metric stops being published, the default treatment
  leaves the alarm in `INSUFFICIENT_DATA` and it never fires. An alarm that stays quiet when the
  thing it watches disappears is worse than no alarm, because it is believed.

**Happy path.**
1. The service stops running.
2. The metric falls below 1 for the evaluation period.
3. SNS delivers an email to the operator.
4. Acceptance criterion: stop the service, receive an email.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The application is running and every request returns 500 | **nothing fires.** A running but broken application is invisible today | *(no notification of any kind)* |
| 2 | A customer's receipt fails repeatedly and lands in the dead letter queue | **nothing fires.** That customer has paid and cannot enter the hall | *(no notification of any kind)* |
| 3 | The service is deleted and missing data is left at its default | the alarm sits in `INSUFFICIENT_DATA` and never fires | *(no notification of any kind)* |
| 4 | Six more alarms are added because they are obviously useful | forbidden — alarms are Zone C and adding scope nobody asked for is two breaches in one move | *(no user-facing surface)* |

**Server-side validation.** None — this is infrastructure the client builds. **The unwatched list,
worst first:**

| Not watched | What it would catch |
|---|---|
| **Dead letter queue depth** | **a customer paid and their receipt never sent** |
| 5xx rate at the load balancer | the application failing while its task is still running |
| Target group unhealthy hosts | readiness failing on PostgreSQL or Redis |
| RDS free storage | forever retention filling 20 GB |
| **S3 poster-bucket size and object count** | **the one store in the product with no deletion path at all filling up.** A replaced poster object is never deleted (`P-ADM-20`, `FR-ADR-012`), so the bucket **grows monotonically** — every re-upload adds a key and removes none — and nothing anywhere reads its size. **The first symptom is a failed poster upload**, which an admin meets mid-task with no warning that anything was filling |
| RDS connection count | pool exhaustion against roughly 110 connections |
| Host memory | a container killed for exceeding its limit |
| SES bounce and complaint rate | receipts going nowhere |
| `outbox_pending` rising | the relay stuck, receipts not enqueued |

**The bucket was missing from this list, and the omission had a shape worth naming.** Every other row
here names a store that something else bounds — RDS has a provisioned size, CloudWatch has a
retention setting, ECR has a lifecycle policy the specification already asks for. **S3 is the only one
with no deletion path and no bound**, which makes it the row most in need of a watcher and it was the
row that was absent. It is added rather than solved: **no lifecycle policy is proposed and no
retention is chosen**, because deleting a poster object would contradict `P-ADM-20` and because
choosing a cost-against-evidence trade is the client's, exactly as the CloudWatch retention period is.

**The first is the worst, and it is named:** the product's central promise is that a customer receives
a receipt that gets them into a hall; when that fails repeatedly the message lands in the dead letter
queue and nothing looks there. **A dead letter queue alarm is the single most valuable thing the
client could add. It is recommended in writing and it is not adopted** — one alarm was ruled, and
adding more is the client's call, not a stricter version of theirs.

---

### `P-XCT-15` · Load every setting from the environment and crash at boot when one is missing · `RULED`
`[SRC: SRC-002 §7.1 · SRC-002 §6.2.4 · SRC-002 §6.2.6 · SRC-002 §13.4 · FR-ADR-053]`
`[BRD: R-CON-01 · R-CON-07]`

**Behaviour.** Every setting comes from an environment variable. There are no configuration files and
no hardcoded environment names. **Validation runs at import time, before the application accepts a
request, and a failure exits non-zero with a message naming the variable.** Not a warning, not a log
line, not a lazy failure on first use.

**Who may do it.** The operator sets the values. In AWS they arrive through the ECS task definition,
which is Zone C.

**Preconditions.**
- The complete variable inventory is in S7 §9 and is the input to the Zone C specification.
- `.env.example` is complete and current, with a comment per variable saying what it does and what
  breaks without it, and placeholder values that are obviously placeholders. **No real value and no
  credential.**

**Happy path.**
1. The process starts.
2. Every variable is read, coerced to its type and validated.
3. The **thirteen** cross-field checks run, in the order S7.9 lists them. *(Corrected 2026-08-23:
   this read twelve while S7.9's own table numbers thirteen. Row 13 is the mail-transport check,
   `MAIL_PROVIDER` exactly `ses` or `stub` — without which row 8 never fires and receipts fail
   silently, so an implementation built to the stale count drops precisely the check that hides
   its own absence.)*
4. The resolved configuration is logged once, with secret values redacted. `PAYMENT_PROVIDER` is
   logged prominently, because it is the flag that says whether the payments are real.
5. The application begins accepting requests.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A required variable with no default is missing | exit non-zero, naming the variable | *(no user-facing surface — the container never becomes healthy)* |
| 2 | A variable fails its type or bound | exit non-zero, naming the variable and the bound | *(no user-facing surface)* |
| 3 | `PAYMENT_SIMULATED_DELAY_MS` is not well under `SEAT_HOLD_TTL_SECONDS` | exit non-zero | *(no user-facing surface — otherwise a customer pays for expired seats)* |
| 4 | `CURRENCY_MINOR_UNIT_RATIO` is not `100` while `CURRENCY_CODE` is `INR` | exit non-zero | *(no user-facing surface)* |
| 5 | `CINEMA_TIMEZONE` does not resolve in the zone database | exit non-zero | *(no user-facing surface — otherwise it fails at the first date comparison)* |
| 6 | A variable is given a "sensible default" so the app starts locally | forbidden — it produces the worst deployment failure: a container that starts, connects to nothing, and reports healthy | *(no user-facing surface)* |

**Server-side validation.** Types, bounds and the cross-field checks in S7 §9. Every declaration in
the Zone B configuration file carries a comment saying what breaks if the variable is wrong or
absent. **A missing variable makes the dependent story `Blocked`, never stubbed.**

**Worked example.** The delay-against-hold check, with real numbers:

```
SEAT_HOLD_TTL_SECONDS      = 180        → 180000 ms
PAYMENT_SIMULATED_DELAY_MS = 1500       → 0.83% of the hold        ACCEPTED
PAYMENT_SIMULATED_DELAY_MS = 200000     → longer than the hold     REJECTED at boot
```

The check is `PAYMENT_SIMULATED_DELAY_MS < SEAT_HOLD_TTL_SECONDS × 1000 × 0.1`. A payment step that
outlives the hold is a customer who paid for expired seats, and it fails at boot rather than at
checkout.

---

### `P-XCT-16` · Read secrets from SSM through the task definition, never from the application · `RULED`
`[SRC: SRC-002 §5.4.3 · SRC-002 §5.3 · SRC-002 §13.4 · SRC-002 §6.3.2 · FR-ADR-054]`
`[BRD: R-CON-03 · R-CON-07]`

**Behaviour.** Secrets live in SSM Parameter Store as `SecureString` parameters. **AWS Secrets Manager
is never used.** They reach the container through the ECS task definition's `secrets` block, using
`valueFrom` with the parameter ARN. **The application reads an ordinary environment variable and knows
nothing about SSM** — no AWS SDK call for configuration, no SSM client, no bootstrap fetch, and no IAM
dependency at read time.

**Who may do it.** The client writes the task definition. The build session writes the specification:
which variables are plain and which are secret, the parameter path for each, and the IAM permissions
the execution role needs.

**Preconditions.**
- Parameter naming is `/frontrow/<environment>/<VARIABLE_NAME>`, matching the variable name exactly. A
  parameter whose name differs from the variable it populates is a mapping that gets out of step.
- Encryption uses the AWS-managed key for SSM. A customer-managed KMS key is a per-key monthly charge
  against a zero budget.

**Happy path.**
1. The client stores `JWT_SECRET`, `DATABASE_URL` and — if authenticated — `REDIS_URL` as
   `SecureString` parameters.
2. Every other variable is a plain environment variable in the task definition. A `SecureString` for
   `SEAT_HOLD_TTL_SECONDS` is encryption applied to a number that appears in this document.
3. ECS resolves the parameters at task start and injects them.
4. Locally the same variables come from a `.env` file, so **the code path is identical in both
   environments.**

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The `ssm:GetParameters` permission is on the **task** role instead of the execution role | the task will not start, with an error that does not obviously say why — ECS resolves the parameter **before** the container starts | *(no user-facing surface)* |
| 2 | `kms:Decrypt` on the AWS-managed SSM key is missing | the task will not start | *(no user-facing surface)* |
| 3 | A secret is changed in Parameter Store | nothing changes until a new task deployment — ECS resolves parameters at task start. **That is a deploy, not a configuration reload.** | *(no user-facing surface)* |
| 4 | A credential is committed to the repository | forbidden. `.env` is git-ignored, `.env.example` carries obvious placeholders, and the staged diff is scanned before every push | *(no user-facing surface)* |
| 5 | `JWT_SECRET` is rotated | **every live session is invalidated.** Rotation is manual and there is no rotation mechanism; automatic rotation is a Secrets Manager feature and Secrets Manager is forbidden | "You were signed out. Sign in again to continue." |

**Server-side validation.** The application validates the *values*, not their source. **The build
session's read-only AWS grant permits verifying that the parameters exist and are the right type. It
must never read a `SecureString`'s decrypted value into a log or a document.**

**Worked example.**

```
/frontrow/dev/JWT_SECRET      SecureString  → env JWT_SECRET
/frontrow/dev/DATABASE_URL    SecureString  → env DATABASE_URL   (it carries the password)
SEAT_HOLD_TTL_SECONDS=180                    plain env in the task definition
```

Execution role needs: `ssm:GetParameters` on `/frontrow/*` and `kms:Decrypt` on the AWS-managed SSM
key. **Needed by Phase 1 — nothing deploys without it.**

---

### `P-XCT-17` · Drain on SIGTERM and release this instance's holds through a Redis registry · `RULED`
`[SRC: SRC-002 §7.5 · SRC-002 §7.3 · SRC-002 §8.1.4 · SRC-001 §7.5 · FR-ADR-033]`
`[BRD: R-QLY-07]`

**Behaviour.** On SIGTERM the API stops accepting new requests, drains in-flight ones, releases the
Redis locks of holds this instance granted, and exits. **The registry of those locks is a set in
Redis, not in process memory** — statelessness forbids local state, and a process killed with SIGKILL
after the grace period loses in-memory state before it can act on it.

**Who may do it.** No role. This is the container's shutdown path, and the values that make it work
are Zone C.

**Preconditions.**
- Each API instance generates an id at boot.
- When it grants a hold it adds the hold's keys to `instance:{instance_id}:holds`, with the same
  3-minute TTL as the holds, so an instance that vanishes leaves no permanent garbage.
- `SHUTDOWN_DRAIN_TIMEOUT_SECONDS` is loaded.

**Happy path.**
1. SIGTERM arrives.
2. The instance is deregistered from the load balancer target group and stops accepting new
   connections.
3. It waits out the deregistration delay so in-flight requests that were already routed complete.
4. In-flight requests finish, bounded by the drain timeout.
5. It reads `instance:{instance_id}:holds` and runs the compare-and-delete release for each key.
6. The process exits.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A customer is mid-checkout on a draining instance | their hold is released and they re-select | "Your seats were released. Choose them again if they are still free." |
| 2 | A hold expired and another customer re-acquired the seat during the drain | the token no longer matches and the delete is a no-op — **this cannot free someone else's lock** | *(nothing — the other customer keeps their seat)* |
| 3 | The ECS stop timeout is shorter than the deregistration delay plus the drain timeout | SIGKILL arrives during step 4 and steps 5 and 6 never happen | *(the locks expire in three minutes — correctness is unaffected)* |
| 4 | The release fails entirely | **nothing breaks.** Expiry is the guarantee; release is an optimisation on top of it | *(seats are unbuyable for up to three minutes)* |
| 5 | SIGTERM arrives at the worker | it stops polling, finishes the message it is handling, completes any outbox relay batch in progress, and exits | *(no user-facing surface)* |

**Server-side validation.** None. **Correctness never depends on the release running.** If it fails,
if the grace period is too short, or if the instance is SIGKILLed, the locks expire in three minutes
and no booking is affected. That is the property that makes this safe to get wrong.

**Worked example.** What a deploy during a busy period costs without the release.

```
seats held by the draining instance at that moment .......... 14   (illustrative)
hold TTL .................................................... 180 s
without release: those 14 seats are unbuyable for ........... up to 180 s, with no error anywhere
with release:    they are available within .................. the drain window
```

**The ordering relationship is Zone C and it breaks silently.** The ECS stop timeout must exceed the
deregistration delay plus the drain timeout. The specification must state the three values, their
required ordering, and what breaks if they are wrong. *(reasoned, not observed.)*

---

### `P-XCT-18` · Keep every container stateless · `RULED`
`[SRC: SRC-002 §7.3 · SRC-002 §5.4.5 · SRC-001 §7.5 · FR-ADR-063 · FR-ADR-056 · FR-ADR-061]`
`[BRD: R-QLY-07]`

**Behaviour.** No local session state, no local file writes, no local uploads. **Killing any container
mid-request must not corrupt data.** Both images declare a read-only root filesystem as their intended
runtime mode; enforcing it is Zone C, and a container that needs a writable filesystem has a bug
rather than a configuration problem.

**Who may do it.** No role. This constrains every line of application code.

**Preconditions.**
- Logs go to stdout, never a file.
- Poster uploads stream to S3 and never touch the container's disk.
- The seat selection a guest carries across the sign-in round trip lives in the browser's
  `sessionStorage`, never server-side.
- The per-instance hold registry lives in Redis, not in process memory.
- Both images run as a non-root user created in the Dockerfile.

**Happy path.**
1. A request arrives at any instance. Nothing about it depends on which instance served the previous
   request.
2. The container is killed mid-request. The transaction rolls back. No partial state survives
   anywhere.
3. A replacement container starts and serves the retry identically.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A container is killed between payment capture and commit | the transaction rolls back and **takes the idempotency record with it**, so the retry with the same `Idempotency-Key` inserts cleanly and runs the whole transaction again — one capture, one booking. **The confirm transaction's crash points are `P-PAY-10`'s and this is its crash point 6**; this row states only the statelessness property, that nothing survives the killed container. | *(the retry produces one booking, and the customer sees the ordinary confirmation)* |
| 2 | A container is killed between commit and the queue send | the outbox row is `pending` and the worker's relay sends it on its next loop (`P-PAY-10` crash point 14) | *(the receipt is delayed, not lost)* |
| 3 | Code writes a file to local disk | forbidden — a file is state on a stateless container and it dies with the container | *(no user-facing surface)* |
| 4 | Code holds a session, a hold registry or a rate-limit counter in process memory | forbidden — the rate limiter in particular then multiplies its own limit by the number of processes | *(no user-facing surface, and the limiter appears to work while protecting nothing)* |
| 5 | The container is asked to bind a port below 1024 | it cannot — it runs as a non-root user, and only root may bind a privileged port, so the process exits at boot. **The API listens on `API_PORT`, default `8000`, and the target group points at that** (`S7.9`). The port is a Zone C input: the target group, the security group's ingress rule and the listener rule are all built against it, and the specification owes the client the number while the client wires it | *(no user-facing surface)* |

**Server-side validation.** None. **The test is a real signal, not a unit test:** send SIGKILL to a
running container mid-request and assert that no partial booking, no orphaned payment and no stranded
lock exists afterwards.

**Worked example.** The crash window that statelessness plus idempotency closes:

```
t0  insert idempotency record (status in_progress)   ← the transaction's first act
t1  capture payment through the simulated provider
t2  ✖ container killed
    → transaction rolls back; the idempotency record is gone with it
t3  the customer retries with the same Idempotency-Key
    → the insert succeeds again, the capture runs once, the booking commits
```

Nothing was captured twice, and **the reason is not idempotency on the key** — the record that would
carry the key rolled back too. It is that the simulated provider holds **no external ledger**: the
only record a capture produces is the `payment` row, which is inside the transaction that rolled back,
so nothing was captured anywhere. **`P-PAY-10` owns that reasoning and states what would change if a
real provider were ever introduced** (`FR-ADR-041` rules one out); this row restates neither and
defers to crash point 6.

**This row is a restatement and carries no authority over the confirm transaction.** Where it and
`P-PAY-10` differ, `P-PAY-10` is right. It is written out here only because statelessness is the
property being specified and a reader of this row needs one concrete crash to see it against.

---

### `P-XCT-19` · Run migrations as a separate explicit step, never on boot · `RULED`
`[SRC: SRC-002 §7.8 · SRC-002 §4.7 · SRC-002 §6.2.2 · SRC-002 §6.4.1 · FR-ADR-062]`
`[BRD: R-QLY-07 · R-CON-07]`

**Behaviour.** Alembic. **The application never runs a migration** — not at import, not in a lifespan
hook, not in the entrypoint's default path, and not behind a flag. **There is no code path in the API
or the worker that can apply a migration.** The entrypoint supports an explicit `migrate` command as
its argument; running the image with `api` or `worker` starts a long-running process and never touches
migrations. **`seed` is the fourth command and it is `P-XCT-32`'s** — it is named here only so the
entrypoint's argument set is stated in one place; it runs no migration either.

**Who may do it.** The client, by hand, before updating the service to the new image. In AWS this is a
one-off ECS task using the same image and task definition family with the command overridden to
`migrate`. **That run is Zone C.**

**Preconditions.**
- The migration and the code are the same build, because they are the same image.
- The one-off task needs the same execution role and the same SSM permissions as the service, because
  it reads `DATABASE_URL` the same way.
- The local compose stack creates a restricted application role without superuser.

**Happy path.**
1. Take a manual RDS snapshot.
2. Run the one-off `migrate` task. It runs `alembic upgrade head` and exits with the migration's
   status.
3. Confirm it succeeded.
4. Update the service to the new image.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The migration is forgotten | the service runs against an old schema and fails at the first query touching a new column. **The symptom is a 500, not a startup failure.** | "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| 2 | A migration drops a column the running code still selects | the deploy window becomes an outage. **Every migration must be backwards-compatible with the running code**, because the old code runs against the new schema for that window | as above |
| 3 | Two tasks boot together and both run `alembic upgrade head` | cannot occur — migrations are a separate step. **Alembic does not take an advisory lock**, which is widely believed and is not true, and removing the race is the reason for the rule | *(no user-facing surface)* |
| 4 | A migration works locally and fails on RDS | superuser, forced SSL or the allowed extension list. Building against a restricted role locally catches it on a laptop instead of during a deploy | *(no user-facing surface)* |
| 5 | Someone runs a down-migration | there are none. Alembic's `downgrade` stub stays a stub that raises. **A bad migration is corrected by a new forward migration.** | *(no user-facing surface)* |

**Server-side validation.** None. **Migrations are reviewed for what they lock.** On a `db.t3.micro`
an `ALTER TABLE` that rewrites a large table blocks it for the duration; `audit_log` and the
seat-occupancy table are the tables that grow without bound, and a migration touching either states in
a comment what it locks and for roughly how long.

**Worked example.** The deploy is two steps and the order is one-directional:

```
1  snapshot        (manual, persists beyond the 7-day automated window)
2  migrate         one-off task, same image, command overridden
3  verify          the task exited 0
4  deploy          update the service to the new image
```

Reversing steps 2 and 4 runs new code against an old schema. Skipping step 1 makes step 2
unrecoverable after seven days.

---

### `P-XCT-20` · Back up the database, and rehearse the restore · `RULED`
`[SRC: SRC-003 OPEN-OPS-02 · SRC-001 §7.5 · SRC-001 §7.6 · SRC-002 §5.2.2 · FR-ADR-070 · FR-ADR-012]`
`[BRD: R-QLY-07]`

**Behaviour.** RDS automated backups, enabled, retention **7 days**, which also enables point-in-time
recovery. A **manual snapshot before every migration**. The backup window sits outside the cinema's
busy period. **A restore that has never been rehearsed is not a recovery** — the rehearsal is a Phase
7 runbook deliverable with a recorded outcome and a recorded date.

**Who may do it.** The client. Enabling backups, setting the window and running a restore are all
`aws` commands that create or modify infrastructure, so they are Zone C and the build session performs
none of them.

**Preconditions.**
- Nothing is ever deleted, so the only thing a backup protects against is hardware failure and a bad
  migration.
- Redis is not backed up and does not need to be: it holds locks and cache, both reconstructible or
  expendable.
- S3 posters are not backed up. S3's own durability is the mechanism, nothing deletes a poster, and a
  new poster is a new key.

**Happy path.**
1. Automated backups run in the configured window.
2. A mistake happens at 14:00.
3. Point-in-time recovery restores to 13:59.
4. The application's `DATABASE_URL` is repointed and the service is redeployed.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A corruption is discovered in week three | **not recoverable from an automated backup** — only from a manual snapshot that happened to be taken. Forever retention and a 7-day backup window are different guarantees | *(operator-facing)* |
| 2 | A restore is performed | **it creates a new RDS instance with a new endpoint.** It does not restore in place, so the recovery procedure includes a configuration change and a deploy | *(a downtime window)* |
| 3 | An RDS instance is deleted without a final snapshot | **its automated backups are deleted with it.** A cleanup that removes a database also removes the ability to recover it | *(operator-facing)* |
| 4 | The restore has never been performed | this record describes a backup and not a recovery. The parts that fail are the endpoint change and the configuration, not AWS's snapshot | *(operator-facing)* |
| 5 | Backup storage exceeds the database's own size | it begins to cost against a zero budget | *(operator-facing)* |

**Server-side validation.** None. **The rehearsal's acceptance criterion:** restore to a new instance,
point a local application at it, and confirm that a known booking is present and correct — by booking
reference, seat, and price in paise.

**Worked example.**

```
retention ................... 7 days      (free-tier: backup storage up to the 20 GB provisioned size)
mistake at .................. 14:00:00 Asia/Kolkata
point-in-time recovery to ... 13:59:00 Asia/Kolkata
recovered figure checked .... booking FR-K7M2-QX9B, seats C12 C13, total 56248 paise
```

**Needed by Phase 2** — the first phase that creates data worth losing. Announced now rather than on
the day it blocks.

---

### `P-XCT-21` · Fit three processes inside roughly 1 GB, with explicit limits and measured replacement · `RULED`
`[SRC: SRC-002 §5.4.1 · SRC-002 §5.2.1 · SRC-002 §13.6 · SRC-002 §5.4.2 · SRC-003 OPEN-PROC-01 · FR-ADR-064 · FR-ADR-063]`
`[BRD: R-CON-01]`

**Behaviour.** Three long-running processes — API, worker, static frontend — each with an **explicit
memory limit**. No container runs unlimited. Final backend image under 250 MB. **Every figure below is
an estimate, reasoned and not observed**, to be replaced with measured numbers at the end of Phase 1.

**Who may do it.** The client sets the limits, in the ECS task definition, which is Zone C. The build
session owes the values and the reasoning.

**Preconditions.**
- One uvicorn worker per API container. Each worker is a full Python process, and two roughly doubles
  the API's footprint.
- The database connection pool is sized deliberately, not defaulted: `db.t3.micro` has roughly 110
  maximum connections and pool size multiplies across processes.
- The frontend is a static container, not a Node process.
- Both images are multi-stage; a build toolchain in a runtime image is the single largest avoidable
  contribution to image size.

**Happy path.**
1. Each container starts with its limit set.
2. Each stays within it under normal load and under the Phase 7 load test.
3. Phase 1 records the resident set size of each container under idle and under load, and the table
   below is replaced with real numbers.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A container exceeds its hard limit | **it is killed by the kernel with an out-of-memory error. It does not slow down and it does not warn.** The symptom is a task that restarts with no application log explaining why, because the process died without a chance to write one | *(the site is down until the task restarts)* |
| 2 | A container runs with no limit | one process's leak takes the host down instead of the container | *(the site is down)* |
| 3 | A measured figure exceeds its limit | **the client is told, with the number and what it would take to fit.** Not quietly raised, not quietly worked around | *(no user-facing surface)* |
| 4 | The backend image lands over 250 MB | ECR holds 500 MB in total and the effective budget is roughly two tags of each image. **The client is told with the number.** | *(a deploy eventually fails on a full registry)* |
| 5 | A second task of the same service is started on the one instance | it cannot start at these limits with a fixed host port, so ECS's default deployment configuration deadlocks waiting for a healthy new task that can never start | *(the deploy hangs)* |

**Server-side validation.** None. **Say it rather than work around it** is the binding rule here.

**Worked example.** The budget, with the arithmetic and its labels.

```
t3.micro total ........................................ 1024 MB
less operating system + Docker daemon + ECS agent ..... 300–400 MB   (reasoned, not observed)
available to our containers ........................... 624–724 MB

API ...................... ~200 MB   Python + FastAPI + SQLAlchemy + pool + one uvicorn worker
Worker ................... ~150 MB   the same libraries, no HTTP server, smaller pool
Static frontend .......... ~15 MB    a static web server and the built assets
budgeted ................. ~365 MB
headroom ................. 259–359 MB
```

**Every figure in that block is `(reasoned from typical figures, not observed)`.** No part of this
application has ever run, in AWS or anywhere. The headroom is deliberate: if measurement shows the API
at 300 MB rather than 200 MB it still fits, which is why the estimate being wrong is survivable.
**Nothing in this specification is currently known not to fit in 1 GB** — and that statement is an
estimate too, and it is what Phase 1 exists to settle.

---

### `P-XCT-22` · Introduce no scheduled job of any kind · `RULED`
`[SRC: SRC-003 OPEN-PROC-01 · SRC-003 OPEN-TMDB-01 · SRC-002 §E E-4 · SRC-002 §8.1.4 · FR-ADR-005 · FR-ADR-012]`
`[BRD: R-CON-06]`

**Behaviour.** **Nothing in this system runs on a schedule.** No scheduler process, no cron container,
no EventBridge rule, no Lambda on a timer, no periodic task inside a process. This is a design
constraint, not merely an absence: **no later design may introduce one.**

**Who may do it.** Nobody. Adding a scheduled job is a scope change and a new record, not a silent
reuse of an idle capability.

**Preconditions.** The three places a periodic job would otherwise be reached for are closed, and each
has a named replacement:

| What a schedule would have done | What takes its place |
|---|---|
| Expire seat holds | the Redis key's own TTL. A seat becomes available because its key is gone. No sweeper, no reconciler. |
| Expire idempotency records | nothing — **the record is never expired.** A key that expires is a key whose retry after the window creates a second booking. |
| Prune old records | nothing — **nothing is ever deleted.** |
| Relay stuck outbox rows | the worker's **existing** receive loop checks for `pending` rows older than a short threshold before each poll. Work on a loop that already exists, not a timer. |
| Reconcile the `seat_locks_held` counter | a bounded `SCAN` on the same existing worker loop, at a long interval. |
| Invalidate a stale cache entry | the entry's own TTL. |

**Happy path.**
1. A behaviour that would be periodic is written to be correct at write time instead.
2. Where recovery work is genuinely needed, it is folded into the worker's existing loop, which is a
   long-running process that already exists.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A design proposes a nightly job, a sweeper or a cleanup task | rejected. It costs memory inside a 1 GB budget to run something that must be correct anyway, and an idle process invites work to be invented for it | *(no user-facing surface)* |
| 2 | The worker is down and outbox rows accumulate | **receipts are delayed, not lost.** They go out when it comes back | *(the receipt arrives late)* |
| 3 | A lock expires without a release and the metric drifts | reconciled on the worker's existing loop | *(no user-facing surface)* |

**Server-side validation.** None. **The discipline this imposes:** anything that would otherwise be
"the nightly job will fix it" has to be correct when it is written. That is stricter, and it is
deliberate.

**Worked example.** A hold that is abandoned:

```
t = 0 s     hold acquired, Redis SET key token NX PX 180000
t = 45 s    the customer closes the tab. Nothing is notified. Nothing is queued.
t = 180 s   Redis expires the key
t = 180 s   the seat is available to the next reader of the seat map
```

No process ran. No job was scheduled. That is the whole mechanism.

---

### `P-XCT-23` · Add no service or dependency outside the approved list · `RULED`
`[SRC: SRC-002 §4.12 · SRC-002 §5.3 · SRC-002 §13.1 · SRC-003 OPEN-EMAIL-01 · SRC-003 OPEN-QUEUE-01 · FR-ADR-001]`
`[BRD: R-CON-03]`

**Behaviour.** The stack is fixed. Anything outside it needs the client's permission **first**.
Permission has been sought and granted exactly twice: **Amazon SES**, which is now on the approved
list, and **ElasticMQ** for local development only.

**Who may do it.** Only the client grants an addition. The build session asks and waits.

**Preconditions.**
- **Forbidden and not to be designed around:** EKS, Fargate, NAT Gateway, AWS Secrets Manager, Managed
  Grafana, OpenSearch.
- The approved runtime is Docker on ECS backed by EC2, with an Application Load Balancer, RDS
  PostgreSQL, ElastiCache Redis, SQS, SES, S3, SSM Parameter Store, ECR and CloudWatch Logs.

**Happy path.**
1. A design needs something outside the list.
2. It is put to the client, with what it buys and what it costs, before it enters the design.
3. The client answers. The answer is recorded.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A component library, a CSS framework or a CSS-in-JS runtime is proposed | not adopted. CSS Modules ship with Vite and the token layer is plain CSS | *(no user-facing surface)* |
| 2 | A task-queue library — RQ, Dramatiq, Celery — is proposed | **not adopted.** RQ and Dramatiq cannot consume SQS, so adopting either means a second broker or abandoning the SQS architecture. `SRC-002 §5.4.1`'s preference is read as scoped to *which* library if a Redis-brokered queue were used, and that reading is recorded because anyone reading the clause alone will reach a different conclusion | *(no user-facing surface)* |
| 3 | Prometheus, Grafana Cloud or a CloudWatch Prometheus scrape is proposed for `/metrics` | not added and not designed around. Raised for the client to decide | *(nothing scrapes `/metrics`)* |
| 4 | MinIO or MailHog is proposed for local development | not added. A real S3 bucket and a stdout mail stub cover it, and the gap is stated: **local development does not fully exercise the poster upload path without AWS credentials, and does not exercise SES at all** | *(no user-facing surface)* |
| 5 | CloudFront, a bastion host or a VPC interface endpoint is proposed | not added — outside the list or outside the free tier. Gateway endpoints for S3 are recorded as a reasonable later exercise | *(no user-facing surface)* |
| 6 | Argon2id is proposed instead of bcrypt | not adopted — a new dependency for a demonstration project. Recorded as the upgrade to ask for if this ever holds real accounts | *(no user-facing surface)* |

**Server-side validation.** None. **A dependency that is not obviously necessary costs the client a
decision**, and spending one badly is a real cost on a project where the client is also the only
decider.

---

### `P-XCT-24` · Adopt WCAG 2.2 AA as the target, claim no conformance, and record the one deviation · `RULED`
`[SRC: SRC-001 §5.2.2 · SRC-001 §6.1 · SRC-003 OPEN-SEAT-02 · FR-ADR-051 · FR-ADR-044]`
`[BRD: R-QLY-09]`

**Behaviour.** WCAG 2.2 Level AA is adopted as the build session's own target. Nobody asked for it;
adopting a stricter option needs no signature. **Every contrast ratio is computed and recorded, never
asserted** — the figures live in `docs/05 B DesignSystem/CONTRAST.md`, which is generated, and nowhere
else. **No conformance is claimed**, because a claim would need testing this project has not done.

**Who may do it.** No role. This binds every screen in the product, in every lane.

**Preconditions.**
- Every colour token in `tokens.css` carries a machine-readable annotation naming what it is and which
  grounds it may sit on. A colour without an annotation fails the check; **a colour cannot enter this
  system unmeasured.**
- Thresholds: 4.5:1 for body text, 3:1 for large text and for non-text interface components.
- `OPEN-SEAT-02` ruled out **accessible-seat marking**, a product feature about wheelchair spaces.
  That says nothing about whether the interface is usable by a person with a disability, and reading
  it as a licence to skip interface accessibility would be reading a ruling wider than it was given.

**Happy path.**
1. A colour pair enters the design system with its annotation.
2. `contrast.py` computes the ratio for both themes and writes it to `CONTRAST.md`.
3. A design review checks the recorded figure against the threshold.
4. Every interactive element is reachable and operable by keyboard, focus order follows visual order,
   and the focus indicator is visible against every background it can appear on.
5. Every input has a programmatically associated label; errors are associated with their field and are
   **announced**, not only coloured.
6. Seat states carry a non-colour cue as well as colour.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A colour pair has no recorded figure | it has not been checked and a design review may not pass it | *(no user-facing surface)* |
| 2 | An error is shown only in red | it has not been reported. Every error goes through a live region | *(a screen-reader user is told what happened)* |
| 3 | The three-minute hold cannot be extended | **this is a recorded deviation from the AA timing criterion**, not an oversight. The limit exists to release a scarce resource to other customers, and extending it would let one customer hold a seat indefinitely | "The hold on your seats has ended and they have been released. You have not been charged." |
| 4 | A conformance statement is published | forbidden. Untested is untested | *(no user-facing surface)* |
| 5 | 220 seats each get their own tab stop | rejected. The map is a single tab stop with arrow-key grid navigation — tabbing through 220 seats to reach the checkout button is technically conformant and unusable | *(no user-facing surface)* |

**Server-side validation.** None — this is an interface floor. **The mitigation for the recorded
timing deviation:** the limit is clearly displayed from the start, warned at 60 seconds, and the
customer's selection is restored on expiry so nothing is lost but the seats.

**Explicitly not in scope and not claimed:** accessible-seat marking as a product feature, a
screen-reader-optimised alternative to the seat map, and formal conformance testing or an
accessibility statement.

**There is no browser or version matrix in any frozen source, and none is invented here.**

---

### `P-XCT-25` · Render the largest hall's seat map on a 375-pixel-wide phone · `ASSUMED`
`[SRC: SRC-001 §6.1 · SRC-001 §9.1 · SRC-003 OPEN-SCALE-02 · FR-ADR-044 · FR-ADR-016 · FR-ADR-051]`
`[BRD: R-QLY-09]`

> ⚠ **`ASSUMED`.** The hall sizes — 90, 120, 150, 180, 200 and 220 seats — are the build session's
> choice. The client said "pick random" (`SRC-003 OPEN-SCALE-02`). **They never harden into a
> constraint**, and this row is flagged every time the 220 figure matters.

**Behaviour.** The design target is the **220-seat hall on a 375-pixel-wide screen**. Layout uses
flexbox and grid with relative units. **The page body never scrolls horizontally**; anything wider
than the viewport scrolls inside its own container, and the seat map is the only component that
regularly needs this.

**Who may do it.** No role. This binds every screen.

**Preconditions.**
- `--fr-seat-size` is 24px, which is the WCAG 2.2 target-size minimum. **Shrinking the seat to make it
  fit is how a product fails a criterion to win an argument with a layout.**
- Page gutter is `--fr-space-4` on a phone and `--fr-space-6` above 40rem.
- Every poster slot reserves a 2:3 box before the image arrives, so a listing does not reflow when it
  loads.

**Happy path.**
1. A customer opens the seat map for the 220-seat hall on a 375-pixel-wide phone.
2. The map renders at full seat size and scrolls horizontally inside its own container.
3. The page body does not scroll horizontally.
4. The checkout action stays reachable without scrolling the map.

**Something has to move the map, and nothing did.** A container that scrolls is only half a
specification: the other half is **who scrolls it and to where**, and no P-row, screen spec or
component spec ever moved it — not on first paint, not when keyboard focus left the visible strip, not
for a restored selection, and not for a seat named in an error. On the design target roughly **half of
a twenty-column row is off screen at any scroll position** (the arithmetic is below), so the omission
is not cosmetic: arrow-key focus routinely landed on a seat nobody could see. **These four rules are
the missing half**, and they bind every surface that renders the map.

| # | When | What scrolls, and by how much |
|---|---|---|
| 1 | **First paint** | the container is scrolled to its **leading edge**, so seat `1` of every row is visible and the opening view is a decision rather than whatever the browser last remembered. **A customer with a restored selection is rule 3's case and overrides this one.** |
| 2 | **Keyboard focus leaves the visible strip** | the container scrolls the **minimum** amount that brings the newly focused seat **fully** inside it. Never centred, never animated past `--fr-motion-base`, and **never the page body** — only this container moves. |
| 3 | **A selection is restored** — the return from sign-in (`SCR-XCT-04`), or a reload carrying a `sessionStorage` selection | the container scrolls to bring the **first** restored seat fully into view, on the same minimum-movement rule. |
| 4 | **An error names seats** — `details.unavailable_seats` on `SEAT_UNAVAILABLE` (`SCR-XCT-01`) | the container scrolls to bring the **first named** seat fully into view, so the seat the banner is talking about is the seat the reader can see. |

**The pinned row gutter is what makes "fully inside it" load-bearing.** `SCR-SEA-01` pins the
28-pixel row-label gutter to the leading edge while the seats scroll under it, so a cell scrolled to
the container's exact leading edge is **underneath** the gutter rather than beside it. A focus ring
drawn there is obscured by page content, which is **WCAG 2.2 SC 2.4.11 Focus Not Obscured (Minimum),
new at AA in 2.2** and inside the target `P-XCT-24` adopts. **It is fixed rather than recorded as a
deviation**, because `P-XCT-24` has exactly one deviation and this is not it: the container carries
`scroll-padding-inline-start: var(--fr-seat-gutter)`, so every one of the four rules above stops short
of the gutter and no focused cell can come to rest under it.

**Two things these rules deliberately do not do.** They **never scroll while the reader is scrolling**
— a programmatic scroll that fights a finger is worse than none — so rules 2 to 4 fire on focus and on
error arrival, not on poll. And they **never move the page body**: `--fr-page-max` and the shell
(`SCR-XCT-05`) both depend on the body having one scroll direction, and a horizontal body scroll is
exception 3 below.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The map is wider than the viewport | it scrolls inside its container. This is the designed behaviour, not a failure | *(nothing — the map scrolls)* |
| 2 | The seat size is reduced to make a hall fit | rejected — it breaks the target-size minimum | *(no user-facing surface)* |
| 3 | The page body scrolls horizontally | a defect | *(no user-facing surface)* |
| 4 | A hall larger than 220 seats is configured | nothing breaks — the map scrolls further. **The 220 figure is a design target, not a limit**, because it is `ASSUMED` | *(nothing)* |
| 5 | Arrow-key focus moves to a seat outside the visible strip and nothing scrolls | a defect. The focus ring is drawn where nobody can see it, and the reader has no way to know which seat is focused | *(nothing appears to happen when the arrow key is pressed)* |
| 6 | A focused seat comes to rest under the pinned row gutter | a defect — **SC 2.4.11 at the adopted AA level**, fixed by the scroll padding above and not by recording a second deviation | *(the focus ring is partly or wholly hidden behind the row letter)* |
| 7 | The map is scrolled by centring the target rather than by minimum movement | rejected. Centring moves the whole map on every arrow press, so the reader loses their place on a grid they are navigating one cell at a time | *(the map lurches on every key press)* |

**Server-side validation.** None.

**Worked example — the row is wider than the viewport, and the visible strip is narrower than the
viewport.** Both halves matter, and the second was previously left out.

```
seat size ............................... 24 px   --fr-seat-size  (WCAG 2.2 target-size minimum)
seat gap ................................  4 px   --fr-seat-gap
per seat ................................ 28 px
a 20-column row ......................... 20 × 28 − 4 = 556 px      <- this is what scrolls

viewport ................................ 375 px
less page gutter, both sides ............ 2 × 16 = 32 px   --fr-space-4  (COMPONENTS.md §0.1)
less map-field padding, both sides ...... 2 × 16 = 32 px   --fr-space-4  (SCR-SEA-01, "Map field")
less the pinned row gutter .............. 28 px            --fr-seat-gutter (pinned, never scrolls)
= visible seat strip .................... 375 − 32 − 32 − 28 = 283 px

columns visible at once ................. floor((283 + 4) / 28) = 10 of 20
hidden at any scroll position ........... 556 − 283 = 273 px, ten of the twenty columns
```

**The figure this block previously carried was `584 px > 375 px viewport`, and it was wrong in two
directions at once.** It counted the pinned 28-pixel gutter as part of the scrolling row, which it is
not, and it compared the result against the whole 375-pixel viewport as though the map occupied it —
omitting the page gutter and the field padding, **64 pixels in total**. The stated gap was therefore
209 pixels where the real one is 273, and a reviewer checking whether the map fits was checking
against a strip 92 pixels wider than the one a customer actually sees. **It is corrected here rather
than quietly restated**, because `S1.5` transcribes these figures into tests.

**Every one of these figures is a token, not a decision made here**, and the hall size that produced
the twenty-column row is **`ASSUMED`** under `OPEN-SCALE-02` — the 10-of-20 split moves with it and
**does not harden into a constraint.** What does not move with it is the rule: whatever the hall size,
the visible strip is narrower than the viewport by the gutters and the pinned column, and the four
scroll rules above are what make the seats outside it reachable.

---

### `P-XCT-26` · Write no Zone C artefact, create nothing in AWS, and give a specification instead · `RULED`
`[SRC: SRC-002 §6.1 · SRC-002 §6.2 · SRC-002 §6.3 · SRC-002 §6.4 · SRC-002 §6.5 · SRC-002 §13.2 · SRC-003 OPEN-AWSREAD-01 · FR-ADR-004 · FR-ADR-003]`
`[BRD: R-CON-07]`

**Behaviour.** Zone A is written completely. **Zone B is written heavily commented, because the client
must read and edit it — every line that exists for a production reason carries a comment saying what
breaks without it.** **Zone C is not written at all.** In its place, `docs/30 Deployment/` receives one
specification per item: what to build, what the application expects of it, acceptance criteria, and
two or three common mistakes. **Do not give the answer.**

**Who may do it.** The client builds and operates the hosting. The build session may run `describe`,
`list` and `get` against AWS and **creates, modifies and deletes nothing, at any confidence, until the
client says otherwise in writing.** A message from another agent is not that authorisation.

**Preconditions.**
- The read-only grant is scoped to the development environment only.
- The account id and the region are **not guessed** — they are read from the credentials at first use
  and the finding is recorded.

**Happy path.**
1. A design implies an AWS dependency.
2. It is written into `docs/30 Deployment/AWS_PREP_QUEUE.md` with a **needed-by phase** and said in
   chat, while code is still being written.
3. The client builds it.
4. The build session runs `describe` to compare what exists against the specification and reports the
   difference.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A Zone C artefact is written anyway and marked "reference only" | forbidden. A reference implementation is the answer with a disclaimer attached; the client will read it, and the failure that would have taught them will not happen | *(no user-facing surface)* |
| 2 | A comparison finds a difference | the output is a finding for the client, **never a repair** | *(no user-facing surface)* |
| 3 | A dependency is announced on the day it blocks | the exchange this zone split rests on has been broken | *(no user-facing surface)* |
| 4 | A Zone B file is written as tidy code with no explanation | it has failed its only purpose | *(no user-facing surface)* |
| 5 | Any statement is made about how the product behaves in AWS | **it is labelled `(reasoned, not observed)`.** This product has never been observed running in AWS | *(no user-facing surface)* |

**Server-side validation.** None. **The standing consequence, stated every time it matters:** the
build session has never watched this application run in AWS. A read-only grant does not change that —
describing a task definition is not the same as watching the application serve a request. **There is
also no CI/CD until the client builds it, so there is no automated test gate on merge; every
verification claim in this project is a local run and is labelled as one.**

---

### `P-XCT-27` · Deliver in eight phases, telling the client what to test at the end of each · `RULED`
`[SRC: SRC-002 §12 · SRC-002 §12.1 · SRC-002 §2.4 · SRC-002 §E E-3 · SRC-003 OPEN-SCOPE-01 · FR-ADR-006]`
`[BRD: R-CON-05]`

**Behaviour.** Eight phases. Nothing is built all at once, and a phase closes only when the client has
been told what to test. At the close of every phase a short explanation file is written covering what
was built, why it is built that way, and what breaks in production if the deployment is got wrong.

**Who may do it.** The client decides when a phase is done, because what "done" means is theirs.

**Preconditions.** The revised plan, with Phase 6 replaced and Phase 8 added:

| Phase | What the business gets |
|---|---|
| 1 | the skeleton, deployed by the client against something trivial so the process is learned first |
| 2 | the record structure and the admin's ability to set up halls, showtimes and prices |
| 3 | public browsing, listings and the seat map to look at |
| 4 | holding seats, confirming a booking, and **the concurrency proof** |
| 5 | the receipt email |
| 6 | **the admin's film management** *(this replaced the withdrawn automatic import)* |
| 7 | measurement, limits, the load test and the operating manual |
| 8 | **the manager and admin dashboard** *(new)* |

**Happy path.**
1. A phase's rows are built.
2. The explanation file is written.
3. The client is told what to test.
4. The phase closes.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A phase's quality gate is red | **the story is marked `Blocked` with a note and surfaced.** Never faked, skipped, `xfail`ed, commented out or deleted to reach green | *(no user-facing surface)* |
| 2 | A required variable is missing | the dependent story is `Blocked`, never stubbed | *(no user-facing surface)* |
| 3 | A phase is delivered without telling the client what to test | the phase has not closed | *(no user-facing surface)* |
| 4 | Work from a later phase is pulled forward | permitted only where an earlier phase depends on it. The seed script is a Phase 2 deliverable and a **dependency of Phase 4**, because the concurrency proof needs fifty authenticated customers | *(no user-facing surface)* |

**Server-side validation.** None. **The phase mapping for this lane's rows is in S7 §18**, with a
stated convention the merge pass applies to every other lane's rows.

---

### `P-XCT-28` · Escalate a reserved question, never invent an answer · `RULED`
`[SRC: SRC-003 OPEN-TLS-01 · SRC-003 OPEN-ATTRIB-01 · SRC-003 OPEN-SHOWCANCEL-01 · SRC-003 OPEN-EMAILFAIL-01 · FR-ADR-069 · FR-ADR-007 · FR-ADR-023 · FR-ADR-049]`
`[BRD: R-CON-11]`

**Behaviour.** Money, anything irreversible or public, secrets, legal and data-protection questions,
what the product is and what "done" means, changes of scope, and **waiving any quality check** are the
client's alone. No model decides them at any confidence. **Adopting a stricter option is not a waiver
and needs no signature.**

**Who may do it.** The client only. **No timeout defaults past a reserved matter.** A reversible
reserved matter is decided and then batched for the client to reverse; a reserved-and-irreversible
matter stops and waits.

**Preconditions.** Four questions are open and each is named rather than filled in:

| Row | The question | Class | What may be specified | What may **not** |
|---|---|---|---|---|
| `OPEN-TLS-01` | securing the connection needs a domain the client is sourcing | product · `DEFERRED` | that `COOKIE_SECURE` is environment-driven and off in the deployed environment; that the environment is never called production | that TLS is or will be terminated anywhere |
| `OPEN-ATTRIB-01` | where do the posters and titles come from | legal | that demonstration content uses obvious placeholders and no image from anywhere | any real title, poster, brand or source |
| `OPEN-SHOWCANCEL-01` | an admin withdraws a showtime with paid bookings — what happens to the money | money, irreversible | that **no withdraw-showtime capability exists in v1**, and why | any withdrawal endpoint, screen or refund behaviour |
| `OPEN-EMAILFAIL-01` | SES definitively fails after payment is captured | product | that the reference is on the confirmation screen and in the bookings list independently of the email; that the receipt job records its attempts and its state | **any wording shown to a customer whose receipt definitively failed, and any policy about the money already taken** |

**Happy path.**
1. A question is found to be reserved.
2. It is named as an Article X row, with the alternatives that make it answerable in one message.
3. The dependent work either proceeds on the mechanism, or stops.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | An open row is filled in with something sensible | **the cardinal failure of this project.** Rejected at review | *(no user-facing surface)* |
| 2 | An admin attempts to withdraw a showtime | there is no such capability in v1. **This is the fail-closed position: an unbuilt capability is recoverable, an unrefunded customer is not** | *(no such control exists)* |
| 3 | A receipt definitively fails after payment | the mechanism ships and **the message does not.** The PRD carries a placeholder citing `FR-ADR-049` so nobody writes a plausible sentence into a screen and calls the question answered | *(no sentence is written here for that screen)* |
| 4 | An option stricter than the ruled one is adopted | permitted, and it needs no signature | *(no user-facing surface)* |
| 5 | A "you decide everything" instruction arrives | technical calls are the build session's; reserved matters stay reserved | *(no user-facing surface)* |

**Server-side validation.** None. **The standing constraint while `OPEN-ATTRIB-01` is open:** no
licensed image or synopsis enters this product.

---

### `P-XCT-29` · Never call the deployed environment production, and put no real customer data in it · `OPEN` / `DEFERRED`
`[SRC: SRC-003 OPEN-TLS-01 · SRC-003 OPEN-EMAIL-01 · FR-ADR-069 · FR-ADR-067 · FR-ADR-060]`
`[BRD: R-CON-08]`

> ⚠ **`OPEN` / `DEFERRED`.** `OPEN-TLS-01` is a live Article X row owned by the client. This row
> specifies the surface the deferral forces; **it does not decide TLS and it states nothing about
> whether TLS is or will be terminated anywhere.**

**Behaviour.** Until the row closes: the session cookie's `Secure` flag is environment-driven and off
in the deployed environment; **the deployed environment is never called production in any document**;
and no real customer data goes into it — seeded demonstration data only.

**Who may do it.** The client closes the row. Nothing here is a decision the build session may make.

**Preconditions.**
- `COOKIE_SECURE` is a required variable with **no default**, so nobody can deploy without stating
  what they intend.
- **Nothing is designed around the absence of TLS.** No plain-HTTP-specific workaround, no token in a
  query string, no alternative session mechanism.

**Happy path.** *(the deferral is the state)*
1. The environment is named something other than production, in every document.
2. `COOKIE_SECURE` is set explicitly, per environment.
3. Only demonstration data is loaded.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `Secure` is set anyway "as the stricter option" | **it is not stricter, it is broken** — the browser never sends the cookie over HTTP and nobody can stay signed in | "You were signed out. Sign in again to continue." *(on every request)* |
| 2 | A self-signed certificate is used | rejected. Every browser warns, which trains the client and any audience to click through a certificate warning | *(a certificate warning)* |
| 3 | Real customer data is loaded | forbidden. **Credentials cross the network unprotected in that environment** | *(no user-facing surface)* |
| 4 | Receipts are sent from a verified single address rather than a verified domain | **materially worse deliverability. A receipt in a spam folder is functionally a receipt that did not arrive**, which lands in `OPEN-EMAILFAIL-01` | *(the receipt may not arrive)* |
| 5 | The row closes | it closes by a **new superseding record**, never by editing the existing one | *(no user-facing surface)* |

**Server-side validation.** `COOKIE_SECURE` must be false unless `PUBLIC_BASE_URL` begins with
`https://` — a boot-time cross-field check, so the two cannot disagree.

**What the client does when a domain exists**, so the answer is one step rather than a project:
request an ACM certificate validated by DNS; add an HTTPS listener and redirect HTTP to it; set
`COOKIE_SECURE=true`; verify the domain in SES and configure DKIM and SPF; set `PUBLIC_BASE_URL` to
the HTTPS address. **All of it except the last two is Zone C. No application code changes.**

**Two independent reasons to close this row:** the credentials, and SES deliverability. Naming both
gives the client a better reason to prioritise it than either alone.

---

### `P-XCT-30` · Ship demonstration content that is obviously demonstration content · `RULED`
`[SRC: SRC-003 OPEN-SEED-01 · SRC-003 OPEN-ATTRIB-01 · SRC-003 OPEN-PAY-01 · SRC-003 OPEN-SCALE-02 · SRC-003 OPEN-SEAT-01 · FR-ADR-067 · FR-ADR-007]`
`[BRD: R-CON-09]`

**Behaviour.** The seed script generates **structural data only**. Movie rows are obvious placeholders
— `DEMO MOVIE 01` through `DEMO MOVIE 08` — with no synopsis text pretending to be a synopsis. **The
client supplies the real titles and posters**, as they said they would. **The eight films are
published and visible**, against one placeholder poster committed to the repository and shared by all
eight.

**Who may do it.** The client runs the seed against the deployed environment, once, deliberately. The
build session cannot: it has no write access to anything in AWS. **The wipe command is never run
there**, and the specification says so in those words.

**Preconditions.**
- The script is idempotent, keyed on the placeholder identifiers, and skips what exists.
- A separate, explicitly named command wipes and reseeds. Not the default, because the default is what
  someone runs by accident.
- Seeded time is relative to an injected clock, not hardcoded dates. A script that seeds a fixed date
  is useless in a month. **On a re-run the anchor comes from the data rather than from the clock**, so
  that idempotency and this precondition can both hold; the schedule block below states the rule and
  the staleness it accepts in exchange.

**Happy path.**
1. One cinema, `DEMO CINEMA`, with `Asia/Kolkata` as its zone.
2. Six screens of 90, 120, 150, 180, 200 and 220 seats, each with an exact grid, seat labels and
   category bands — the layout table below — **`ASSUMED`**, from "pick random".
3. Three seat categories, Standard, Premium and Recliner — **`ASSUMED`**.
4. **The lookup vocabulary a film is built from** — languages, certifications, genres and formats —
   created before the first film, because `P-ADM-01` refuses a film unless a row already exists in
   each. The table below.
5. **One placeholder poster**, from the repository, uploaded once and referenced by all eight films —
   the block below.
6. **Eight placeholder movies, all published and all inside their display windows**, so a customer
   who runs the seed sees a catalogue rather than "Nothing is showing right now."
7. **720 showtimes** — four per hall per day for 30 days — one admin, **twelve managers mapped to
   screens by the rule below**, **fifty distinct authenticated customers**, and bookings with payments
   in `captured` state at a deterministic occupancy. The schedule block below fixes all of it.

**The manager-to-screen mapping**, because *"two per screen"* fixes the shape and not the assignment:

```
screen_number = floor((m - 1) / 2) + 1        for manager-01 .. manager-12

manager-01, manager-02  -> Screen 1        manager-07, manager-08  -> Screen 4
manager-03, manager-04  -> Screen 2        manager-09, manager-10  -> Screen 5
manager-05, manager-06  -> Screen 3        manager-11, manager-12  -> Screen 6
```

**Without this, a given manager's dashboard covers a different hall depending on who built the seed**,
and every manager-scope test — the one `S7.5` insists must assert a **non-empty** result for the
manager's own screens and a denied result for another's — has no fixed subject to assert against.
`manager-01` sees Screen 1 and is denied Screen 2; that pair is now the same in every build.
**`PROVISIONAL`, with the four-role ruling it rests on** (`SRC-003 C-1`): if the manager role
reverses, this mapping goes with it.

**"Authenticated" in step 7 means an account that can actually sign in, and how it gets a password is
`P-XCT-32`'s** — one environment variable, hashed once, never printed and never committed. Without it
this row produces sixty-three accounts nobody can use, Phase 2 has no admin and Phase 4 has no fifty
customers for the concurrency proof. **The seed also enqueues no receipt job**, for the bounce reason
`P-XCT-32` states, **and writes each dispatch row `suppressed` instead (`P-TKT-04`)** — so a seeded
booking has a dispatch row that records the truth about it rather than no row at all.

#### The seed writes no `audit_log` row, and that is a decision rather than an omission

**`scripts/seed.py` inserts directly into PostgreSQL with no request, no session and no acting user,
and it writes no row into `audit_log` for anything it creates.** The row said nothing about this, and
silence here is not neutral: a developer writing the script has to choose, and every choice available
to them breaks a stated rule.

**Why there is no honest actor to name.** `P-ADM-19` makes `actor_user_id` a **non-null** foreign key
to the acting user and forbids **both** a role name and a service account. The seed **creates the
first admin itself**, so at the moment of its earliest writes — the cinema, the screens, the seats, the
twelve lookup rows — no user row exists that any actor column could point at. The three ways out are
each worse than the absence:

| The way out | Why it is refused |
|---|---|
| Write the audit row with a null or a placeholder actor | breaks `P-ADM-19`'s non-null rule in the one table whose whole value is that its rows are true |
| Invent a `seed` or `system` service account | **`P-ADM-19` forbids a service account in terms.** It is also a real user row that can be signed in as, if it ever gets a password |
| Attribute every seeded row to `admin-01` | a **false statement about who did it.** `admin-01` did nothing; the row would say they created 720 showtimes in one second |

**The scope this rests on, stated so it is not read wider than it is.** `S7.3` and `P-XCT-03` audit
**every privileged write**, and a privileged write is **an admin action arriving through the API**.
The seed is database provisioning by a script the client runs once, deliberately, with the application
not necessarily running at all. **This is the only process in the product that writes to these tables
without a request, and it is the only exemption there is.** No application code path inherits it: a
handler that writes without an audit row is a defect, exactly as `P-XCT-03` says.

**What identifies a seeded row instead**, since the audit log does not: the `DEMO` prefix on every
name and the reserved `.invalid` email domain (`FR-ADR-067`, `P-XCT-32`). An operator asking *where
did this come from* gets an answer from the row itself, which is the question they were going to ask
the audit log.

**The gap, recorded rather than closed:** the Phase 8 change log shows **nothing** before the first
real admin action. A reader of it cannot tell whether the catalogue was seeded or created by hand, and
they will assume it was created by hand because that is all the log contains. That is the accepted
cost of the three refusals above.

#### Running the seed freezes every hall's layout, permanently, and this is the sentence that says so

**The seed inserts 720 `showtime` rows across all six screens. `P-ADM-14` freezes a hall's layout the
moment *any* showtime row exists on it.** So the seed's showtime pass closes, for all six halls at
once: **renumbering a seat, removing a seat, and moving a seat to a different category are refused
with 409 `LAYOUT_FROZEN` from then on.** Adding a seat, taking one out of service and changing its
grid coordinates stay permitted; the identity of an existing seat does not.

**It does not thaw.** Nothing is ever deleted, so the showtime rows that froze it stay, and the freeze
is therefore permanent unless the separate, explicitly named wipe-and-reseed command is run —
**which this row already forbids in the deployed environment** (exception 5). In that environment
there is no route back at all.

**This is `OPEN-SEATLABEL-01`'s deadline arriving, and nothing warned anyone of it.** That row is the
one open item with a deadline rather than only a direction: it stops being fixable once the first
showtime exists. **The seed is what makes the first showtime exist.** So:

- **The seed prints one line before its first showtime write**, naming what is about to become
  permanent and naming the halls it affects. It is a notice and not a prompt — the seed does not stop
  and wait, because a script that blocks on input cannot be run as a one-off container task.
- **The specification tells the client to settle seat labelling before running the seed against a
  deployed environment**, and says why in the same breath: the labels are what a receipt carries and
  what the person at the door reads (`P-ADM-14`).
- **Local runs are recoverable and deployed runs are not.** Wipe and reseed locally; there is no
  equivalent in AWS.

#### The films are published, and the poster that makes that possible

**The defect this fixes, stated because the fix looks like a loosening and is not.** `P-ADM-05`
refuses publication without a poster. With the seed publishing nothing, `docker compose up` followed
by a seed produced a customer landing page reading **"Nothing is showing right now."** — and three
statements elsewhere silently became false: `P-BRW-04`'s worked example asserts the eight films are
*all published and inside their display windows* and derives which filter controls render from that;
this row's own consequence that **every one of the twelve lookup rows is referenced by a visible
film** is only true of visible films; and **Phase 3's acceptance was not demonstrable at all.** A seed
whose entire output is invisible is not demonstration data.

**One placeholder poster, committed to the repository, shared by all eight films.** It is an asset
**the build session authors**: a flat design-system shape, no artwork, **no text that could be
mistaken for a title**. The seed uploads it once through the ordinary poster path and points all eight
films at the stored object — it is not generated at seed time and it is not fetched from anywhere.

**`OPEN-ATTRIB-01` is untouched, and this is the paragraph that says why.** That row is about **real
posters and real titles and their licensing** — where the client's artwork comes from and who may use
it. A flat shape authored in this repository is **neither generated content nor content from an
unknown source**, so it raises no attribution question, no licence question and no question about a
distributor. The row stays open, exactly as open as it was, and the client replaces this asset the
moment they supply real ones.

**One constraint of this row is deliberately narrowed, and narrowing it silently would be the defect.**
It previously read that the seed *generates no image of any kind, from anywhere*. **It now reads:
"the seed invents no film artwork and fetches no image from anywhere."** The original wording banned
the placeholder along with everything it was aimed at, and what it was aimed at is two specific
things — **inventing artwork** for a film, which fabricates content the client may take as real, and
**fetching an image** from an unknown source, which is the licence problem. **A repo-committed flat
shape is neither**, and the narrowing is stated here so a reader meets a decision rather than an
inconsistency.

#### The seeded lookup vocabulary — this row claims it, and no other row does

**Why it has to be here.** `P-ADM-01` refuses to create a film unless its `language_id`, its
`certification_id` and **at least one** `genre_id` already exist as rows, and `P-ADM-23` — correctly —
claims no starting rows, because the seed is this row's and not the admin section's. **Nothing then
claimed them**, so the eight `DEMO MOVIE` films below could not be inserted, Phase 2 had no data and
Phase 4 had no fifty customers. **This row claims them.**

| Vocabulary | Rows the seed creates |
|---|---|
| `language` | `DEMO LANGUAGE A`, `DEMO LANGUAGE B`, `DEMO LANGUAGE C` |
| `certification` | `DEMO RATING 1`, `DEMO RATING 2` |
| `genre` | `DEMO GENRE 1` .. `DEMO GENRE 4` |
| `format` | `DEMO FORMAT 1`, `DEMO FORMAT 2` |

**Every seeded lookup name is a placeholder, and that is the point.** `OPEN-ATTRIB-01` is about real
titles, posters and their licensing, and **this table does not touch it and must not**: no seeded name
implies a real language, a real regulator's certificate or a real distributor's format, so nothing
here creates an attribution or a licensing question. **All twelve rows are `ASSUMED`** — the names sit
under `OPEN-SEAT-01`'s "you pick", extended to the same class of naming question, and under
`OPEN-ATTRIB-01`'s standing constraint for *why* they are placeholders. **They never harden into a
constraint**, and the client replaces the whole catalogue the moment they supply real content.

**Assignment is deterministic**, so two runs of the seed produce the same catalogue and a screenshot
taken today still matches next month. For `DEMO MOVIE nn`, with `n` from 1 to 8 and `i = n - 1`:

```
language        = language[i mod 3]
certification   = certification[i mod 2]
genres          = { genre[i mod 4], genre[(i + 1) mod 4] }      two per film, always distinct
```

**Worked example.** `DEMO MOVIE 04`:

```
i = 4 - 1 = 3
language        i mod 3       = 3 mod 3 = 0   -> DEMO LANGUAGE A
certification   i mod 2       = 3 mod 2 = 1   -> DEMO RATING 2
genres          i mod 4       = 3            -> DEMO GENRE 4
                (i + 1) mod 4 = 0            -> DEMO GENRE 1
```

Two consequences, both of which the browse surface depends on: **every film carries at least one of
every filterable vocabulary**, so no filter control is rendered against a film that has nothing to
show; and **every one of the twelve lookup rows is referenced by at least one film**, so an endpoint
that returns only rows in use returns all twelve against the seeded catalogue.

#### The six hall layouts

Sizes are `ASSUMED` under `OPEN-SCALE-02` and the grids below are this row's derivation of them, so
the seed is deterministic and the seat-label uniqueness rule has something concrete to be true of.

```
Screen 1 ...  90 seats =  9 rows x 10 columns
Screen 2 ... 120 seats = 10 rows x 12 columns
Screen 3 ... 150 seats = 10 rows x 15 columns
Screen 4 ... 180 seats = 12 rows x 15 columns
Screen 5 ... 200 seats = 10 rows x 20 columns
Screen 6 ... 220 seats = 11 rows x 20 columns
```

**Rows are labelled `A` onward, `A` nearest the screen. Seats are numbered `1` upward, left to right
as the audience faces the screen.** A seat's label is its row letter and its number with no
separator: `A1`, `A10`, `J20`.

**The row letter skips `I`.** `I` and `1` are the pair a person misreads on a printed row marker and
on a phone at 375 pixels, so the letters run `A B C D E F G H J K L M`. **Say it out loud because it
changes what a seat is called**: Screen 1 has nine rows and its last row is `J`, not `I`.

**Category bands are computed from the row count, never typed:**

```
standard_rows  = ceil(rows * 0.5)      the rows nearest the screen
premium_rows   = ceil(rows * 0.3)
recliner_rows  = rows - standard_rows - premium_rows      the rows furthest from it
```

**Worked example, Screen 1:**

```
rows = 9
standard_rows  = ceil(4.5) = 5     -> A B C D E    50 seats
premium_rows   = ceil(2.7) = 3     -> F G H        30 seats
recliner_rows  = 9 - 5 - 3 = 1     -> J            10 seats
                                      total        90 seats
```

**The remainder is positive for all six row counts** — 9, 10, 10, 12, 10 and 11 — so no screen ever
gets a negative or an empty recliner band, and the seed does not need a special case it would then
never exercise.

#### The three seeded categories and their uplifts — seed data, not an example

**These are the seed's values and they are stated here because the alternative is a reader inferring
that an example is data.** The worked examples in the pricing rows elsewhere use `0`, `1250` and
`3333` basis points as **example input**. **The seed uses the same three numbers**, deliberately, so
that a reader who computes a seeded price by hand reproduces a published worked example rather than a
fourth set of figures — and that identity is now written down instead of being a coincidence a reader
has to guess at.

| Category | Uplift, basis points | On the seeded base price of `24999` paise |
|---|---|---|
| Standard | `0` | `24999` paise — ₹249.99 |
| Premium | `1250` | `28124` paise — ₹281.24 |
| Recliner | `3333` | `33331` paise — ₹333.31 |

**All three are `ASSUMED` under `OPEN-SEAT-01`'s "you pick"**, the names and the uplifts alike. **They
never harden into a constraint.** The rounding rule that produces the third column is `FR-ADR-038`'s
and lane E3's; it is applied here and not restated.

#### The schedule — 720 showtimes, computed and not typed

**Why this has to be exact.** This row's own precondition requires the seed to be **idempotent, keyed
on the placeholder identifiers**, and a schedule described as *"about one month"* gives it nothing
stable to key on: two runs a day apart would produce overlapping-but-different showtimes and the skip
logic could not tell a re-run from new data. **"About" is not a specification a script can be written
from.**

```
days              30, CENTRED on the injected clock's LOCAL date in Asia/Kolkata
                  day index d = 0..29 maps to a local date offset of (d - 15)
                  -> 15 days before the clock date, the clock date itself, 14 days after
                  (on a RE-RUN the anchor is read from the data, not the clock -- see
                   "The showtime's placeholder identity" below)
halls              6
starts per day     4
                  ---
showtimes          6 x 4 x 30 = 720          (360 past, 360 from today onward)
```

**The window is centred rather than starting at the clock, and that is this row's answer to a
question `P-ADM-07` raised.** That row says the seed needs *"about a month of historical data"*; this
row previously scheduled 30 days **starting** at the clock, so **not one seeded booking was ever in
the past.** `P-ADM-07` is rank 4 and this row wins on precedence — but winning on precedence while
producing a demonstration with no history is winning the wrong argument. **Three things were empty by
construction and each exists to be exercised:** `SCR-ACC-04`'s **Past** group, one of three zero
states written specifically to be distinguishable from the other two; every dashboard period longer
than today, on a product whose Phase 8 is the dashboard; and `EP-ADM-09`'s `include_past=false`, which
had nothing to hide.

**Centring costs nothing and changes no published figure.** The day count, the slot count, the hall
count, the occupancy cycle and the booking rule are all untouched — only the local dates the schedule
is written onto move. **720 showtimes, 58,800 booked seats and 11,003 bookings are the same numbers
before and after**, which is the reason this shape was chosen over adding a past month to the existing
thirty days. Films stay visible today because their display windows follow the schedule, and 360
future showtimes remain for the concurrency proof and for any manual walkthrough.

**The four local start times are `11:00`, `14:30`, `18:00` and `21:30`** — spaced three and a half
hours, which is **210 minutes against a longest seeded occupancy of 180** (the longest runtime plus
the changeover, both fixed below), so two showtimes on one screen can never overlap and the seed
cannot trip `P-ADM-08`'s own overlap refusal. **They are `ASSUMED`.** No source names a schedule, and
a client with real programming replaces four numbers.

**A claim this row previously made here was unfounded and is withdrawn.** It said the slots were
placed so that the last show of a day ends before midnight local and no showtime straddles a date
boundary. **That was written before this row gave the films a runtime, so it rested on nothing.**

**The figure that replaced it was also wrong, and it is corrected here rather than quietly restated.**
It said the `21:30` slot ends at `00:10` with the longest seeded film — which is
`21:30 + runtime` with **the changeover silently dropped.** This row's own rule is
`starts_at + runtime_minutes + SEED_CHANGEOVER_MINUTES`:

```
21:30 + 160 (longest runtime) + 20 (changeover) = 21:30 + 180 minutes = 00:30 next local day
```

**It is `00:30`, not `00:10`.** *(Recorded rather than replaced silently: a worked figure that is
quietly corrected teaches nobody, and `S1.5` transcribes these into tests.)*

**The consequence is unchanged by the correction, and was checked again against `00:30` rather than
assumed to carry over:** `ends_at` is an instant, nothing in the product buckets or filters by it —
`include_past` and every dashboard period key on `starts_at` — and the next showtime on that screen is
the following day's `11:00`, **eleven and a half hours later**, so no overlap arises at either figure.
The 210-minute slot spacing is likewise unaffected: it is measured against the **180-minute** longest
occupancy, which is the number this correction confirms rather than changes.

#### The showtime's placeholder identity, and what a second run does

**Every other seeded entity has a placeholder identifier the skip logic keys on** — `DEMO MOVIE nn`,
`DEMO CINEMA`, the screens, the seats, the categories, the twelve lookup rows, the sixty-three
addresses. **Showtimes had none**, and that is not a cosmetic omission: the window is anchored to the
injected clock, so a run tomorrow addresses a different span, and because `film_index = (k + d) mod 8`
is a **global** index over the 720, every overlapping showtime would come back carrying a different
film from the same-slot rows around it. **This row already rejected "about one month" for exactly this
property** — *two runs a day apart would produce overlapping-but-different showtimes and the skip logic
could not tell a re-run from new data* — and the replacement inherited it.

**The identifier is `(screen_id, starts_at)`**, which is unique by construction: two showtimes on one
screen cannot share a start instant, because `P-ADM-08`'s overlap rule forbids it.

**And the anchor is derived from the data, not from the clock, on every run after the first:**

```
first_day = the local date of the EARLIEST existing seeded showtime, when any exist
          = (the injected clock's local date) - 15,                 when none do
day index d = 0..29 maps to first_day + d
```

**So a second run recomputes the identical 720 showtimes, finds every one of them, and inserts
nothing.** The film assignment, the formats, the occupancy and the bookings all follow the same
indices they did the first time, because the indices are computed from a schedule the database already
fixes rather than from today's date. **A run interrupted halfway is also handled by the same rule**:
the anchor comes from what was written, so the recomputed schedule matches and only the missing rows
are inserted — with the same films they would have had.

**The cost, stated because it is the one a reader will meet and it is not hidden by this design.** A
database seeded three months ago and re-run today **still carries a three-month-old window**. Every
seeded showtime is then in the past, the browse surface is empty and the Past group holds everything.
**That is correct behaviour for an idempotent script and it is not silently repaired**: refreshing the
window is what the separate, explicitly named wipe-and-reseed command is for, and that command resets
the anchor because it removes the showtimes the anchor is read from. **The alternatives were worse in
kind rather than in degree:** re-anchoring to today on every run inserts a new day's showtimes whose
films disagree with their neighbours' and makes the row's own idempotency precondition false;
skipping all showtimes whenever any exist cannot repair an interrupted run; and a blind full insert is
refused by `P-ADM-08` and exits non-zero, which is at least honest but leaves the operator with a
half-seeded database and no route forward.

**Every start is computed from the injected clock, never hardcoded**, and every one is built in
`Asia/Kolkata` and stored as `timestamptz` — a schedule generated in UTC would land four shows on the
wrong local day for the last five and a half hours of every day.

**Display windows follow the schedule rather than the other way round:** each film's window opens at
the seed's start date and closes after the last day it has a showtime, so **every seeded film is
inside its window for the whole 30 days** and `P-BRW-01`'s visibility gate passes for all eight.

**`format_id` alternates across each hall's showtimes**, by index within the hall:

```
format = format[(index_within_hall) mod 2]        DEMO FORMAT 1, DEMO FORMAT 2, alternating
```

**Format lives on the showtime, not the film**, which is why the film assignment function above does
not cover it and why it needed deciding separately. Alternating guarantees **both** `format` rows are
carried by a visible, not-yet-closed showtime, so `EP-BRW-07` returns two of them and **the format
filter control renders** — which is one of the four vocabularies `P-BRW-04`'s worked example depends
on, and the only one that could not have been satisfied by the film-level assignment.

#### Occupancy — deterministic, so two runs produce the same dashboard

**Varying occupancy was specified and no rule was.** A random occupancy makes the dashboard a
different number on every run, which makes a screenshot worthless and makes any test that asserts a
revenue figure flaky by construction. The rule, by showtime index `k` counting from 0 across all 720
in a stable order:

```
occupancy_percent = 10 + (k mod 9) * 10          -> 10, 20, 30 ... 90, repeating
booked_seats      = floor(seat_count * occupancy_percent / 100)
```

**Seats are taken from the front of the seat set** — row `A` seat `1` onward — so the booked block is
contiguous and a seat map screenshot is legible rather than speckled.

**Worked example**, the 400th showtime, on Screen 5 (200 seats, 10 rows x 20 columns):

```
k                  = 399
399 mod 9          = 3
occupancy_percent  = 10 + 3 * 10 = 40
booked_seats       = floor(200 * 40 / 100) = 80
                     -> rows A B C D filled, 20 seats each
revenue at Standard = 80 x 24999 = 1,999,920 paise = Rs 19,999.20
```

**Occupancy never reaches 100%**, which is deliberate: every seeded showtime keeps free seats, so the
concurrency proof and any manual walkthrough can always find something to hold. **It never reaches 0
either**, so no seeded showtime produces an empty dashboard row.

**The `showtime_seat` storage estimate changes and `P-ADM-14` should be recomputed against this
number.** `P-ADM-14` materialises one row per seat per showtime at showtime creation (`D3`, earlier
wave), so the seeded volume is:

```
seats per hall     90 + 120 + 150 + 180 + 200 + 220 = 960 across the six
showtimes per hall 4 x 30 = 120
rows               960 x 120 = 115,200 showtime_seat rows
```

**115,200 rows, not the smaller figure a "spanning about one month" reading would have produced.** At
a few tens of bytes per row that is single-digit megabytes and it is comfortably inside the free-tier
`db.t3.micro` storage — **the estimate's conclusion does not change, but its input does**, and
`P-ADM-14` carries the estimate. **That row is lane E6's and is named here, not edited.**

#### Which film plays, how long it runs, and when it ends

**Three columns the seed cannot write without these rules, and one of them is `NOT NULL`.** This row
was exhaustive about days, halls, slots, formats, occupancy, seat labels and band widths and said
**nothing** about the film on a showtime, the films' `runtime_minutes`, or `showtime.ends_at` — which
is `NOT NULL` and, by its own rule, *stored and never derived at read time*. `scripts/seed.py` cannot
be written from the row as it stood.

**Film assignment**, by global showtime index `k` and day index `d`:

```
film_index = (k + d) mod 8            k counts 0..719 in ascending (day, slot, screen) order
                                      d counts 0..29
```

The `+ d` rotates the schedule daily. Without it, 24 showtimes a day against 8 films — an exact
multiple — would pin every film to the same screen and slot for all thirty days. **With it every film
gets exactly 90 showtimes** (3 per day × 30), so all eight appear in the dashboard's per-film table
and none of them appears only in one hall.

**`runtime_minutes`, seeded per film and `ASSUMED`:**

```
runtime_minutes = 90 + (i * 10)       i = the film's index, 0..7
                                      -> 90, 100, 110, 120, 130, 140, 150, 160
```

**`ends_at` is computed once at seed time and stored:**

```
ends_at = starts_at + runtime_minutes + SEED_CHANGEOVER_MINUTES
SEED_CHANGEOVER_MINUTES = 20          ASSUMED
longest case = 160 + 20 = 180 minutes, against a 210-minute slot spacing
```

**The changeover figure is `ASSUMED` and it is deliberately not an answer to `PROPOSED-TURNAROUND-01`.**
That row asks the client to rule the real changeover between shows, and **this row does not decide
it and must not be read as deciding it.** The seed needs *a* number because `ends_at` is `NOT NULL`
and a column cannot hold an open question; twenty minutes is a placeholder that keeps the schedule
non-overlapping, and **when the client rules the real figure, `PROPOSED-TURNAROUND-01` is what
changes and this number follows it.** Stated here because a seed constant quietly becoming the
answer to an open row is exactly the failure `SEAT_HOLD_TTL_SECONDS` already produced once in this
project.

#### Bookings — how many, what size, and whose

**Occupancy said how many seats are sold and nothing said how they are grouped**, which decides
whether `GET /api/me/bookings` is empty for forty-nine of the fifty seeded customers or exercised for
all fifty.

```
booking_index counts from 0, globally, across all 720 showtimes in the same
              (day, slot, screen) order k uses. It does NOT restart per showtime.

booking_size  = min(1 + (booking_index mod 10), seats remaining on this showtime)
owner         = customer[(booking_index) mod 50]      customer[0] is customer-01
```

**The base is stated because it is load-bearing and this row had omitted it.** Every other index in
this section names its base — occupancy *counting from 0*, the vocabulary assignment *with `n` from 1
to 8 and `i = n - 1`*, `runtime_minutes` with *`i` = 0..7* — and `booking_index` alone did not, which
meant **the published figures below could not be checked against the rule that produced them.** The
two bases are not cosmetically different: starting at 1 shifts every booking's owner by one customer
and changes where each showtime's tail truncates.

**Re-derived from the stated base, and the published figures hold unchanged:**

| Base | Booked seats | Bookings | Mean size |
|---|---|---|---|
| **0 — the stated rule** | 58,800 | **11,003** | **5.344** |
| 1 | 58,800 | 11,002 | 5.3445 |

**11,003 and 5.34 were computed from base 0 and are correct as published**, so nothing changes here —
but the check was run before saying so, and had it come out the other way **the published figure would
have moved rather than the rule being adjusted to fit it.** The booked-seat total is 58,800 under
either base, because it is fixed by the occupancy rule alone; only the grouping into bookings moves.

Both cycle over a single global `booking_index`, so the whole distribution is reproducible.
**Sizes run the full legal range 1..10**, which is worth having rather than a constant: it exercises
`MAX_SEATS_PER_BOOKING` at its cap and it puts real one-seat bookings in the data, which is the case a
count string with no singular renders as `1 seats` (`S7.21`).

**The resulting inventory, computed and not estimated:**

```
booked seats   58,800        the occupancy rule summed over all 720 showtimes
bookings       11,003        at a mean booking size of 5.34
per customer   220 or 221    every one of the fifty, so no seeded account has an empty bookings list
                             and every one of them pages
mean occupancy 51.04%        of 720 x 160 seats; not exactly 50% because floor() and the
                             hall sizes interact with the 9-step occupancy cycle
```

**Worked example — day 10, the `18:00` slot, Screen 4:**

```
k                = 231            (9 full days x 24) + (2 slots x 6) + screen 4's offset
d                = 9
occupancy        = 10 + (231 mod 9) * 10 = 10 + 6*10 = 70%
seat_count       = 180            Screen 4, 12 rows x 15 columns
booked_seats     = floor(180 * 70 / 100) = 126
film_index       = (231 + 9) mod 8 = 240 mod 8 = 0   -> DEMO MOVIE 01
runtime          = 90 minutes
starts_at        = day 10 at 18:00 Asia/Kolkata
ends_at          = 18:00 + 90 + 20 = 19:50 Asia/Kolkata
```

#### The booking count this row had been quoting was wrong by two orders of magnitude

**Three rows justified the `suppressed` dispatch state by saying the seed creates "roughly sixty"
bookings.** From this row's own occupancy rule the figure is **11,003**. Sixty was never computed
from anything — it appears to have been read off the sixty-three *accounts*, which is a different
quantity that happens to sit nearby in the same rows.

**The justification survives the correction and is strengthened by it.** Writing no
`receipt_dispatch` row would have put **11,003** confirmed bookings on the branch `P-TKT-05` calls
unreachable, not sixty. **At sixty it was a specification defect; at eleven thousand it is also the
first thing an operator would see** — a resend control with undefined behaviour on every demonstration
booking in the system. **Nothing about the decision changes; only the size of what it prevents.**

**Two of the three sites are lane E4's** — `P-TKT-05`'s claim table and `P-TKT-07`'s precondition
discussion — **and are named here, not edited.** The two in this section are corrected.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A realistic movie title is generated, **or any film artwork is invented, or any image is fetched from anywhere** | forbidden. It is content the client will see and may take as real, and an image from an unknown source is precisely the licence problem `OPEN-ATTRIB-01` is about. **The one repo-committed placeholder is not this case** — it is authored here, it is a flat shape, and it is the same object on all eight films | *(no user-facing surface)* |
| 1a | The eight seeded films are left unpublished, or left without a poster | **the seed has produced nothing a customer can see**, `P-ADM-05` refuses publication without a poster, and the landing page reads "Nothing is showing right now." Three statements elsewhere become false and Phase 3 cannot be demonstrated. **Worth a test asserting the seeded landing page is non-empty**, alongside row 4's dashboard test | *(a customer sees "Nothing is showing right now." after a successful seed)* |
| 1b | The placeholder poster carries text, a logo, or anything resembling a title | forbidden. The moment it carries words it is content, and content is what `OPEN-ATTRIB-01` and row 1 are about. **A flat design-system shape and nothing else** | *(no user-facing surface)* |
| 2 | A fake-data library is used for names and emails | rejected. It produces **realistic** personal data, which is the opposite of what is wanted | *(no user-facing surface)* |
| 3 | Card-shaped data appears in a fixture | forbidden — no number, no last-four, no expiry, no placeholder for one. **A fixture becomes a habit** | *(no user-facing surface)* |
| 4 | Seeded bookings have no `captured` payments | the dashboard's revenue figure reads zero. Worth a test asserting the seeded dashboard is non-empty | *(a dashboard showing ₹0.00)* |
| 5 | The seed is run in the deployed environment | **nothing is ever deleted**, so seeded rows there are permanent unless the client removes them by hand. It is a one-way action in practice and the specification says so before they run it | *(no user-facing surface)* |
| 6 | A seeded lookup name reads as a real language, a real regulator's certificate or a real distributor's format | forbidden, for the same reason as row 1: it is content the client will see and may take as real, and a plausible certificate name is a claim about a regulator nobody made. Every name in the vocabulary table carries the `DEMO` prefix | *(no user-facing surface)* |
| 7 | The seed inserts a film before its vocabulary exists | `P-ADM-01`'s rule refuses it and the seed **exits non-zero without a partial catalogue**. The ordering is fixed — vocabulary, then screens and seats, then films — and it is a property of the script rather than a comment in it | *(no user-facing surface)* |
| 8 | A seat label uses the letter `I` | forbidden. The letter is skipped, so a nine-row screen ends at `J`. A label containing `I` means a second labelling implementation exists | *(no user-facing surface)* |
| 9 | A screen's seat count does not equal its rows × columns, or its three bands do not sum to its row count | the seed exits non-zero naming the screen, before its first write. **A layout that is typed rather than computed is how the two disagree** | *(no user-facing surface)* |
| 10 | The seed writes an `audit_log` row for anything it creates | forbidden. There is no honest `actor_user_id` — the seed creates the first admin itself — and `P-ADM-19` forbids both substitutes, a role name and a service account. **The absence is specified rather than left open**, and it is the only exemption from `P-XCT-03` anywhere in the product | *(no user-facing surface)* |
| 11 | The seed is run before seat labelling is settled | **all six halls freeze** under `P-ADM-14` at the first showtime insert, and no seat can be renumbered, removed or recategorised afterwards. Locally, wipe and reseed; **in the deployed environment there is no way back**, because the wipe is never run there (row 5). **This is `OPEN-SEATLABEL-01`'s deadline arriving** | *(no user-facing surface — an admin meets 409 `LAYOUT_FROZEN` later, with no clue that the seed is what closed it)* |

**Server-side validation.** Every seeded row is identifiable as seeded: a `DEMO` prefix on names and a
reserved email domain, so an operator looking at the database can tell demonstration data from real
data at a glance. **The layout is computed and then checked against itself** before anything is
written: rows × columns equals the stated seat count, the three bands sum to the row count, every band
is at least one row, and every seat label within a screen is unique. **The vocabulary is created
first and the film assignment is a pure function of the film's index**, so re-running the seed against
an existing catalogue produces the same assignment and its idempotency skip has something stable to
compare against.

**The consequence, accepted:** the demonstration looks obviously like a demonstration. If the client
wants it to look real, they supply the content.

---

### `P-XCT-31` · Contain no artificial-intelligence feature and send no customer data to a model · `RULED`
`[SRC: SRC-003 OPEN-MODEL-01]`
`[BRD: R-CON-10]`

**Behaviour.** The product has no artificial-intelligence feature. No recommendation model, no
generated copy shown to a customer, no classifier, no assistant. **No customer data is sent to any
model, at any point, by any process.**

**Who may do it.** Nobody. This is ruled and it is reserved: legal.

**Preconditions.** The application's outbound paths are exactly six — S3, SQS, SES, SSM Parameter
Store, ECR and CloudWatch Logs — and none of them is a model endpoint.

**Happy path.** Nothing happens. There is no feature to exercise.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A model API call is added to any process | forbidden, and it would also be a service outside the approved list | *(no user-facing surface)* |
| 2 | Customer data is sent anywhere for inference | forbidden | *(no user-facing surface)* |
| 3 | A "smart" default or ranking is proposed | it is ordinary code or it is not built. Listings sort by the customer's chosen filter, defaulting to newest first | *(no user-facing surface)* |

**Server-side validation.** None. **A distinction worth stating:** this governs **the product**. That
the product is *built* by reading this repository is a separate matter, and it is why the repository
holds no credential and no real customer data.

---

### `P-XCT-32` · Give every seeded account a password it can actually sign in with, without committing a credential · `RULED` in substance, `[JUDGMENT CALL]` in mechanism
`[SRC: SRC-003 OPEN-SEED-01 · SRC-003 OPEN-TLS-01 · SRC-002 §9.1 · FR-ADR-067 · FR-ADR-050 · FR-ADR-060 · FR-ADR-053 · FR-ADR-034]`
`[BRD: R-CON-09 · R-ACC-01]`

**Why this row exists — it is a Phase 2 and a Phase 4 stop, not a tidiness item.** `P-XCT-30` and
`FR-ADR-067` require the seed to create one admin, twelve managers and **fifty distinct authenticated
customers**, and `FR-ADR-034` makes those fifty a hard dependency of the concurrency proof. **Nothing
anywhere says how any of those accounts gets a password anyone can use.** Passwords are stored as
bcrypt hashes and cannot be read back (`P-XCT-06`), so there is no recovering one that was never set.
The only specified route to a first password is the reset flow, and that needs SES — which **starts
sandboxed and refuses any recipient the client has not verified** (`FR-ADR-060`), and every seeded
address is at a reserved demonstration domain nobody can verify. **Phase 2 then has no admin who can
sign in and create a movie, and Phase 4 has no fifty customers who can take a hold.** Both stop.

**Behaviour.** The seed script sets one password on every account it creates, taken from the
environment at the moment it runs.

| Rule | Statement |
|---|---|
| Where the value comes from | `SEED_DEFAULT_PASSWORD`, an environment variable with **no default** (`S7.9`) |
| What is stored | a bcrypt hash at `BCRYPT_COST`, through the same hashing function the registration path uses (`P-XCT-06`). **The seed does not have its own password code** — a second implementation is a second place the cost factor or the byte limit can be wrong |
| Which accounts get it | every account the seed creates: the admin, the twelve managers, the fifty customers |
| What is committed | **nothing.** No password, no hash, no `.env`. `.env.example` carries the variable with an obviously-placeholder value and a comment saying what it is for (`S7.9`) |
| What is printed | the **email addresses** it created, grouped by role, and the count of each. **Never the password**, not to stdout, not to a log line, not to a file — the client already has it, because they set it |
| Who runs it against the deployed environment | the client, once, deliberately (`P-XCT-30`, `FR-ADR-003`). The build session has no write access to anything in AWS and cannot run it there |

**The addresses are deterministic so the client does not need a credential printed to know who to sign
in as.** `admin-01@`, `manager-01@` … `manager-12@`, `customer-01@` … `customer-50@`, all at
`SEED_EMAIL_DOMAIN`. The identifiers are the thing that has to be discoverable; the secret is the thing
that must not be.

**`SEED_EMAIL_DOMAIN` defaults to a domain that can never exist**, `demo.frontrow.invalid`. `.invalid`
is reserved by RFC 2606 and is guaranteed never to resolve, which does two jobs at once: it satisfies
`FR-ADR-067`'s "reserved email domain, so an operator can tell demonstration data from real data at a
glance", and it makes it **impossible** for a seeded address to receive real mail by accident.

**A consequence of that domain, stated because it is a trap with a cost outside this system: the seed
enqueues no receipt job for the bookings it creates.** Every seeded address is undeliverable by
construction. In the SES sandbox those sends are rejected outright; out of the sandbox they would be
**hard bounces**, and a hard-bounce rate is charged against the sending identity's reputation and can
get an SES account suspended — which would take the real receipt path down with it (`FR-ADR-060`).
Seeded bookings therefore exist as booking rows and nothing is dispatched for them.

**What records that, stated rather than handed off.** The seed writes a `receipt_dispatch` row for
**every** seeded booking, in state **`suppressed`**, with `attempts = 0` and no dispatch timestamp.
`suppressed` means no send was ever attempted, none will be attempted automatically, and that is a
fact about the row rather than a failure of anything. **Writing no row at all was the alternative and
it is wrong**: `P-TKT-07`'s preconditions assert that a confirmed booking always has a dispatch row,
so **11,003** seeded bookings would reach a branch `P-TKT-05` calls unreachable — **a
specification with a reachable unreachable branch is the defect, not the data.** **The state itself,
its transitions and the exact words an admin sees when a resend is refused are `P-TKT-04`'s and
`P-TKT-07`'s**; what this row owns is that the seed writes the row and writes it `suppressed`.

**One password across sixty-three accounts, and the weakness accepted in writing.** It is one value,
so anyone who has it has every seeded account. That is accepted because **the environment it is used
in carries no real customer data and is never called production** (`R-CON-08`, `P-XCT-29`,
`OPEN-TLS-01`), and every account in it is demonstration data by construction. **It is not accepted
for any environment that ever carries a real person's booking**, and this row says so rather than
leaving the reader to infer the boundary. If `OPEN-TLS-01` closes and the client wants real data in
that environment, this mechanism is withdrawn and per-account credentials become a new question for
the client — a reserved one, because it is about real people's accounts.

**Who may do it.** The client runs the seed. The build session writes it (Zone A, `SRC-002 §6.1.6`)
and runs it locally only.

**How the seed is run against the deployed environment, and how the password reaches it.**

**This had to be written down, because without it Phase 2 and Phase 4 both stop at their first step.**
This row and `P-XCT-30` both assign the deployed seed run to the client and neither said how to
perform it; `S7.9` makes `SEED_DEFAULT_PASSWORD` **seed-only**, read by no container the service runs,
so it deliberately cannot ride in on the service task definition's `secrets` block — which left the
one value the whole phase depends on with no route into the environment at all.

**It is the same shape as the migration run, deliberately, so the client learns one pattern rather
than two** (`P-XCT-19`):

| | The migration run | The seed run |
|---|---|---|
| What it is | a one-off ECS task, same image | a one-off ECS task, same image |
| Entrypoint command | `migrate` | **`seed`** |
| Task definition | the service's family, command overridden | **its own family** — see below |
| Extra secret | none | **`SEED_DEFAULT_PASSWORD`** |
| Frequency | before every deploy that carries a migration | **once, deliberately** |

- **The entrypoint takes `seed` as a fourth command**, alongside `api`, `worker` and `migrate`. It runs
  `scripts/seed.py` and exits with its status. **No long-running process runs the seed and there is no
  flag that makes one**, for the same reason `P-XCT-19` gives about migrations.
- **`SEED_DEFAULT_PASSWORD` is an SSM `SecureString` at `/frontrow/<environment>/SEED_DEFAULT_PASSWORD`,
  referenced by `valueFrom` from a task definition family that is the seed's alone** — never the API's
  and never the worker's. That is what keeps `S7.9`'s seed-only rule true: **the service's task
  definition never carries the parameter**, so no container is made to refuse to boot over a value it
  never reads, and the secret still reaches the process the way `P-XCT-16` requires every secret to,
  with the application reading an ordinary environment variable and knowing nothing about SSM.
- **A separate task definition family, not the service's with an override.** Overriding a command is
  ECS's ordinary mechanism and it is what the migration run uses; overriding a command **and** adding a
  `secrets` entry is not — the secret would have to be in the shared family to be overridable, which is
  exactly what the previous bullet forbids. **Two families, one image**, so the code and the seed are
  still the same build.
- **The client builds all of it and the build session builds none of it.** The task definition, the SSM
  parameter, the execution-role grant for that parameter and the run itself are Zone C (`P-XCT-26`).
  What is owed here is the specification: the command, the variable, the parameter path, the extra
  `ssm:GetParameters` resource on the execution role, and the acceptance criterion — **sign in as
  `admin-01@` with the value that was stored**.
- **Needed by Phase 2**, and again as a hard dependency of Phase 4. It is an AWS dependency this
  section owes to `docs/30 Deployment/AWS_PREP_QUEUE.md` with that needed-by phase; **this lane writes
  nothing to that file** (`S7.16`) and names the dependency in its return instead.

**Preconditions.**
- `SEED_DEFAULT_PASSWORD` is set in the environment the seed runs in, and is not in the repository.
- It is at least `PASSWORD_MIN_LENGTH` **characters** — the same floor the registration path enforces
  (`P-XCT-06`), which is a character count and not a byte count — and at most 72 **bytes**, which is
  the bcrypt limit and is a byte bound. **The two bounds are measured in different units and that is
  not a slip.** Stating the floor in bytes, as this row previously did, would let the seed accept a
  twelve-byte password of four multi-byte characters that `P-XCT-06` refuses at registration — seeded
  accounts carrying a credential the application's own rules would not have allowed, in the row that
  spends two paragraphs on bytes not being characters.
- It is not the placeholder string `.env.example` ships with.
- The hashing function is the application's own.

**Happy path.**
1. The client sets `SEED_DEFAULT_PASSWORD` in the environment they are about to run the seed in.
2. The seed validates it, hashes it once, and reuses the hash across every account it creates —
   **one bcrypt run, not sixty-three.** At `BCRYPT_COST` 12 that is the difference between roughly
   0.3 seconds and roughly 20 seconds of pure CPU on a 1 GB host. *(the per-hash figure is
   `GOTCHAS.md`'s and is `[UNPROVEN HERE]`; the multiplication is arithmetic.)*
3. It prints the addresses and the counts.
4. The client signs in as `admin-01@…` and Phase 2 proceeds. The stress script signs in as fifty
   customers and Phase 4 proceeds.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `SEED_DEFAULT_PASSWORD` is absent | **the seed exits non-zero before writing anything**, naming the variable. Not a warning and not a generated value | *(a terminal message naming the variable — there is no user-facing surface)* |
| 2 | It is shorter than `PASSWORD_MIN_LENGTH` **characters**, or over 72 **bytes** | the seed exits non-zero naming the bound, **and the two bounds are checked in their own units** — the floor by character count, exactly as `P-XCT-06` checks it at registration, and the ceiling by byte count. **Over 72 bytes is the dangerous one**: bcrypt silently ignores the excess, so the client would set a long password and a shorter one would work | *(no user-facing surface)* |
| 3 | It equals the `.env.example` placeholder | the seed exits non-zero. **The placeholder must never become the deployed password**, and the only way to be sure is to refuse it by value | *(no user-facing surface)* |
| 4 | The seed prints the password "for convenience" | forbidden. It reaches a terminal scrollback, a CI log and a screenshot, and **a credential in a log is a committed credential with extra steps** | *(no user-facing surface)* |
| 5 | A hash is committed to the repository instead of a password | forbidden. A bcrypt hash of a known-weak password is a credential; the repository being private (`FR-ADR-071`) changes the audience and not the rule | *(no user-facing surface)* |
| 6 | The seed generates a random password per account and prints them | rejected. Sixty-three secrets the client must keep, printed into a scrollback they will lose, and no way to recover one — because `P-XCT-06` stores hashes | *(no user-facing surface)* |
| 7 | The client is told to use the password-reset flow for the first sign-in instead | **it does not work, and that is the whole reason this row exists.** SES is sandboxed and no seeded address is verified; out of the sandbox the address is `.invalid` and hard-bounces | *(the reset request appears to succeed — `P-ACC-07` answers uniformly so it cannot disclose whether an address exists — and no mail ever arrives)* |
| 8 | The seed is re-run after the client changed the admin's password by hand | the script is idempotent and **skips accounts that exist** (`P-XCT-30`), so it does not reset anyone back to the seeded value | *(no user-facing surface)* |

**Server-side validation.** All of the above runs in the seed script before its first write, so a
failure leaves the database exactly as it was. **The API and the worker never read
`SEED_DEFAULT_PASSWORD`** — it is in `S7.9`'s inventory as a seed-only variable, in its own table, so
that no container is made to refuse to boot without a value it has no use for.

**Worked example — what each phase needs and where it stops without this.**

```
Phase 2   admin creates a movie by hand
          → needs 1 account that can sign in
          → without a set password: no admin can sign in, and there is no
            other route to one.  Phase 2 stops at its first step.

Phase 4   scripts/stress_seats.py, 50 simultaneous requests for one seat
          → SRC-002 §9.1 and FR-ADR-034 require 50 DISTINCT authenticated
            customers, because the hold cap is per user (P-HLD-04) and 50
            requests from one account would be one customer holding one seat
          → without a set password: 0 of the 50 can authenticate.
            The concurrency proof — the one gate that is never waivable —
            cannot be run at all.
```

**`[JUDGMENT CALL]` — the mechanism is the build session's under Art III.9.** No frozen source and no
`APPROVED` record says how a seeded account gets a password; `FR-ADR-067` lists the accounts and stops
there. What is decided here is one environment variable, one hash, deterministic addresses and a
refusal to print. **What is not decided here** is anything about credentials for real accounts, about
rotating this value, or about who may hold it — those are the client's, and the first two are only
reachable once `OPEN-TLS-01` closes.

---


## S5 — UX specification

Five surfaces. **Global chrome only** — every product screen belongs to another lane. These are the
surfaces that can appear on top of, or around, any screen in the product, and they exist here so that
several lanes do not each invent their own version of the same thing.

Four of them are failures. **The fifth is the shell every screen renders inside**, added because the
document specified twenty-six screens, a sign-out behaviour in detail, and no control anywhere to
invoke it — see `SCR-XCT-05`.

The four failure surfaces are built from `COMPONENTS.md §6` (the error banner) over the foundations in
`COMPONENTS.md §0`; the shell is built from `COMPONENTS.md §0` alone. Every token named below exists in
`docs/05 B DesignSystem/tokens.css`. **No colour value and no contrast ratio is written here** — the
computed figures live in `docs/05 B DesignSystem/CONTRAST.md` and nowhere else.

#### The rule every `SCR-` row in this document obeys — stated here because it is not one screen's

> **A screen that names a control owes that control's words. A control specified with no published
> string is a defect, not a detail left to the implementer.**

**It applies to every `SCR-` row in every lane, not only the five below.** A control counts as named
if it appears **anywhere** in the row — the fields-and-controls table, the states table, the
accessibility focus order, or the prose. If it is named there, it has a row in that screen's copy
table or it defers **by name** to the P-row that publishes it.

**This is the obligation that follows from `S1.2.1` case 3**, which already makes the screen the owner
of any string no P-row publishes. Ownership without an obligation to publish is how a screen comes to
specify a control precisely — its tokens, its focus position, its disabled behaviour — and never say
what it reads. **The implementer then writes the words**, which means the words are decided by whoever
happens to build it, are never reviewed, and are the one part of the interface the customer actually
reads.

**Two ways to discharge it, and only two:**

1. **Publish the string** in this screen's copy table.
2. **Defer by name** to the rank-2 row that publishes it — *"`P-ACC-13` publishes it and this screen
   renders it"* — which is a discharge because a reader can follow it. **"The copy is obvious" and
   silence are not discharges**, and neither is a control whose label is assumed to equal its name.

**Why it is written as a class rather than fixed case by case:** `SCR-ACC-04` was corrected for
exactly this in an earlier pass, the correction did not generalise, and the next reader found **six**
more instances across three lanes. A defect that recurs after being fixed once is a missing rule, not
a missing edit.

**This lane's own sweep, reported rather than claimed — and it found things.** All five `SCR-XCT-`
rows were walked: every control in every fields-and-controls table, every states table and every
accessibility focus order, checked against that screen's copy table. **Controls checked: 24. Strings
added: 6. Deferrals made explicit: 2.**

| Screen | Found | Done |
|---|---|---|
| `SCR-XCT-01` | the **banner action** was specified as *"present only where there is an action"* and never labelled, and no row said which codes carry one | published `Choose seats again` and `Reload this record`, and stated that **every other code's banner carries no control** — the absence specified rather than left open. **3 strings** |
| `SCR-XCT-02` | the **retry action** was specified down to its tokens and its accessible-name *shape* — *"says what will be retried, not 'Retry' alone"* — with **no words anywhere**. A rule about a label, and no label | published `Try holding these seats again`, `Try paying again` and `Try again` as the named fallback. **3 strings** |
| `SCR-XCT-03` | its only control is **another screen's** — the action that tripped the limit — which this row leaves enabled and untouched | **nothing owed.** A screen owes words for controls it introduces, not for ones it declines to modify |
| `SCR-XCT-04` | a **third variant** of another row's string | now defers to `P-ACC-13` by name. **1 deferral** |
| `SCR-XCT-05` | the shell — the only row here specifying ordinary navigation | **clean.** Skip link, wordmark, all nine nav links, sign-in, sign-out, both accessible names and the footer all carry published words |

**The two gaps are worth naming because of what they have in common.** Neither screen was vague: both
specified their control's tokens, its behaviour and — in `SCR-XCT-02`'s case — a **rule about what its
accessible name must say**. What both omitted was the words themselves. **A screen can specify a
control in complete detail and still not have said what it reads**, and that is precisely the shape
this rule exists to catch: the omission does not look like an omission, because the row around it is
thorough.

---

### `SCR-XCT-01` · The failure surface
**Route.** any · **Who reaches it.** guest · customer · manager · admin · **Component basis.** `COMPONENTS.md §6`

**What the user arrives with / leaves with.** They arrive with a request that failed. They leave
knowing what happened, whether anything changed, and — on a 5xx only — a short code they can quote.
**They never leave with a stack trace, a table name, a hostname or an exception class.**

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Container | `--fr-surface-danger`, `--fr-radius-md`, padding `--fr-space-3`, 1px `--fr-control-edge` | **Pinned to the top of the viewport for as long as it is live**, in the page's own scroll context — never inside a component's scroll container, and never riding a sticky application header, because `SCR-XCT-05` marks that header `Not sticky` and the seat map's container scrolls horizontally only (`COMPONENTS.md §1.3`). It reserves its own height rather than overlaying content, so a focused control is never obscured by it (WCAG 2.2 SC 2.4.11). A banner is not permanent chrome: it exists only while there is a message and is removed with it, which is why it may pin where a header may not. **A screen that owns a surface may place its own banner differently and this row defers to it by name** — `SCR-SEA-03` does, for the seat map (`S1.2.1` case 6) | — |
| Leading rule | 3px `--fr-danger-ink` down the leading edge | Non-colour cue: the banner is identifiable without colour perception | — |
| Message | `--fr-ink-on-danger`, `--fr-text-sm`, `--fr-leading-body` | One sentence saying what happened, one saying what to do next where there is something to do | — |
| Named values in the message (seat labels, counts, seconds) | `--fr-font-mono`, `--fr-weight-bold` | Taken from the error envelope's `details`, never parsed out of `message` | — |

**The server renders `message` and the client does not compose it.** `message` arrives ready to
display, in one language (`P-SCP-04`), and the client's only job is to render it. `details` exists so
the interface can **act** — highlight two seats, disable a control, start a timer — not so it can
rebuild the sentence. A client that assembles copy from `details` would be a second implementation of
every string in this document.

**`details` keys, by code.** A code not listed here carries no `details`, and a client must render
correctly when the object is absent:

| Code | `details` | What the interface does with it |
|---|---|---|
| `SEAT_UNAVAILABLE` | `unavailable_seats`: array of seat labels | marks exactly those seats unavailable on the map and names them in the banner |
| `SEAT_LIMIT_EXCEEDED` | `max_seats`, `currently_held`, `requested` — three integers | states the cap and the two counts without the client counting anything itself |
| `SALES_CLOSED` | `sales_closed_at`: ISO-8601 instant, UTC | renders the local closing time, and disables the map |
| `RATE_LIMITED` | `retry_after_seconds`: integer, matching the `Retry-After` header | starts the countdown on the retry control |
| `HOLD_EXPIRED` | *(none)* | returns to the map and re-applies the previous selection |
| `SHOWTIME_OVERLAP` | `conflicting_showtimes`: array of `{id, film_title, starts_at, ends_at}`, the instants serialised with the cinema's offset | outlines each conflicting row in the day strip by `id`, and names them in the banner |
| `VALIDATION_FAILED` | `field`, and `bound` where the field has one | marks that field and shows the message against it |
| `REQUEST_INVALID` | `field` where one can be named | as above; absent when the body did not parse at all |
| `PAYMENT_FAILED` | `hold_survived`: boolean | chooses between the two sentences `P-HLD-14` publishes for this code |
| `INTERNAL_ERROR` | *(none — `request_id` is a top-level field, not a detail)* | shows the request id for the customer to quote |
| Action inside the banner | `--fr-accent-ink`, underlined, minimum target `--fr-tap-min` | Present only where there is an action. Focusable, with the standard focus treatment | — |
| Request id line | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | **Rendered on 5xx only.** Never on a 4xx | — |
| Arrival | `--fr-motion-base`, `--fr-ease-out` | Collapses to 1ms under `prefers-reduced-motion` | — |

**States.**

| State | What renders |
|---|---|
| **Empty** | Nothing. The banner is **absent**, not collapsed to zero height, so it occupies no space and no place in the focus order. |
| **Loading** | Not applicable — the banner is the result of a completed request, never a pending one. |
| **Error** | One banner, keyed on the envelope's `code`. The interface branches on `code`, never on `message`. |
| **Success** | Not applicable. |
| **Partial** | `SEAT_UNAVAILABLE` is the partial case: the seats that went are named and marked `sold` on the map immediately, and **the rest of the selection stays exactly as it was.** |
| **Several at once** | One banner. The newest message replaces the previous one; errors do not stack into a wall. |
| **Dismissible** | Only errors with nothing left to do. `SEAT_UNAVAILABLE` is not dismissible — it clears when the customer changes the selection. |

**Copy.**

| Code | Verbatim |
|---|---|
| `INTERNAL_ERROR` | "The server could not complete this request. If you need help, quote `a1b2c3d4`." |
| `NOT_FOUND` | "That page does not exist." |
| `FORBIDDEN` and `AUTH_REQUIRED` | **deferred — see below. This row publishes a last-resort default and does not compete with the endpoint-specific strings.** |
| Banner action, `HOLD_EXPIRED` | `Choose seats again` — **on every surface except the seat map. `SCR-SEA-03` owns the seat map and there the code carries no control at all.** |
| Banner action, `VERSION_CONFLICT` | `Reload this record` |
| Banner action, every other code | **none.** The banner carries words and no control, and the absence is specified rather than left open |

**`REQUEST_INVALID` had no published sentence anywhere, and the gap was provable inside the
document.** The rule that fixes this code's status and wording *"once here and nowhere else"* published
no string, this table covered seven codes and not this one, and **this row's own rule says the server
renders `message` and the client never composes it** — so the one thing that was certain was that no
component was allowed to invent it. The proof: the same rule moves `P-ADM-17`'s rejected `role` field
to `400` and says *"its sentence does not change"*, and `P-ADM-17` publishes no sentence for it to keep.

**It is written to read correctly to an admin**, because an admin is who meets it most: this code fires
on a body carrying a property the endpoint does not define, which is what an admin form does when it
round-trips a field the server has since stopped accepting. **"Nothing was changed" is the load-bearing
half** — the reader was mid-edit and needs to know the record is untouched — and it is the same clause
`METHOD_NOT_ALLOWED` uses, deliberately, because both are "the request never reached the work".
**"Reload the page and try again" is the only honest instruction**: the fault is in what the client
sent, so retrying the same submission fails identically, and a fresh page is what replaces it. **It
does not blame the reader**, who did nothing wrong and could not have.

**`SHOWTIME_OVERLAP` was missing from the `details` table above, and its absence was a denial.** This
table states that *a code not listed here carries no `details`* — so while `P-ADM-08` requires the
payload and `SCR-ADM-03` needs the `id` to outline the conflicting row in the day strip, **this
registry was saying there was none.** The key follows the house shape every other payload uses, a
named array rather than a bare list (`unavailable_seats`, `duplicate_labels`, `frozen_fields`).
**Lane E6's `newerrorcode` block is where the shape is fixed**; this row carries it so the registry
stops contradicting it, and if E6 names the keys differently theirs wins and this row follows.

**`HOLD_EXPIRED` carries no banner action on the seat map, and this row defers there by name.**
`SCR-SEA-03` owns the seat map and rules that `DEPENDENCY_UNAVAILABLE` is the only code carrying a
control on it, with `HOLD_EXPIRED` re-applying the selection automatically. **Both rows are rank 3 and
both cover that one surface**, so neither outranked the other — the general case is now `S1.2.1` case
6: **where two rank-3 screens cover one surface, the screen that owns the surface wins and the
cross-cutting registry defers for that surface while keeping its entry as the rule everywhere else.**
**The reason is not precedence, it is that the button would do nothing:** a customer meeting
`HOLD_EXPIRED` on the seat map is **already on the screen `Choose seats again` would send them to**,
and a control that navigates a reader to where they are standing is worse than no control. Everywhere
else — the checkout screen, the bookings list — the customer is elsewhere and the action is real.

**`FORBIDDEN` and `AUTH_REQUIRED` defer, because seven per-endpoint strings already exist.** Rank-2
P-rows across the account, admin, dashboard and booking lanes each publish wording for the specific
thing the caller could not reach, and under `S1.2` each of those beats this rank-3 registry on its own
surface. **Publishing a general sentence here would have made an eighth string for one code**, and the
eighth would be the one that is never quite right — a manager refused another hall's dashboard needs
different words from a customer refused another customer's booking, and neither is served by a
sentence that avoids saying which.

**The default, used only where no P-row publishes one for that surface**, so a code can never render
with nothing:

| Code | Last-resort default |
|---|---|
| `AUTH_REQUIRED` | "Sign in to continue." |
| `FORBIDDEN` | "This account does not have access to that page." |

**A lane that finds itself rendering either of those two has found a gap in its own rows**, not a
finished string, and the right fix is a sentence on the owning P-row rather than a variant here.
| `VALIDATION_FAILED` (form level) | "Some fields need attention." |
| `VERSION_CONFLICT` | "Someone else changed this record while you were editing it. Reload it and make the change again." |
| `DEPENDENCY_UNAVAILABLE` (**a read** — the request fetched and wrote nothing) | "This could not be loaded right now. Nothing was being saved, so nothing was lost. Try again in a moment." |
| `METHOD_NOT_ALLOWED` | "That action is not available. Nothing was changed." |
| `REQUEST_INVALID` | "That request could not be read and nothing was changed. Reload the page and try again." |

**`METHOD_NOT_ALLOWED` is published once, here, and reused everywhere.** It is **generic and
entity-blind** by necessity, not by preference — it is rendered by a global handler that runs after
routing has already failed, so it cannot know what was addressed (`P-XCT-11`). **No lane publishes a
variant naming a film, a showtime or a lookup row**; those sentences belong in the never-deleted note
on each admin screen, which is where an admin reads them. **It covers two cases and only two** — a
`DELETE` at one of the never-deleted entities, and **any non-`GET` method at a path on the read-only
reports router** (`P-RPT-09`, `P-XCT-05` exception 5b), where the same sentence is the right answer
for the same reason: the address exists, the verb does not, and nothing was changed. A `DELETE` of a
seat is a real, mounted, sometimes-successful route (`EP-ADM-21`) and never reaches
this sentence. **The code appears in no `errors` array until the merge owner registers it**
(`P-XCT-11`), so a lane that finds it missing from `contract.json` has found the expected state and
not a defect.

**`DEPENDENCY_UNAVAILABLE` has two sentences, and which one applies is a property of the request, not
of the lane.** They are registered here because the code is cross-cutting and a per-lane variant of a
shared sentence is how one code ends up with five strings.

| The request | Sentence | Owner |
|---|---|---|
| **Writes, or would have written** | "The system cannot reach its database right now. Nothing was saved. Try again in a moment." — with the dependency named where the lane knows which one failed, and the object named where something specific was not saved | the admin section, which publishes it and its S3 variants |
| **Only reads** | the row above: "This could not be loaded right now. Nothing was being saved, so nothing was lost. Try again in a moment." | **this row** |
| **Was refused by the rate limiter failing closed**, rather than by the dependency the request needed | "That is unavailable right now. Try again in a few minutes." | `P-XCT-07`. It is neither of the two above: nothing was attempted at all, so neither "not saved" nor "not loaded" is true |
| **Is the seat-map read or one of its polls** | `P-BRW-12` publishes it and **declares ownership** | `P-BRW-12` |

**Three things a lane picking one needs, stated so it is choosing rather than guessing.**

1. **"Nothing was saved" is false on a `GET`** and is the defect this pair exists to prevent. A read
   sentence that claims a write was rolled back describes work the request never did.
2. **The read sentence names no dependency**, deliberately. A read can fail on PostgreSQL, on Redis or
   on S3, and a customer cannot act on which — where a lane *does* know and the distinction is useful
   to an **operator-facing** surface, that belongs in the log line, not in the copy.
3. **A P-row that already publishes its own sentence for this code keeps it.** This is a default for
   the silence, not a replacement, and `S1.2` already ranks a rank-2 row above this rank-3 registry.
   **Two such sentences exist today and both stay**: `P-BRW-12`'s seat-map string, and the browse
   section's "The site is temporarily unavailable. Please try again in a moment." for a public read
   that cannot reach PostgreSQL — which is scoped to the public browse surface and reads oddly on an
   admin list, which is why the default above exists rather than that one being stretched to cover it.

**Not written here, deliberately:** any sentence shown to a customer whose receipt has definitively
failed after payment was captured. That is `OPEN-EMAILFAIL-01`, it is reserved to the client, and
**writing a plausible sentence for it would be filling in an open row.**

**Accessibility.** The banner is announced through a live region — an error that is only red has not
been reported. It receives focus only when it carries an action; otherwise focus stays where the user
left it. Its action sits in the tab order immediately after the control that produced the error. The
leading rule is the non-colour cue. The request id is selectable text, never an image.

---

### `SCR-XCT-02` · The dependency-unavailable notice
**Route.** any · **Who reaches it.** customer · manager · admin *(a guest never reaches a Redis-dependent write path)* · **Component basis.** `COMPONENTS.md §6`

**What the user arrives with / leaves with.** They arrive having tried to hold, confirm, or use a
rate-limited path while Redis is unreachable. They leave knowing that **the failure is on our side,
that browsing still works, and that nothing they did caused it.**

**The boundary against `SCR-XCT-01`, stated so the two do not overlap.** This screen is the notice for
a **Redis-dependent action** — a hold, a confirm, a release, or any path the limiter refused by
failing closed — and it carries a retry action and the reassurance that browsing continues. **A plain
read that returns `DEPENDENCY_UNAVAILABLE` renders through `SCR-XCT-01`'s banner instead**, with the
read sentence registered in that row's copy table, because there is no partially-working state to
explain and nothing about the rest of the product to reassure the reader about.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Container | as `SCR-XCT-01` | The same component, a different message | — |
| Message | `--fr-ink-on-danger`, `--fr-text-sm` | States what is unavailable and what still works | — |
| Retry action | `--fr-accent-ink`, underlined | Re-issues the request on a press. **No automatic retry loop** — a client that retries a 503 in a tight loop makes an outage worse | — |
| The seat map behind it | unchanged | The map already on screen keeps rendering. **It is not blanked**, because what is on screen was correct when it was fetched. **It does not refresh**: the seat-map read is rate-limited and the limiter fails closed, so the next poll returns 503 and the map on screen is the last successful read (`P-XCT-09`) | — |

**States.**

| State | What renders |
|---|---|
| **Empty** | Nothing — Redis is reachable. |
| **Loading** | The action shows its pending treatment for the duration of the configured Redis timeout, which is short by design. |
| **Error** | The banner, with the retry action. |
| **Success** | The banner clears and the hold proceeds. |
| **Partial** | The movie list and the showtime list continue working while holds do not, and while the seat-map **refresh** does not either — that read is rate-limited and the limiter fails closed (`P-XCT-09`). **This is the designed state, not a half-failure to hide.** |

**Copy.**

| Situation | Verbatim |
|---|---|
| Hold or confirm while Redis is down | "Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes." |
| A rate-limited path while Redis is down | "That is unavailable right now. Try again in a few minutes." |
| A seat-map refresh while Redis is down | **deferred to `P-BRW-12`, which owns this code on this endpoint and publishes the one string for it.** This screen renders that string and no variant of it. It is deliberately not copied here: a copy is a copy that can go stale, which is exactly how three different sentences for this one situation came to exist (`S1.2`, rank 4) |
| Redis restarted and live holds were lost | "Your seats were released. Choose them again if they are still free." |
| Retry action, after a refused **hold** | `Try holding these seats again` |
| Retry action, after a refused **confirm** | `Try paying again` |
| Retry action, anywhere else on this surface | `Try again` |

**The retry action's words are published here because this screen owns them.** No P-row publishes a
label for it — the P-rows publish the banner's *sentence*, not the control's — so under `S1.2.1` case
3 the screen is the owner, and **owning it means publishing it** (S5's preamble rule). The accessible
name is the label above, never the bare word "Retry": *"Retry"* alone tells a screen-reader user that
something will be retried and not what, and this banner can appear over a hold, a confirm or a
rate-limited path. **`Try again` is the fallback only where the refused action has no more specific
name**, and it is listed so the fallback is a decision rather than a gap.

**Accessibility.** Announced through the same live region. The retry action is keyboard-operable and
its accessible name says what will be retried, not "Retry" alone. The seat map behind the banner
keeps its own focus position.

---

### `SCR-XCT-03` · The rate-limit notice
**Route.** any limited endpoint · **Who reaches it.** guest · customer · manager · admin · **Component basis.** `COMPONENTS.md §6`

**What the user arrives with / leaves with.** They arrive having made more requests than the bucket
allows. They leave with **a real wait**, computed from that bucket's refill rate and rendered by
S7.20's rule, rather than a generic failure.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Message | `--fr-ink-on-danger`, `--fr-text-sm` | Carries the wait, rendered by **S7.20** — seconds below 120, whole minutes rounded up at 120 and above | — |
| The number | `--fr-font-mono`, `--fr-weight-bold`, `font-variant-numeric: tabular-nums` | Read from the `Retry-After` header, never guessed by the client. **The header is always seconds; the unit word in the sentence is S7.20's, not the header's** | — |
| Countdown | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | Counts to zero from the `Retry-After` seconds it was given, then the banner clears itself. **It is a live timer rather than a rendered duration**, so S7.20 does not govern its ticking display. It is **not** re-derived by the client: a further refusal returns a smaller number and the banner takes the new one | — |
| The action that tripped it | **unchanged — it keeps its ordinary enabled treatment** | **It stays enabled.** The customer may press it again and **the server is the thing that says no.** This reverses what this row said in its previous revision | — |

**States.**

| State | What renders |
|---|---|
| **Empty** | Nothing. |
| **Loading** | Not applicable. |
| **Error** | The banner with the wait. **No control is disabled.** |
| **Success** | At zero the banner clears. **Nothing is submitted automatically**, and nothing was disabled to be re-enabled. |
| **Partial** | Not applicable — every control on the screen stays enabled, including the one that was refused. |

**The control stays enabled, and this reverses what this row said before.** `SCR-ACC-01` already
reasons this way — *the primary action stays enabled: the customer may try again, and the server is
the thing that says no* — and that is the product's general stance rather than one screen's local
choice, so this row adopts it rather than two rank-3 rows disagreeing about one situation.

**The reason is that a client-side countdown is a second clock.** It starts from a number the server
computed at the moment of refusal, and from then on it runs on the customer's device, against that
device's clock, through a backgrounded tab and a sleeping laptop. **It drifts.** A control disabled by
the drifted clock refuses a request **the server would have allowed** — the product denying something
nobody asked it to deny, with no record anywhere that it happened. Under `S7.20`'s corrected
arithmetic that is the likelier direction of error, not the rarer one: the tabulated figure is the
**maximum**, so a customer who waits and retries is frequently allowed *earlier* than the countdown
they were shown. **The server holds the authority on whether a request is refused, and it is the only
thing that does.**

**The failure this gives up, stated rather than hidden:** a customer who presses repeatedly spends
more requests, each of which is counted and each of which is refused. That is a bounded cost the
limiter is designed to absorb — it is the limiter working — and it is the cheaper of the two failures.

**Copy.**

| Situation | Verbatim |
|---|---|
| Seat hold limit — 20 per minute per user, so `60 / 20 = 3` s | "Too many requests. Try again in 3 seconds." |
| Sign-in limit — 30 per 15 minutes per IP, so `900 / 30 = 30` s | "Too many attempts. Try again in 30 seconds." |
| Registration or password-reset limit — 5 per hour per IP, so `3600 / 5 = 720` s | "Too many attempts. Try again in 12 minutes." |

**The number is never typed into the copy.** It is substituted from `Retry-After`, which is computed
from the refusing bucket's refill rate (`P-XCT-07`, S7.4) — **the window divided by the capacity, not
the window itself** — and then rendered by **S7.20**: seconds below 120, `ceil`-ed whole minutes at
120 and above. Each row above names the bucket it was derived from so the figure can be checked rather
than trusted, and **S7.20 tabulates the derivation for every bucket in the product.** These three are
this screen's generic examples; **where an endpoint's own P-row publishes wording for its limit —
`P-ACC-01`, `P-ACC-02`, `P-ACC-07`, `P-XCT-06` — that wording wins and this screen renders it.** It
never blames the customer and it never says "slow down".

**One surface is deliberately not this screen's, and it is the seat map — on its POLLS.** A 429 on one
of the seat map's polls renders `SCR-BRW-03`'s string — `"Too many requests. The seat map will update
again shortly."` — and **this row publishes no variant for it.** `P-BRW-11` publishes no string, so
under `S1.2.1` case 3 the screen that renders it owns it, and that screen is `SCR-BRW-03`. **The
reason is not precedence, it is that this row's sentence would be wrong there:** the map re-polls on
its own every `SEATMAP_POLL_INTERVAL_SECONDS`, so there is nothing for the customer to do and telling
them to try again asks them to take an action the client is already taking. **Every other sentence on
this screen tells the customer to act because on every other surface they must.**

**A 429 on the seat map's FIRST load is not that case, and this row previously swept it in.** There is
no map on screen and **no poll loop is running**, so nothing will deliver the update that sentence
promises. `P-BRW-11` exception 4 governs it: the first-load error and a `Try again`, which is the one
control that can produce the map (`SCR-BRW-03`). **This row publishes no string for that case either**
— the distinction is which of `SCR-BRW-03`'s two strings applies, not a third sentence.

**Accessibility.** Announced once when it appears, **not on every countdown tick** — a live region
that updates every second is unusable with a screen reader. The ticking countdown is `aria-hidden`
and the single announcement carries the wait. **The control gains no `aria-disabled` and no
`disabled`**, because it is not disabled: it keeps its ordinary accessible name and its ordinary
state, and **the banner is what tells the customer to wait.** Announcing a state the control does not
have is worse than announcing nothing — it tells a screen-reader user the action is unavailable when
pressing it may well succeed.

---

### `SCR-XCT-04` · The session-expiry return
**Route.** any authenticated route · **Who reaches it.** customer · manager · admin · **Component basis.** `COMPONENTS.md §11` over `COMPONENTS.md §6`

**What the user arrives with / leaves with.** They arrive having been signed out mid-flow. They leave
signed in and back where they were, **with their seat selection intact.**

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Notice | `--fr-surface-danger`, `--fr-ink-on-danger`, `--fr-text-sm` | Explains the sign-out **before** the form, not after it | — |
| Sign-in form | `COMPONENTS.md §11`, `--fr-surface-raised`, `--fr-shadow-sheet` | Two tabs, sign in and register, one destination | Email and password exactly as `P-XCT-06` specifies |
| Preserved context | — | **The path they were on**, plus any seat ids and showtime, written to `sessionStorage` **before** the authentication step and restored after it | — |
| Return action | `--fr-surface-accent`, `--fr-ink-on-accent`, minimum target `--fr-tap-min` | Returns to the original surface with the selection re-applied | — |

**States.**

| State | What renders |
|---|---|
| **Empty** | Not applicable — this surface exists only after an expiry. |
| **Loading** | The sign-in action shows its pending treatment while bcrypt runs, which is not instant by design. |
| **Error** | A sign-in failure renders inside the form, beside the field, not as a page-level banner. |
| **Success** | The customer returns to the original surface with the selection re-applied. **The hold is not taken automatically.** |
| **Partial** | If a seat has gone while they were signing in, it is shown as taken in the restored selection and they adjust before pressing again. **The words are `P-ACC-13`'s**, which publishes a singular, a plural and an all-gone variant; this screen selects among them and composes none. |

**Copy.**

| Situation | Verbatim |
|---|---|
| Session expired mid-flow, with a selection | "You were signed out. Sign in again to continue. Your seat selection has been kept." |
| Session expired with no selection to keep | "You were signed out. Sign in again to continue." |
| A seat went while they were signing in | **`P-ACC-13` publishes it and this screen renders it. This row publishes no string for this case.** |

**Why that last row defers, when the two above it do not.** A seat going while the customer was
signing in is **exactly** `P-ACC-13`'s situation — it is the return from sign-in or registration — and
`P-ACC-13` is a rank-2 row, so under `S1.2` it owns the words and this rank-3 screen renders them. It
publishes a **singular, a plural and an all-gone** variant, which this screen could not have matched
by publishing one sentence.

**This row previously published `"C12 is no longer available. Your other seats are still selected."`
and that was a defect** — a **third** variant of a situation the document had already split into two,
and worse, one assembled from both halves of the split: it opened with `P-SEA-03`'s wording (*is no
longer available*, the no-sign-in-involved case) and closed with `P-ACC-13`'s (*your other seats are
still selected*, the sign-in case). **A sentence that borrows from both sides of a deliberate
distinction erases the distinction.** The two situations and their owners are:

| Situation | Owner |
|---|---|
| The local selection is re-checked against a fresh map and a seat has gone. **No sign-in involved** | `P-SEA-03` (lane E2) |
| **The customer returns from sign-in or registration** and a seat has gone | `P-ACC-13` (lane E5) — the case this screen is about |

**This surface owns where re-authentication lands, and it preserves the path.** Previously the only
preserved context was seat ids and a showtime, which answers the question for one journey and silently
drops every other: **an admin whose session expired mid-edit was returned to the movie listing**, and a
manager reading a dashboard to `/`. The path is stored because it is the thing that is always true —
every reader who meets this surface was somewhere, and only some of them were choosing seats.

**Why this row owns it rather than the sign-in screen.** `SCR-ACC-01` also states where sign-in sends
you, and both rows are rank 3 on one surface — resolved by `S1.2.1` case 6, **the screen that owns the
surface wins**, and the surface here is the 401 interstitial: it is where the reader is standing when
the question arises, and it is the only one of the two that knows what they were interrupted doing.
**`SCR-ACC-01` keeps its own rule for a deliberate sign-in** — someone who navigated to sign in of
their own accord, who was interrupted by nothing and has no path to restore — and says which of the
two it describes. **The two rules are not in competition; they answer different questions** that were
sharing one sentence.

**What is restored, and what is not.** The path is restored and the reader lands where they were. **A
seat selection is restored as a selection, never as a hold** — the hold is not re-taken, for the reason
below — and **no form input is preserved**: this row stores a route, not a draft, and claiming
otherwise would promise a recovery the product does not implement. An admin returns to the page they
were editing with the stored record as it stands on the server, which is the honest state.

**Why the hold is not re-taken automatically:** between selecting and returning, a seat may have gone.
Taking a hold automatically would either silently drop the missing seat — the customer pays for three
of the four they chose — or fail immediately after a successful sign-in, which reads as the sign-in
having failed. **Restoring the selection and letting them press once removes both.**

**Accessibility.** Focus moves to the notice, then to the first form field. The notice is announced.
Every input has a programmatically associated label; errors are associated with their field and are
announced, not only coloured. Focus order follows visual order and the focus ring is visible against
`--fr-surface-raised`.

---

### `SCR-XCT-05` · The application shell — header, navigation, sign-out and footer
**Route.** every route in the product · **Who reaches it.** guest · customer · manager · admin ·
**Component basis.** `COMPONENTS.md §0` (the page frame, focus, numbers)

> **Why this exists, stated plainly.** Every other screen in this document specifies what sits inside
> the content column and nothing specifies what sits around it. `P-ACC-05` specifies signing out in
> detail — the endpoint, the cleared cookie, the `204`, what it does and does not revoke — **and no
> screen in the document contains a control that invokes it.** No screen links to any other screen:
> an admin who reaches `/admin/movies` has no route to `/admin/showtimes`, and a customer who books
> has no route to their own bookings. This row is the shell, and it is deliberately the smallest thing
> that makes the product navigable. **This is a demonstration product; the shell is a header, a nav, a
> sign-out control and one line of footer, and it is not a design exercise.**

**What the user arrives with / leaves with.** They arrive on any route. They leave able to reach every
other area their role may reach, and — if signed in — able to sign out from anywhere.

**Structure.** Three landmarks and nothing else: `header` (banner), `main`, `footer` (contentinfo).
The content column inside `main` is `--fr-page-max`, centred, with the page gutter of
`COMPONENTS.md §0.1`. **The shell never scrolls horizontally and never introduces a second scroll
container** — the seat map's own horizontal scroll lives inside `main` and is unaffected
(`FR-ADR-044`).

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Skip link | `--fr-surface-accent`, `--fr-ink-on-accent`, `--fr-radius-sm`, padding `--fr-space-2` | **The first focusable element on every page.** Visually hidden until focused, then visible at the top-left. Moves focus to `main` | — |
| Header bar | `--fr-surface-raised`, 1px `--fr-rule` on the bottom edge only, padding `--fr-space-3` on a phone and `--fr-space-4` above 40rem | Full width; its contents are held to `--fr-page-max` and centred. **Not sticky** — a sticky header steals vertical space from a 220-seat map on a 375px phone, which `P-XCT-25` is about | — |
| Wordmark | `--fr-font-display`, `--fr-text-lg`, `--fr-weight-black`, `--fr-track-tight`, `--fr-ink-strong` | A link to `/`. It is the only route back to browsing from anywhere | — |
| Primary nav | `--fr-text-sm`, `--fr-ink`, gap `--fr-space-4`; the current area at `--fr-weight-bold` `--fr-ink-strong` | One `nav` landmark. Links only — **no dropdown, no menu, no hamburger.** The longest list is the admin's and it fits | — |
| Current-area marker | `--fr-weight-bold` **and** `aria-current="page"` | Weight is the visible cue and `aria-current` is the programmatic one. **Colour is not the carrier** | — |
| Account control | `--fr-text-sm`, `--fr-ink-muted`; the address in `--fr-ink` | Signed in: the account's own email address, truncated with an ellipsis past 24 characters and never truncated in its accessible name. Not a link | — |
| Sign-out control | transparent, 1px `--fr-control-edge`, `--fr-accent-ink`, `--fr-radius-md`, min height `--fr-tap-min` | Calls the sign-out endpoint (`P-ACC-05`), then navigates to `/`. **The only sign-out control in the product** | — |
| Sign-in link | `--fr-accent-ink`, underlined, min target `--fr-tap-min` | Shown to a guest only. Goes to `/sign-in` | — |
| Footer | `--fr-ink-muted`, `--fr-text-xs`, `--fr-surface-base`, 1px `--fr-rule-quiet` on the top edge, padding `--fr-space-4` | One line. No links, no columns, no social anything | — |
| Environment line | `--fr-ink-muted`, `--fr-text-xs` | The demonstration notice, below | — |

**What each role sees in the primary nav**, in this order, left to right:

| Role | Nav | Account area |
|---|---|---|
| **guest** | *(nothing — the wordmark is the only navigation, because every route a guest may reach is reachable from `/`)* | `Sign in` → `/sign-in` |
| **customer** | `My bookings` → `/account/bookings` | the email address, then `Sign out` |
| **manager** | `Dashboard` → `/dashboard` · `My bookings` → `/account/bookings` | the email address, then `Sign out` |
| **admin** | `Dashboard` → `/dashboard` · `Change log` → `/dashboard/audit` · `Films` → `/admin/movies` · `Showtimes` → `/admin/showtimes` · `Pricing` → `/admin/pricing` · `Halls` → `/admin/halls` · `Managers` → `/admin/managers` · `Lists` → `/admin/lookups` · `My bookings` → `/account/bookings` | the email address, then `Sign out` |

**Three rules that keep the nav honest**, each of which is a defect if broken:

- **A link a role may not follow is never rendered for that role.** A manager sees no admin link at
  all — not disabled, not greyed. The nav is built from the same role the router's authorisation
  dependency reads (`P-XCT-05`), so the two cannot disagree.
- **The nav is not the authorisation boundary and nothing depends on it being right.** Every route
  behind every link is enforced server-side, once, on the router (`P-XCT-05`). A hand-typed
  `/admin/movies` from a manager's browser returns `403` and `SCR-XCT-01`'s `FORBIDDEN` copy. **Hiding
  a link is presentation; refusing the request is the control.**
- **`Change log` is admin-only, matching `SCR-RPT-02`.** A manager reaching `/dashboard` sees the
  dashboard and no audit link, because `SRC-003 OPEN-OPS-03` makes every privileged read of the audit
  trail the admin's.

**States.**

| State | What renders |
|---|---|
| **Guest** | Wordmark and `Sign in`. No account area, no nav links. |
| **Signed in** | Wordmark, the role's nav, the address, `Sign out`. |
| **Loading — the role is not yet known** | The header draws at **full height** with the wordmark, and the nav and account areas as `--fr-surface-inset` blocks at their final width. **The header never resizes when the role lands**, and no nav is rendered speculatively: a link that appears and then vanishes is worse than one that arrives late. |
| **Error — the session check failed** | The shell renders as **guest**. It never blocks the page: the content behind it is public on most routes, and a route that is not public will return `401` on its own request and `SCR-XCT-04` takes over. |
| **Sign-out in flight** | The control shows its pending treatment and is disabled. **A second press does nothing** rather than firing a second request. |
| **Sign-out failed** | The client discards its own in-memory state and navigates to `/` anyway. **Signing out must not be blockable by a failed request** — the cookie is `HttpOnly` so the client cannot clear it itself, and this is stated rather than hidden: the session survives on the server until `exp` or a password change (`P-ACC-05`), and the honest surface is that the browser is returned to a signed-out view. |
| **Offline or 5xx on the page behind it** | The shell still renders. It is the only thing on screen that still works, and it is how the reader gets somewhere else. |
| **Empty** | Not applicable — the shell is present on every route. |

**Copy.**

| Where | Verbatim |
|---|---|
| Skip link | `Skip to content` |
| Wordmark | `FrontRow` |
| Nav, customer | `My bookings` |
| Nav, manager | `Dashboard` · `My bookings` — **two links, matching the structure table above.** A manager is read-only and reaches no admin route (`P-XCT-05`, `S7.5`), so publishing the admin set here would have specified a nav that renders links the router refuses |
| Nav, admin | `Dashboard` · `Change log` · `Films` · `Showtimes` · `Pricing` · `Halls` · `Managers` · `Lists` · `My bookings` |
| Sign-in link | `Sign in` |
| Sign-out control | `Sign out` |
| Sign-out accessible name | `Sign out of admin-01@demo.frontrow.invalid` |
| Account area accessible name | `Signed in as admin-01@demo.frontrow.invalid` |
| Footer | `Demonstration environment. Payments are simulated and no card details are ever taken.` |

**The footer line is not decoration and it is not marketing.** `FR-ADR-041` requires the simulated
provider to be visible rather than silent, and `P-XCT-29` and `FR-ADR-069` require the deployed
environment never to be called production. One line discharges both on every screen. **It says
"Demonstration environment", never "staging", never "production", never a version number and never a
build hash** — a hash in a footer is an internal detail on a public page, and it is the sort of thing
added without a reason.

**Accessibility.**

- **Landmarks:** exactly one `banner`, one `main`, one `contentinfo`, and one `navigation` inside the
  banner. `main` carries the id the skip link targets and is focusable programmatically.
- **Focus order:** skip link, wordmark, nav links in their rendered order, account area, sign-out,
  then `main`. It follows visual order, which `COMPONENTS.md §0.2` requires.
- **The skip link is first, always.** With the admin's nav that is nine controls between the top of
  the page and the content on every single page load; without it a keyboard user tabs through all
  nine to reach the seat map, on every navigation.
- **Focus after navigation** moves to the `h1` of the destination and the route change is announced
  once in a polite live region. Focus is never left on a link that no longer exists.
- **Focus after sign-out** moves to the `h1` of `/`. Focus left on a control that has been removed
  from the page sends a screen reader to the top of the document with no announcement.
- The focus ring is `COMPONENTS.md §0.2`'s, unmodified, and is visible against both
  `--fr-surface-raised` (the header) and `--fr-surface-base` (the footer).
- The nav is a list, so a screen reader announces how many items it has before reading them.
- Every control in the shell is at least `--fr-tap-min`.

**What this row deliberately does not add**, so a later session does not read the omissions as
oversights: no search, no notifications, no breadcrumb, no user avatar, no theme switch in the header
(`FR-ADR-073` makes dark mode follow the system and adds no control), no language switch
(`R-OUT-04`), no cinema switch (there is one cinema, `FR-ADR-010`), and **no footer links at all** —
there is no page for them to point at, and inventing an "About" or a "Contact" would be inventing
product content the client will see (`FR-ADR-067`).

---

## S6 — API endpoints

Three endpoints, and no others. **Every product endpoint belongs to another lane.** These three are
operational: two the client wires to infrastructure, one the client reads with a terminal.

**None of the three uses the error envelope.** They are operational endpoints with their own bodies,
read by a load balancer and by a person with `curl`, not by the interface. Their `errors` arrays are
empty for that reason, and the reason is stated here rather than left as an omission.

The four codes this lane's specifications require and the registry does not carry are declared
first, as `FR-ADR-052` requires. **None of them is raised by an `EP-XCT` endpoint** — they are floors
this lane specifies for endpoints other lanes own, which is why their `raised_by` names a router
rather than an endpoint id, and the merge pass is what reconciles that. **The fourth is raised by no
route at all**, which is the whole of its point.

```newerrorcode
{"code":"FORBIDDEN","http":403,"when":"a request carries a valid session but the caller's role, or a manager's screen assignment, does not permit the router or the resource. Distinct from AUTH_REQUIRED (401), which means no valid session, and from HOLD_NOT_OWNED (403), which is specific to a hold token.","raised_by":["every non-public router"],"why_needed":"P-XCT-05 applies authorisation once on the router as a dependency. Without a code for 'signed in, wrong role', that dependency has nothing to return and each lane will invent one, which is the outcome the registry exists to prevent."}
```

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"a request body, query parameter or header fails server-side validation. The failing fields are carried in details.","raised_by":["every write endpoint in every lane"],"why_needed":"P-XCT-11 requires one envelope from every endpoint. FastAPI's default validation response is a different shape, so without a registered code the contract breaks on the most common error a form produces. IDEMPOTENCY_KEY_REUSED and SEAT_LIMIT_EXCEEDED are two specific 422s already in the registry; this is the general case they are specialisations of."}
```

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"an addressed route or resource does not exist, and disclosing its absence is not itself a leak. A private resource belonging to another user returns FORBIDDEN instead, so the two cases stay separable. A path that exists for some other method returns METHOD_NOT_ALLOWED (405) instead, so 'no such address' and 'not that verb' stay separable too.","raised_by":["every lane's read endpoints"],"why_needed":"P-XCT-11 makes the envelope universal. Without a 404 code the interface cannot distinguish 'no such showtime' from a server fault, and a 500 for a mistyped URL pollutes the error rate the operator watches."}
```

```newerrorcode
{"code":"METHOD_NOT_ALLOWED","http":405,"when":"a request uses an HTTP method that is mounted on no route at that path, while the path itself is mounted for at least one other method. There are exactly two such cases in this product. FIRST: a DELETE addressed at one of the never-deleted entities - movie, showtime, screen, cinema and the four lookup vocabularies - for which no DELETE route is mounted because withdrawal replaces deletion (P-ADM-20, FR-ADR-012). It does NOT cover seats or manager screen assignments, which are genuinely deleted and have real mounted DELETE routes: EP-ADM-21 succeeds while its hall has no showtime rows. SECOND: any non-GET method addressed at a path on the read-only reports router, every route of which is a GET (P-RPT-09). A POST to /api/reports/dashboard is 405 and not 404, because that path exists and serves GET. It is raised by a global exception handler rather than by any route in both cases, so it can carry no information about which entity or router was addressed.","raised_by":["a global handler, mounted on the application rather than on any router or endpoint. No endpoint block names this code, and none may until the merge owner adds it to the generator registry"],"why_needed":"FR-ADR-052 requires one envelope from every response, and the framework's own method-not-allowed body is a different shape, so without this code a DELETE to a never-deleted entity, or a POST to the reports router, returns a body the interface cannot parse. Mounting a DELETE route that always refuses was rejected on the distinction that makes the scoping principled: a route that refuses a real request with a real reason has a case where it succeeds, and a route mounted only to say no does not - which is why EP-ADM-21 is allowed to exist and a movie delete route is not. 404 was also rejected in both cases, because it would deny that the address exists when the same address serves GET and PATCH, and that misreports the situation to the only audience that ever sees it. The reports case is named explicitly because P-XCT-05's worked example published 404 for it while P-RPT-09 published 405, and the negative test for the read-only router is transcribed from one of the two."}
```

---

`/health/live` answers exactly one question: is this process running and able to serve HTTP. It
touches nothing — no database query, no Redis command, no disk, no network — because a liveness check
that touches a dependency turns every dependency outage into a restart loop. **It is the endpoint a
container-level restart check points at, and it is never the load balancer's target group check.**

```endpoint
{
  "id": "EP-XCT-01",
  "method": "GET",
  "path": "/health/live",
  "summary": "Report that this process is running and able to serve HTTP",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The process is running. Returned unconditionally while the process can serve HTTP, and it touches no dependency of any kind.", "body": {"status": "string, always the literal 'live'"}}
  },
  "errors": [],
  "idempotency": "safe method — no state change",
  "rate_limit": "none — the container runtime polls this continuously and limiting it would manufacture a false unhealthy signal",
  "authorisation_rule": "No dependency is applied. This route sits on the public router and is reachable without a session, because a health check that needs a credential cannot be used by the thing that needs it.",
  "satisfies": ["P-XCT-10"],
  "brd": ["R-QLY-03", "R-CON-07"]
}
```

---

`/health/ready` answers whether this instance can serve real traffic. It checks PostgreSQL with
`SELECT 1` and Redis with `PING`, both on a short timeout, and returns 503 naming the one that
failed. It deliberately does not probe SQS, SES or S3: the API serves almost every request without
them, and probing them would take the site out of service for a failure it can absorb. **This is the
endpoint the load balancer's target group health check points at.** Its result is cached for a few
seconds so continuous polling does not run a query per poll per instance.

```endpoint
{
  "id": "EP-XCT-02",
  "method": "GET",
  "path": "/health/ready",
  "summary": "Report whether PostgreSQL and Redis are reachable from this instance",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "Both PostgreSQL and Redis responded inside the configured timeout.", "body": {"status": "string, the literal 'ready'", "checks": "object, {postgres: 'ok', redis: 'ok'}", "payment_provider": "string, the configured PAYMENT_PROVIDER value, disclosed deliberately so an operator can tell whether payments are real without going through checkout"}},
    "503": {"description": "PostgreSQL or Redis is unreachable. The body names which one, which is operational information and not sensitive. The instance is expected to be removed from the load balancer, and with one instance that takes browsing down as well — the consequence is recorded rather than softened.", "body": {"status": "string, the literal 'not_ready'", "checks": "object, {postgres: 'ok'|'unreachable', redis: 'ok'|'unreachable'}", "payment_provider": "string, as above"}}
  },
  "errors": [],
  "idempotency": "safe method — no state change",
  "rate_limit": "none — polled continuously by the load balancer. The result is cached for READINESS_CACHE_TTL_SECONDS instead, which bounds the cost without manufacturing a false unhealthy signal",
  "authorisation_rule": "No dependency is applied. Public and unauthenticated, and it returns no version, no hostname and no connection string. PAYMENT_PROVIDER is the one deliberate disclosure.",
  "satisfies": ["P-XCT-10", "P-XCT-09"],
  "brd": ["R-QLY-03", "R-CON-07"]
}
```

---

`/metrics` exposes request counts, latency, seat lock counts and queue depth in Prometheus text
format, plus four counters this product's own failures need. It is built because `SRC-002 §7.7`
requires it and because it is a learning deliverable. **Nothing in the approved stack scrapes it.**
Managed Grafana and OpenSearch are forbidden, no Prometheus server is on the approved list, and
adding one needs the client's permission first. Nothing stores its history and nothing alerts on it.
What it is good for today is an operator with a terminal reading the numbers during an incident.
**It is not routed through the load balancer**, and restricting that is Zone C.

```endpoint
{
  "id": "EP-XCT-03",
  "method": "GET",
  "path": "/metrics",
  "summary": "Expose request counts, latency, seat lock counts and queue depth in Prometheus format",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "Prometheus text exposition format, content type text/plain; version=0.0.4. Carries http_requests_total, http_request_duration_seconds, seat_locks_held, queue_depth, seat_conflicts_total, booking_confirmations_total, receipt_dispatch_total and outbox_pending. The worker serves the same path on its own small HTTP listener, carrying the worker-side counters, because those are the ones that matter most for the failure this product is most exposed to.", "body": {"_": "text/plain, not JSON"}}
  },
  "errors": [],
  "idempotency": "safe method — no state change",
  "rate_limit": "none — it is not reachable through the load balancer. queue_depth is cached for the scrape interval so a read does not become an AWS API call each time, and seat_locks_held comes from an O(1) Redis counter rather than a scan",
  "authorisation_rule": "No dependency is applied and no authentication exists in front of it. Access is controlled by not routing it: no load balancer listener rule may match /metrics. That restriction is Zone C, and the specification in docs/30 Deployment/ must say what is disclosed if a rule does match — traffic volumes and internal route names.",
  "satisfies": ["P-XCT-13"],
  "brd": ["R-CON-04", "R-CON-02"]
}
```

---

## S7 — Cross-cutting floors

The reference material behind `## S4`. A developer reads this once and consults it afterwards. **It
does not restate the P-rows and it does not contradict them** — where a P-row states the rule, this
section states the mechanism, the wrong implementation, and the numbers.

---

### S7.1 — Concurrency: two layers, and why the second may not be waived

**The guarantee is enforced twice, in two different systems, and neither alone satisfies it.**

**Redis provides the hold.** One key per seat per showtime, `lock:seat:{showtime_id}:{seat_id}`.
Acquisition is `SET key <token> NX PX <ttl_ms>` — **one command**. The TTL is set in the same command
as the acquisition, never as a second call: a process that crashes between `SETNX` and `EXPIRE` leaves
a lock with no expiry, and the seat becomes unbuyable forever with no error anywhere and no test that
catches it. The token is a per-hold random value from a cryptographically secure source, one token
shared across every seat in the hold. Release is a Lua script that compares the token and deletes
atomically:

```
if redis.call("GET", KEYS[1]) == ARGV[1] then return redis.call("DEL", KEYS[1]) else return 0 end
```

`GET` then `DEL` as two calls has exactly the race the token exists to prevent: A's lock expires, B
acquires the seat, then A's abandoned tab fires its release and frees B's seat while B is paying.

**PostgreSQL provides the truth.** A **unique constraint on `(showtime_id, seat_id)`** on the
seat-occupancy table. It is **total** — no `WHERE status <> 'cancelled'` clause — because a partial
index would make the guard conditional to accommodate a state that cannot occur in v1. **If
cancellation is ever added, this constraint must be revisited before it.**

**`SELECT ... FOR UPDATE` is not the guard, and is used only where it helps.** It locks the showtime
row to serialise the cut-off check and the price read against a concurrent admin edit. It is **not**
used to check whether a seat is free, because that check has nothing to lock: a row-level lock on rows
that do not exist locks nothing, so two transactions both find no row, both proceed, and both insert.
**The unique constraint is the only thing that catches that.**

**Isolation is `READ COMMITTED`**, PostgreSQL's default. The correctness guarantee holds at every
isolation level. `SERIALIZABLE` would add serialisation failures and retries to every booking to
prevent an anomaly the constraint already prevents.

**Why the database half may not be waived.** Redis is a cache and a lock service. Losing it, or having
it be wrong, must degrade the product and must never corrupt it. A Redis restart, an eviction under
memory pressure, a clock difference, or a bug in the release path each produce two holders, and with
no database guard there is then nothing to stop two bookings. **Waiving a quality check is reserved to
the client, and this is the check.** No `ON CONFLICT DO NOTHING` exists anywhere near the
seat-occupancy table: it would turn the guard into silence, committing a booking with fewer seats than
the customer paid for and no error anywhere.

**A unique violation is not an error.** It is the guard working. It is caught, translated into a 409
naming the seats that were taken, **not retried** — retrying a lost race loses it again, slower — and
logged as an expected outcome with a counter, because the rate at which it fires is the signal that
tells the operator the lock layer has a problem.

**The red-proof drill runs in two stages, and only the second one reaches the constraint.**

**Why there are two, stated first because a single-stage drill was specified here and could not
work.** The fifty-request gate fires at the **hold** endpoint (`SRC-002 §9.1`, `P-HLD-13`,
`P-PAY-11`), where every loser is refused by Redis at `SET … NX` and **the unique constraint is never
reached**. Dropping the constraint and re-running that gate therefore still yields exactly one winner
— and the previous version of this procedure classified that outcome as a void proof and a
stop-the-line finding, which made **the never-waivable gate report failure against a correct
implementation**. The gate is unchanged; a second stage is added that puts two live holders on one
seat, which is the only state from which two confirms both reach `P-PAY-10` step 7. **That is
stricter, not weaker** — the constraint was being exercised zero times and is now exercised, watched
failing, and watched working again.

**Stage A — the fifty-request gate.** Unchanged, and `P-HLD-13` owns it.

1. Run `scripts/stress_seats.py`. Observe **exactly one 201 and forty-nine 409 `SEAT_UNAVAILABLE`**,
   the start-instant spread inside `STRESS_CONCURRENCY_SPREAD_MS`, and — after the winner confirms —
   exactly one `booking_seat` row for the pair, read directly from PostgreSQL.
2. **Record that the constraint fired zero times.** Stage A proves the lock layer and the end-to-end
   result. It proves nothing about the constraint, and saying so is what stops Stage B being skipped.

**Stage B — the red proof, run by hand, in the local environment only**, with a recorded outcome and a
recorded date:

3. Customer A takes a hold on seat `S`, then issues a confirm. Step 6 of `P-PAY-10` spends
   `PAYMENT_SIMULATED_DELAY_MS`, which is the window the rest of this stage runs inside.
4. **Inside that window, delete `lock:seat:{showtime_id}:{seat_id}` directly in Redis.** That is an
   eviction, injected by hand — the exact failure the paragraph above names as the reason the database
   half exists.
5. Customer B takes a hold on the same seat `S`. `SET … NX` succeeds because the key is gone, and
   `P-HLD-01` step 7 finds no committed `booking_seat` row because A has not committed. **Two
   customers now hold one seat**, each with a token their own confirm will re-validate successfully.
6. B issues a confirm. Both transactions reach step 7. **With the constraint present: one 201, one
   409 `SEAT_UNAVAILABLE`, and one `booking_seat` row.** That 409 is the constraint firing, observed
   at the layer that owns it.
7. **Drop the unique constraint on `(showtime_id, seat_id)` and repeat steps 3 to 6. Observe two 201s
   and two `booking_seat` rows for one `(showtime_id, seat_id)` — the seat sold twice.** If it still
   produces one row, the run is not exercising the constraint and the whole proof is void. **That
   outcome is a stop-the-line finding, not a pleasant surprise.**
8. Restore the constraint.
9. **Verify the restore** by repeating steps 3 to 6 and observing one row, and by reading the
   constraint back from `pg_constraint`.

**Nothing is disabled at any point in Stage B**, and that matters because disabling a control to make
a test pass is a fake green and waiving a quality check is reserved to the client. Both holds go
through the real lock acquisition, both confirms re-validate their token, and the rate limiter runs
throughout. **A key is made to disappear, which is a fault the system is supposed to survive** — the
same kind of deliberate act as dropping the constraint, and permitted on the same terms.

The drill is local only because dropping a correctness constraint in the deployed environment is a
destructive schema change, because Stage B needs direct Redis command access, and because the build
session has no write access to AWS at all. **The stress script itself runs against both**, by changing
a base URL, exactly as `SRC-002 §9.1` requires. Running it against the deployed environment writes
real bookings there, and the Zone C specification must say so and say which showtime to point it at.

**The script proves its own concurrency before its result is trusted.** It records the start instant
of each of the fifty requests and asserts the spread between first and last is under a configured
threshold, defaulting to 100 ms. **If the spread is too wide it fails with "not concurrent", not with
"passed".** Fifty requests from one Python process using a single event loop, one connection pool, or
a blocking client in a thread pool can serialise enough that the race never happens — and the test
then passes against genuinely broken code. **A proof that cannot distinguish a passing system from a
serialised client is not a proof.**

It runs as **fifty distinct authenticated customers**, seeded for the purpose. Holding requires an
account, and fifty requests from one account would be caught by the per-user rate limiter and would
measure the limiter rather than the lock. **The rate limiter is not disabled for the run** — fifty
distinct users stay inside the per-user buckets, and the per-IP bucket is configured to permit the
test's source. Disabling a control to make a test pass is the shape of a fake green.

**The fifty sessions are obtained in an untimed warm-up phase that the measured window does not
overlap**, which is what keeps the login limiter out of the result. `P-XCT-07` owns that mechanism,
its arithmetic and what the script prints; this section does not restate it.

Assertions, at both layers: exactly **one** 201 and **forty-nine** 409s — not "at most one", because
zero winners is also a failure — and exactly **one row** in the seat-occupancy table for that
`(showtime_id, seat_id)`, **read directly from PostgreSQL**. The HTTP assertion alone is not
sufficient: a bug that returns 200 to one caller while writing two rows is precisely the failure being
hunted.

**This gate is never waived, never skipped, and never marked expected-to-fail.** A red concurrency
gate blocks the story it belongs to; the story is marked `Blocked` with a note and surfaced.

---

### S7.2 — Money: integer paise, one function, one one-way door

**Currency is INR. The minor unit is paise. The ratio is 100.**

- **`Decimal` at the boundary only.** A value arriving as text or JSON is parsed to `Decimal`,
  validated, and converted to an integer number of paise before it goes any further. **There is no
  `Decimal` on the money path beyond that boundary**, because a `Decimal` carries a rounding mode set
  somewhere else — a context, a constructor argument, or a default — which is one more place two
  screens can disagree. Integer arithmetic has no mode to set.
- **`bigint` in persistence.** Every money column is an integer count of paise. `bigint` rather than
  `integer` because nothing is deleted and revenue totals accumulate; a 2.1-billion-paise ceiling is
  ₹21,474,836, which is reachable and exists for no reason.
- **A formatted string at render time only.** Formatting happens in the presentation layer and
  nowhere else. **A formatted money value never travels through an API response as the value of
  record.**
- **No float, anywhere, at any layer.** Floats cannot hold 0.10 and summing them drifts. A float on
  the money path is a defect regardless of whether a test caught it.
- **The naming convention is part of the rule.** A field named `price` holding `250.00` is a defect;
  the field is `price_paise` and holds `25000`. A suffix on every money identifier is the cheapest
  way to make a unit error visible in a code review.

**One function computes a seat price, and every caller uses it** — the seat map, the checkout total,
the receipt, the dashboard revenue and the seed script. It is a pure function of two integers with a
table-driven test. **Two implementations of the formula is the failure mode, not the formula being
wrong.**

**The rounding rule is `FR-ADR-038` and lane E3 carries its worked examples.** It is not restated
here. **The invariant a reviewer checks is this:** rounding is applied per seat, the booking total is
the sum of already-rounded per-seat prices, and **the total is never rounded**. If the per-seat prices
shown on the seat map do not sum exactly to the total shown beside them, a second implementation
exists somewhere.

**The ratio is a one-way door.** Bookings are permanent, so reinterpreting the minor unit later
silently rewrites what every past customer paid, and no migration fixes it because no row records
which interpretation it was written under. It is therefore a **named configuration value**,
`CURRENCY_MINOR_UNIT_RATIO`, validated at boot and logged once. **`100` never appears as a literal on
the money path** — not in a conversion, not in a test fixture, not in a seed script. Being a variable
does not make it changeable; it is a named value so that it is visible and checkable.

**No per-row currency column.** One currency exists, and a constant repeated on every row invites a
mixed-currency sum nobody validates. A second currency would be a schema change, and it should be one.

**Two consequences worth naming.** `SUM()` over a `bigint` column returns `numeric` in PostgreSQL,
which arrives in Python as `Decimal` and mixes badly with `int` — cast back to `BigInteger` in the
query, which is directly relevant to the dashboard's revenue totals. And **no tax is shown
separately**, so the stored total is a single figure that cannot be split later. That is an accepted,
recorded consequence of a client ruling, not an oversight.

---

### S7.3 — Audit: same transaction, append-only, before and after

**One `audit_log` table. Every privileged write inserts one row into it in the same database
transaction as the change itself.** Either both land or neither does. **An audit written after the
commit is missing exactly the rows that crashed**, which are the ones worth having.

| Column | Holds |
|---|---|
| `id` | `bigint` identity |
| `occurred_at` | `timestamptz`, UTC |
| `actor_user_id` | non-null foreign key to the acting user. Never a role name, never a service account |
| `actor_role` | the role the actor held **at the time**, copied rather than joined, because a role can change |
| `action` | a **closed** controlled vocabulary string, published by the administration section (`FR-ADR-019`) — `movie.created`, `showtime.base_price_changed`, and so on. **No section coins one of its own** |
| `entity_type` | the table the change landed on |
| `entity_id` | the primary key of the changed row |
| `before` | `jsonb`, the changed fields' prior values. Null for a creation |
| `after` | `jsonb`, the changed fields' new values. Null for a withdrawal that changes nothing else |
| `request_id` | the request id from the log context, so an audit row joins to the log lines |

**`before` and `after` carry only the fields that changed**, not the whole row. A full-row snapshot on
every edit makes this the largest object in the database and buries the one field that moved.

**Append-only, enforced at the database-role level, not merely intended.** The application role holds
`INSERT` and `SELECT` on this table and no `UPDATE` and no `DELETE`. **An audit log the application
can rewrite is not evidence.**

**Not a trigger.** A database trigger cannot know the acting user or the request id — it sees a
connection — and both are the point.

**Writes only. Reads are not audited.** A manager opening a dashboard writes no row. Auditing reads
would produce a table dominated by dashboard page loads.

**What counts as a privileged write:** every admin action. Creating or editing a movie, publishing
one, changing a display window, creating a showtime, setting a base price, changing a category uplift,
configuring a screen or its seats, creating or assigning a manager. **A customer booking a seat is not
a privileged write** — it is the product working.

**How `R-QLY-08` is answered for any seat, at any time, and it is not the audit log.** The booking
record answers it, because the booking record is permanent:

```
(showtime_id, seat_id)
  → seat-occupancy row        at most one, guaranteed by the unique constraint
  → booking_id                → user_id, created_at
  → price_paise               snapshotted at hold acquisition, never recomputed
```

Three properties make that query total rather than usually-correct. **Nothing is ever deleted** — no
pruning job, no retention window, and no `ON DELETE CASCADE` on any path that can reach a booking; the
default is `ON DELETE RESTRICT`, because a cascade is a delete that happens without anyone writing the
word delete. **The booking's `user_id` is non-null**, so an orphaned booking cannot exist.
**The price is snapshotted**, so a later admin price edit cannot rewrite what a past customer paid.

The seat has no row: the seat was never sold. That is a valid answer, not a failure, and it is
distinguishable from an error.

**`audit_log` will be the largest table in the system and it never shrinks.** That is the intended
cost of forever retention and it belongs in the runbook as a figure to watch. **The `action`
vocabulary is a controlled list the PRD enumerates** — a free-text action column becomes unqueryable
within a month, which defeats the Phase 8 screen that reads it.

---

### S7.4 — Rate limiting: a token bucket in Redis, on the real client address, failing closed

**A token bucket in Redis, evaluated by a Lua script**, so the read, the refill and the decrement are
one atomic operation. A read-then-write in two round trips is a limiter that leaks under exactly the
concurrency it exists to control.

**Two independent buckets per limited request. Both must have a token.** Per user, on authenticated
endpoints, keyed on the user id. Per IP, always, keyed on the real client address.

**The real client address, and this is where it goes wrong silently.** Behind a load balancer the peer
address is the load balancer, so a limiter keyed on the peer puts every customer in one bucket — it
appears to work while protecting nothing. The address is therefore taken from `X-Forwarded-For`,
**counting from the right and skipping exactly one trusted proxy**, with the application configured to
trust exactly one: uvicorn runs with `--proxy-headers` and an explicit `--forwarded-allow-ips` naming
the load balancer's subnet range, **never a wildcard**, because a wildcard trusts any peer's header
and that is the same as trusting the client. **The leftmost entry is the one a client can forge by
sending its own header, and it is never used.**

**This needs its own test, because getting it wrong is silent:** assert that two requests carrying
different forged `X-Forwarded-For` values from the same peer are counted in the **same** bucket.

**In Redis and not in process, and only if every process actually uses it.** A limiter storing state
in-process multiplies its own limit: with two workers across N tasks, "5 attempts per 15 minutes" is
really 5 × 2 × N.

**Bucket values. Every one of these is an estimate, not a measurement.** They are named configuration,
and Phase 7's load test replaces them with observed numbers.

| Endpoint | Per user | Per IP | Per booking |
|---|---|---|---|
| seat hold | 20 / minute | 60 / minute | — |
| booking confirm | 10 / minute | 30 / minute | — |
| login | 10 / 15 minutes | 30 / 15 minutes | — |
| registration | — | 5 / hour | — |
| password reset request | — | 5 / hour | — |
| password reset **confirm** | — | 10 / hour | — |
| booking lookup by reference | 20 / minute | 60 / minute | — |
| seat map read | — | 120 / minute | — |
| reports and change log | 60 / minute | — | — |
| receipt resend | 20 / minute *(it is a booking lookup too)* | 60 / minute | **1 per `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` = 300 s** |

**The last two rows are build-session extensions, added under `CONSTITUTION.md` Art III.9, and each
names the record it satisfies.**

**Receipt resend, keyed per booking.** `FR-ADR-048` requires the resend to be "rate-limited per
booking". `FR-ADR-058` enumerates the limited endpoints and **has no row for it** — not a
disagreement, simply a record that predates the surface. Both are `APPROVED`, so the row is added
here rather than either record being read as forbidding it. **The key is the booking, not only the
user**, because the thing being prevented is one booking's receipt being re-sent over and over: a
per-user bucket of twenty a minute permits nineteen copies of the same receipt to the same inbox and
satisfies nothing `FR-ADR-048` asked for. The per-user and per-IP figures on that row are the
booking-lookup buckets it already sits behind, not a second control. **Starting value 300 seconds. It
is an estimate, not a measurement**, exactly like every other number in this table, and the wait the
customer is shown is computed from it rather than written into the copy.

**The password-reset confirm gets its own bucket, and the reason it exists at all is security rather
than courtesy.** `EP-ACC-06` already declared itself limited while carrying no `429`, no
`RATE_LIMITED` and no row in any bucket table — and `P-ACC-08`'s `503` on Redis loss only makes sense
if a limiter runs. **The limiter is not what makes this token unguessable, and the row says so rather than claiming otherwise.** `P-ACC-07` step 4 draws **32 bytes from a cryptographically secure source**, so the guess space is 2^256; at 1000 requests a second an attacker makes roughly 1.8 x 10^6 guesses inside the token's thirty-minute life, which is indistinguishable from zero with or without a bucket. **What the limiter buys is that the entropy argument rests entirely on one line continuing to draw 32 bytes from a secure source.** Shortening the token, narrowing the alphabet, or swapping `secrets` for `random` is a one-line change that **no case in `08 SIT` or `09 NegativeTesting` would catch**, because every functional test still passes against a weak token. This bucket is the only control that survives that change, which is exactly why it may not be dropped as an optimisation — and it is **explicitly a control that is not paying for itself today.** *(An earlier revision of this row asserted the token was "brute-forceable at line rate". That was false and is recorded here rather than quietly removed: it is arithmetic nobody ran, it breaches Art VII.1, and it is self-defeating — the first engineer to check it concludes the limiter is unnecessary. `E5_account.md`'s lane was handed the same wording and refused to write it; this is that lane's reasoning.)* **It does not share the request bucket**: a customer
who requests a reset and then confirms it would spend two of five hourly tokens on one legitimate
recovery, and a couple of mistyped attempts would lock them out of **the only route back into an
account whose address is permanently taken**.

**Ten, and the number is sized to the thing it protects rather than to a round figure.** At most five
reset *links* can exist per hour — `RATE_LIMIT_RESET_IP_PER_HOUR` is 5 — so ten confirms is about
**two attempts per obtainable link**. *(Not "enough to keep the guessing rate low": the paragraph
above says why that framing is the wrong one, and a bucket sized against a `2^256` space would be
arbitrary at any value.)*

**Every request spends a token, including one rejected for a malformed token.** Otherwise an attacker
gets unmetered attempts simply by sending deliberately malformed values, and **the 43-character length
check — which exists to save a database read — becomes the thing that defeats the limiter.** The
length check still runs before any query, so a malformed guess costs a token and no read.

**Starting value, an estimate not a measurement**, like every other row here.

**Reports and the change log, per user only.** The reporting endpoints did not exist when
`FR-ADR-058` was written either. `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`, starting value 60. **No
per-IP bucket on that row**: every caller there is authenticated and there are at most thirteen of
them, and a per-IP bucket would put twelve managers sharing one building's address into one bucket —
which is precisely the failure `FR-ADR-058` exists to avoid. **Estimate, not measurement.**

**Login, registration and password reset are limited even though the mandate names only seat selection
and booking.** Extending a control is stricter and needs no signature. An unlimited login endpoint is a
guessing oracle, and an unlimited registration endpoint fills a table that is never pruned. **The seat
map read is limited per IP only, generously**, because it is unauthenticated and polled every three
seconds by every viewer — the limit exists to stop scraping, not to stop browsing, and 120 a minute is
far above what a legitimate poller uses. **That row has a consequence beyond scraping, and it is
stated in `P-XCT-09`:** because the seat-map read is limited and the limiter runs before the cache, a
Redis outage returns 503 there rather than falling through to PostgreSQL. The movie and showtime
lists carry no row in this table and do fall through.

**On Redis being unreachable the limiter fails closed: 503, not unlimited access.** A limiter that
fails open removes a control at exactly the moment the system is least healthy. This is the stricter
option and it needs no signature.

**A retry carrying an already-seen `Idempotency-Key` still consumes a token.** It is a real request
arriving at the server, and an exemption keyed on a client-supplied header is an unlimited path for
anyone who sends one. The bucket sizes are set so a legitimate double-click and one or two retries fit
comfortably inside them: ten confirms a minute against a three-minute hold is not a constraint a real
customer meets.

**429 carries `Retry-After` in seconds, computed from that bucket's refill rate rather than a
constant**, and the `RATE_LIMITED` code. **The per-booking row has no refill rate**, because it is a
minimum interval rather than a bucket, so its `Retry-After` is the interval less the time already
elapsed — computed the same way, from the same kind of stored instant, and never a constant either.

```
capacity 20 / 60 s   → refill 0.3333 tokens/s → one token in 3.0 s  → Retry-After: 3
capacity 30 / 900 s  → refill 0.0333 tokens/s → one token in 30 s   → Retry-After: 30

receipt resend, per booking — an interval, not a bucket:
  last accepted send 18:00:00, retry at 18:01:00, interval 300 s
  300 − 60 = 240                                                    → Retry-After: 240
  the customer is shown "in 4 minutes", computed from 240 rather than typed into the string
```

**The header carries the integer; the sentence beside it is rendered by S7.20** — below 120 seconds
as a second count, at 120 and above as whole minutes rounded up. That is why 240 reads "4 minutes"
while 30 reads "30 seconds", and it is one rule rather than a choice made per surface.

**The load balancer's subnet range is a Zone C value the application needs.** `--forwarded-allow-ips`
cannot be set correctly without it, so it goes in the prep queue with a needed-by phase of Phase 1,
announced now rather than on the day it blocks.

---

### S7.5 — Sessions and authorisation

**Authentication is our own email and password with a JWT. Never Cognito.**

- **Email is the identity**, unique case-insensitively, stored as entered and constrained on
  `lower(email)` by a unique index. A second lowercased column would be two fields to keep in step.
- **Password: a length floor, not a composition rule.** Minimum 12 characters, no mandatory mixture of
  character classes. Length resists guessing; composition rules push people toward predictable
  substitutions and toward writing passwords down. **The maximum is 72 bytes, enforced explicitly and
  with its own message, because bcrypt silently truncates at 72 bytes** — a truncation nobody sees
  means two different long passwords authenticate the same account.
- **Hashed with bcrypt, off the event loop.** Roughly 300 ms of pure CPU inside an `async def` stalls
  every other request on that worker, and on a shared 1 GB host a handful of simultaneous logins is a
  visible outage. It runs in a thread, which makes the thread pool size a tuning parameter inside the
  API's memory budget.
- **The comparison runs even when the email is unknown**, against a dummy hash, so response timing
  does not disclose whether an account exists. The password reset response is identical whether or not
  the address is registered, for the same reason.
- **A password reset flow exists**, by emailed single-use token with a short expiry. Without one, a
  customer who forgets their password loses access to every booking they have made, and the account
  cannot be deleted and re-created because the email is taken forever.

**The JWT lives in an `HttpOnly`, `SameSite=Lax` cookie**, never in `localStorage`, so a script on the
page cannot read it. **`COOKIE_SECURE` is environment-driven, has no default, and is off in the
deployed environment.** `OPEN-TLS-01` is deferred; **this document does not decide it and states
nothing about whether TLS is or will be terminated anywhere.** Setting `Secure` without TLS is not the
stricter option — it is broken, because the browser would never send the cookie over HTTP and nobody
could stay signed in.

**`SameSite=Lax` is not only a usability choice; it is the product's only cross-site request
defence, and `P-XCT-06` names it as one.** There is no CSRF token, no double-submit cookie and no
`Origin` check in this specification. `Lax` withholds the cookie from every cross-site request except
a top-level navigation using a safe method, which covers every state-changing endpoint here because
every one of them is a `POST`, `PUT`, `PATCH` or `DELETE`. **Two changes remove it in one line each —
an endpoint that writes on a `GET`, and relaxing the attribute to `None`** — and `P-XCT-06` carries
both, so neither can be made without meeting the sentence that says what it costs.

**Authorisation is applied once, on the router, as a dependency. Never per handler.** A check repeated
in fifty places is a check that eventually misses one. Four routers exist — public, customer, manager,
admin — and a handler contains no role check. **The role is read from the database on every request,
never from a claim in the token**, so a role change takes effect on the next request.

**The four-role matrix — `PROVISIONAL`.**

> ⚠ This is a build-session reading that reconciles two of the client's own answers (`SRC-003 C-1`).
> `OPEN-ROLE-01` says "do not make more personas"; the very next answer describes two managers per
> hall with a dashboard. **One message from the client reverses it.** The rejected reading was three
> roles with the manager dashboard served to admins filtered by hall — which discards "2 managers per
> cinema hall" and puts twelve people on one shared admin account, so every audit row would name the
> same actor.

| Role | Account | May reach | May write |
|---|---|---|---|
| **guest** | none | the public router: movies, showtimes, the seat map | nothing. **Cannot hold and cannot book** |
| **customer** | required | public + customer: hold, pay, their own bookings and receipts | their own bookings only |
| **manager** | required | public + customer + manager: the dashboard for their assigned screens | **nothing. Read only** |
| **admin** | required | every router, including everything a manager can do | everything |

**Every privileged write belongs to the admin alone. A manager endpoint that writes anything is a
defect, not a feature.** There is no small, safe write. **There is no cinema-staff role and no door
scanner** — entry is a person reading the booking reference from the emailed receipt.

**Manager scope is an assignment table on `(manager, screen)`.** "Two per hall" is an observation
about the client's current staffing, not a constraint: the business can employ one or three without
anything being rebuilt. A manager with no hall assigned yet sees an empty dashboard, which is the
correct state for a new account and not an error. **The scope is applied in the query's `WHERE`
clause by the router dependency, not by filtering results after they are fetched.**

**The test shape is fixed and it is the thing that is usually got wrong:** assert a **non-empty**
result for the manager's own screens and a denied result for another's. A test asserting only "denied"
passes against a query that returns nothing for anybody.

**Two accepted weaknesses, recorded rather than solved.** There is **no email-verification gate in
v1** — it inserts a second interruption into the flow the two-minute target protects, it makes
registration depend on SES being healthy, and it does not catch the most common bad address, which is
a valid deliverable one belonging to someone else. The mitigation is that the address is displayed
back on the confirmation screen and the reference is on screen and in the bookings list regardless.
And **credentials cross the network unprotected in the deployed environment** while `COOKIE_SECURE` is
off, which is why that environment is never called production and carries no real customer data.

---

### S7.6 — Caching: cache-aside, `DEL` not `SET`, and a rebuild lock

**Cache-aside in Redis. Keys and TTLs:**

| Key | TTL | Invalidated by |
|---|---|---|
| `cache:seatmap:{showtime_id}` | `SEATMAP_CACHE_TTL_SECONDS` = 10 s | **a `DEL`** after a booking, a hold or a release commits — the rule stated below, and `P-XCT-08` owns it |
| `cache:seatmap:{showtime_id}:rebuild` | `CACHE_REBUILD_LOCK_TTL_MS` = 2000 ms | nothing. **It is a stampede guard rather than a cached value**, and it is released by the rebuilder or expires on its own |
| the movie list, keyed **per filter combination** | `LISTING_CACHE_TTL_SECONDS` = 60 s | **not a `DEL`** — the listings generation moves after the admin write commits, which makes the previous generation's keys unreachable. **`P-BRW-12` owns the key format, the counter and the list of writes that move it** |
| the showtime list, keyed **per filter combination** | `LISTING_CACHE_TTL_SECONDS` = 60 s | as the row above, and owned by the same row |

**Invalidation is a `DEL` issued after the transaction commits and after the Redis locks are released.
Not a `SET` of the new value.**

- **`DEL` rather than `SET`:** a writer that computes and writes the new map can lose to a slower
  reader that computed an older map first — the read-then-write race. **Deleting cannot write a stale
  value, because it writes nothing.**
- **After commit:** deleting before commit opens a window in which a reader rebuilds from a database
  that does not yet have the booking, and caches that.
- **Not inside the transaction:** Redis does not participate in the rollback, so a rolled-back
  transaction would have already deleted and a committed one would have deleted too early.

**A hold or a release also invalidates**, because a held seat is a distinct state on the map.

**The `DEL` above is stated for the seat map, which is the case where a key can be named.** The two
listing rows in the table are cached **per filter combination**, so their key set is unbounded and no
`DEL` can enumerate it; they are invalidated by moving a generation value that every listings key
embeds, which makes the old entries unreachable and lets them expire on the same TTL. `P-XCT-08`
states why that is the same rule rather than an exemption from it, and **`P-BRW-12` owns the key
format, the counter and the writes that move it.** Neither is restated here.

**If the `DEL` fails, nothing is retried and nothing is rolled back.** The entry expires within its
TTL. That is a **bounded, stated** staleness rather than an unbounded one, and it is why the TTL
exists alongside invalidation: without it, every missed `DEL` — a Redis blip, a crash between commit
and delete — becomes permanent staleness, and a permanently stale seat map sells a seat that is gone.

**Stampede prevention: a per-key rebuild lock.** On a miss, one caller acquires
`cache:seatmap:{id}:rebuild` with `SET NX PX <CACHE_REBUILD_LOCK_TTL_MS>`, default `2000`, and
rebuilds. **The value is the named setting and never a literal**, the same rule every other tuned
number in S7.9 carries. Callers that do not get it wait
briefly and re-read the cache; on a second miss they read PostgreSQL directly rather than queueing.
**Nobody blocks on a lock they cannot get** — under a three-second poll a queue of waiters refills
faster than it drains. This is the specific place the mandate's "document the stampede in code"
requirement applies, and the code carries a comment naming the scenario: **the TTL expires on a
popular Friday showtime and every in-flight poller rebuilds the map at once.**

**The worst-case staleness figure, with the arithmetic that produces it:**

```
cache TTL, the ceiling for a failed DEL ...... 10 s
+ client poll interval ....................... 3 s
= worst case a customer can see .............. 13 s
```

`SRC-001 §3.3` asks for accuracy "within a few seconds", and 13 is at the edge of it. **It is stated
rather than rounded down**, and it is the number to revisit if the client finds the map feels wrong.

**Staleness never causes an oversell.** A customer who clicks a seat the map showed as available loses
at the Redis lock or at the unique constraint and is told. **The cache affects what someone sees,
never what they get.**

**The map is cached objectively, not per user.** Caching per viewer with their own held seats included
would multiply the cache by the number of viewers and destroy the hit rate. The cached map carries
`available`, `sold` and `held`; the caller's own holds are overlaid from their hold token at render.

**A cache outage is a cache miss.** Reads fall through to PostgreSQL and **the movie list and the
showtime list keep working**, slower. That is not the fallback `SRC-002 §7.9` forbids — reading from a
source of truth is not a substitution, it is the source.

**The seat map is the exception, and it is a limiter property rather than a cache one.** A Redis
outage is not only a cache outage: the seat-map read is rate-limited (`FR-ADR-058`,
`RATE_LIMIT_SEATMAP_IP_PER_MIN`) and the limiter runs **before** the cache and **fails closed**, so
that read returns **503 `DEPENDENCY_UNAVAILABLE`** and the fallback described above is never reached.
`FR-ADR-028` and `FR-ADR-058` are both `APPROVED` and both cover this read; 503 is the stricter
option and needs no signature (Art III.10). `P-XCT-09` carries the resolution in full.

---

### S7.7 — Health and readiness, and the consequence stated rather than softened

**`/health/live` touches nothing.** No database query, no Redis command, no disk, no network. It
returns 200 with a fixed body and answers exactly one question: is this process running and able to
serve HTTP. **If it touches a dependency it is not a liveness check.**

**`/health/ready` checks PostgreSQL with `SELECT 1` and Redis with `PING`, both on a short timeout,
and nothing else.** 503 if either is unreachable, with a body naming which one — an operator reading a
503 needs to know which dependency, and it is not sensitive. **A readiness check that hangs fails by
timing out at the caller**, which is slower and less informative than failing fast.

**SQS, SES and S3 are deliberately not probed.** The API serves almost every request without them:
browsing, the seat map, holds and bookings all work, and only the receipt send is affected, which is
the worker's job through a durable queue. Probing them would take the site out of service for a
failure it can absorb, and every probe is an API call on a path the load balancer polls continuously
against free-tier request allowances.

**The readiness result is cached for a few seconds** so polling does not run a query per poll per
instance. A stale-by-seconds answer is correct for a check whose consumer polls on an interval anyway.

**The consequence, stated rather than softened.** With one EC2 instance, **a Redis outage takes the
only instance out of the load balancer, so the site is down even though browsing would have worked.**
That is what `SRC-002 §7.4` requires and what `SRC-002 §1.3` intends — the client wants to see the
failure — and softening readiness to keep a degraded site up would hide the outage the clause exists
to reveal. It is recorded here as a known cost, not discovered later.

**Which endpoint goes where, and it is Zone C:**

> **The load balancer's target group health check points at `/health/ready`.**
> **Any container-level restart check points at `/health/live`.**

**Wiring them the wrong way round turns a recoverable dependency outage into a restart loop.** A
health check that touches the database makes a database blip restart every container: the blip is
recoverable, the restart loop is not. That is one of the two or three common mistakes the Zone C
specification is required to name.

**The readiness cache interval and the health check interval interact**, and the specification must
state both numbers and their required relationship: if the cache is longer than the unhealthy-threshold
window, the load balancer reacts to stale information. *(reasoned, not observed.)*

**Neither endpoint is authenticated and neither returns anything sensitive** — no version, no
hostname, no connection string. `PAYMENT_PROVIDER` is the one deliberate disclosure: an operator must
be able to tell whether the payments are real without going through checkout, and it is not a secret.

**The worker has no HTTP surface and exposes neither endpoint.** Its liveness is the process running,
which ECS observes directly. **That is a real gap:** a worker that is running but wedged — not
polling, not failing — looks healthy. It is recorded rather than solved, and **queue depth is the
signal that would reveal it.**

**The static frontend container serves a static file as its health check.** A static web server that
can serve a file is working.

**Both endpoints are Zone B**, so every line carries a comment saying what breaks without it —
including, on `/health/live`, a comment saying why it deliberately does nothing. **That comment is the
one that stops a future contributor "improving" it by adding a database check.**

**Testing this means stopping PostgreSQL and asserting 503 from readiness and 200 from liveness in the
same moment.** A mocked test proves the handler; only stopping the container proves the timeouts.

---

### S7.8 — Logging and the request id

**JSON, one object per line, to stdout. Never a file on disk.** A file is state on a stateless
container and it dies with the container.

**A fixed field set on every line**, so the logs are queryable rather than merely readable:
`timestamp` (UTC, ISO-8601) · `level` · `logger` · `message` · `request_id` · `service` (`api` or
`worker`) · `instance_id`. And where they apply: `user_id`, `route`, `method`, `status_code`,
`duration_ms`, `showtime_id`, `booking_id`, `error_code`.

**One request-id header: `X-Request-Id`. An inbound value is never trusted.** The load balancer is
internet-facing, so a client can send any header it likes, and a forged or duplicated id makes the
correlation worse than having none. **A fresh id is always generated by us.** If a client sent one it
is recorded as `client_request_id` — a separate field, never the one used for correlation. The
generated id is returned in the response `X-Request-Id` header and is shown to the customer on a 5xx.

**The load balancer's own trace header is recorded as an additional field when present** — it is
genuinely useful for correlating with access logs — but it is never the primary, because it is
absent locally and the local and deployed code paths would then differ.

**Propagation into the worker is explicit, through the message payload.** A context variable cannot
cross a process boundary. The `request_id` of the request that created the booking is written onto the
outbox row, travels in the queue message, and is bound to the worker's logging context for the whole
job. **That is the only way one search finds both halves of a booking.** The worker also logs its own
`job_id`, because one request can produce several deliveries under at-least-once.

**Levels.** `INFO` by default in every environment, from `LOG_LEVEL`. `DEBUG` exists and is the
default nowhere, because CloudWatch holds 5 GB on the free tier — and because debug logging of request
bodies is how card-shaped data would arrive in a log if the system ever had any.

**What is logged at which level, because this is where volume comes from:**

- One `INFO` line per **completed request**, with route, status and duration. Not one per log
  statement inside it.
- **`/health/live` and `/health/ready` are not logged at `INFO`.** They are polled continuously and
  would dominate the volume. Failures are logged. The consequence is that the logs do not prove the
  load balancer is polling; that is what the load balancer's own metrics are for.
- A `SEAT_UNAVAILABLE` outcome is `INFO` with a counter, **not `WARNING`**. It is the guard working,
  and logging correct behaviour as a warning trains the operator to ignore warnings.
- Unhandled exceptions are `ERROR` with a stack trace. **The trace goes in the log and never in the
  response.**

**Never logged, at any level:** no card data ever — there is none in the system, and the rule stays
stated so nobody adds a card-shaped log field out of habit; no password, no password hash, no JWT, no
session cookie, no `Authorization` header; **no booking reference in a line that also carries the
customer's email**, because together they are enough to walk into a hall; no resolved secret values;
no full request bodies.

**Redaction is a filter on the logging pipeline, not a discipline at each call site.** A denylist of
field names is applied centrally, so forgetting at one call site does not leak.

**The single most important consequence, and it is Zone C.** **Container stdout dies with the
container unless a log driver is configured.** With the default driver, the record of a crash loop is
destroyed by the restart that caused it. Configuring the `awslogs` driver is the client's work, it
needs a prep-queue row with a needed-by phase of **Phase 1**, and **without it this entire section
delivers nothing.** Log retention is also a Zone C setting whose default is never-expire, which will
consume the 5 GB allowance eventually; the specification should recommend a finite retention and say
what is lost.

**The request id joins the audit row, the outbox row, the queue message and the customer's error
screen.** One search across a log group answers "what happened to this booking" end to end.

---

### S7.9 — Configuration: every setting from the environment, validated at boot

**Every setting comes from an environment variable. There are no configuration files and no hardcoded
environment names.** Validation runs at import time, before the application accepts a request, and a
failure **exits non-zero with a message naming the variable.** Not a warning, not a log line, not a
lazy failure on first use. **A container that starts and then fails on its first booking is worse than
one that never starts, because the container runtime reports it healthy.**

The validation layer is Pydantic's settings module, which the web framework already depends on. It is
not a new dependency; it is the validation layer of a library already in the stack.

**There is no `ENVIRONMENT=production|development` switch.** It would concentrate every behavioural
difference into one string, and the failure is silent when the string is wrong. **Each behaviour gets
its own variable** — `COOKIE_SECURE`, `PAYMENT_PROVIDER`, `MAIL_PROVIDER`, `LOG_LEVEL` — so each is
separately visible and separately wrong.

#### The variables that deliberately have **no** default, and why

**A default here is not a convenience. It is the difference between a deployment that refuses to start
and a deployment that starts and is quietly wrong.**

| Variable | What it is for | Why it has no default, and what breaks if it is wrong |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | No correct guess exists. A default localhost value produces a container that starts, connects to nothing and reports healthy. |
| `REDIS_URL` | Redis connection string, for locks, cache and rate-limit buckets | Same. Wrong value: every hold returns 503 and readiness is permanently 503. |
| `QUEUE_URL` | SQS in AWS, ElasticMQ locally. One interface over both | Same. Wrong value: receipts accumulate in the outbox and never leave. |
| `JWT_SECRET` | Signs the session token | **A default signing secret is a forged session for anyone who reads the source.** Rotating it invalidates every live session, which is a runbook entry and not an automated process. |
| `PAYMENT_PROVIDER` | Selects the simulated payment provider. The only permitted value is `simulated` | **A default here makes a deployment a fake shop silently.** There is no fallback, because a fallback is how a deployment quietly becomes one. Reported by `/health/ready` and logged prominently at boot. |
| `MAIL_PROVIDER` | Selects the mail transport. **Exactly two values exist: `ses` and `stub`.** `ses` sends through Amazon SES; `stub` writes the message to stdout and sends nothing, and is for local development only | A default to the stub means **a deployment silently sends nothing** — every customer pays and no receipt leaves the building, and nothing in the product reports a fault. **There is no third value and no fallback**, exactly as `PAYMENT_PROVIDER` has none: any other value exits non-zero at boot with a message naming both permitted values. Cross-check 13. **The stub's value had never been written down anywhere**, which meant a local `docker compose up` could not be brought up from this document at all — the operator had a required variable and no vocabulary to put in it. |
| `S3_BUCKET_NAME` | The private bucket holding posters | Environment-specific. Wrong value: poster upload fails and the presigned redirect points at nothing. |
| `AWS_REGION` | Region for the SDK clients | Environment-specific. Wrong value: SQS, SES and S3 calls fail against a region with none of them, and a wrong region silently inspects an empty account. |
| `SES_SENDER_ADDRESS` | The verified sender identity for receipts | It must be an identity the client has verified; there is no correct guess. Wrong value: every receipt is rejected by SES, and **the customer has paid and cannot enter the hall.** |
| `PUBLIC_BASE_URL` | The address used in emailed links | Wrong value: the link in a receipt goes nowhere. |
| `COOKIE_SECURE` | The session cookie's `Secure` flag | **`OPEN-TLS-01` is deferred and a default would decide it.** Set true without TLS and the browser never sends the cookie, so nobody can stay signed in. Set false once TLS exists and the cookie travels in the clear. |
| `FORWARDED_ALLOW_IPS` | The single trusted proxy for `X-Forwarded-For` | **A wildcard trusts any peer's header, which is the same as trusting the client**, and the rate limiter then protects nothing while appearing to work. The load balancer's subnet range is a Zone C value the application needs. Boot rejects `*`. |
| `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX` | The `Idempotency-Key` prefix that makes the simulated payment fail deliberately, so a failure can be demonstrated and tested without a random failure rate | **A default would be a prefix an ordinary customer could hit by accident**, turning a real booking into a failed payment. It is validated at boot as a string of 1–32 characters, and it is a **header** prefix rather than a request-body field so no failure-control field ever enters the public request contract. **Which outcome the prefix produces is specified by the checkout and payment section, not here.** |

#### The variables with a default, because the value is ruled and the default **is** the ruled value

| Variable | Default | What it is for | What breaks if it is wrong |
|---|---|---|---|
| `SEAT_HOLD_TTL_SECONDS` | `180` | The seat hold, ruled at 3 minutes | Too long: seats are held off sale. Too short: customers cannot finish. **A literal `180` anywhere in the code is a defect** — this value has already been changed once by a client message. |
| `MAX_SEATS_PER_BOOKING` | `10` | The ruled cap, enforced server-side | Above 10 contradicts a ruling and boot rejects it. Below 10 is stricter and permitted. **Because below 10 is permitted, every customer-facing string quoting the cap renders this value and never a literal `10` (`S7.21`)** — a literal would tell the customer a limit the server does not enforce, and the two agree at the default so no test catches it. |
| `SALES_CUTOFF_MINUTES` | `+15` | Signed offset from the advertised start. **`PROVISIONAL`** — the alternative reading is 15 minutes *before* | Sign error moves the cut-off by half an hour and either closes sales early or sells seats for a show that has started. |
| `CURRENCY_CODE` | `INR` | The ruled currency | A different value would need a rounding rule and a minor unit nobody ruled. |
| `CURRENCY_MINOR_UNIT_RATIO` | `100` | Paise per rupee | **A one-way door.** Changing it silently rewrites what every past customer paid. Cross-checked against `CURRENCY_CODE` at boot so that changing it is deliberate rather than a typo. |
| `CINEMA_TIMEZONE` | `Asia/Kolkata` | The zone every human-read time is rendered in | An invalid name fails at the first date comparison rather than at boot, unless checked — so it is checked. A wrong zone puts "today's showtimes" on the wrong day. |
| `SEATMAP_CACHE_TTL_SECONDS` | `10` | Seat-map cache entry lifetime | Longer: worse worst-case staleness. Zero: every poll rebuilds from PostgreSQL. |
| `LISTING_CACHE_TTL_SECONDS` | `60` | Movie and showtime list cache lifetime | Longer: an admin's publish takes longer to appear. |
| `SEATMAP_POLL_INTERVAL_SECONDS` | `3` | How often the client re-reads the map | Shorter multiplies read load; longer widens the staleness window. |
| `CACHE_REBUILD_LOCK_TTL_MS` | `2000` | The per-key stampede guard | Too short and two callers rebuild; too long and a crashed rebuilder blocks others until it expires. |
| `PAYMENT_SIMULATED_DELAY_MS` | `1500` | Makes the simulated flow realistic and exercises the loading state | **It must never approach the hold.** A payment step that outlives the hold is a customer who paid for expired seats. Cross-checked at boot. |
| `REDIS_CONNECT_TIMEOUT_MS` | `500` | Connect timeout | **No timeout turns an unreachable node into hung requests rather than a 503, and hung requests exhaust the connection pool.** |
| `REDIS_COMMAND_TIMEOUT_MS` | `500` | Per-command timeout | Same. |
| `SHUTDOWN_DRAIN_TIMEOUT_SECONDS` | `20` | How long in-flight requests get on SIGTERM | Longer than the container stop timeout and SIGKILL arrives before the locks are released. |
| `READINESS_CACHE_TTL_SECONDS` | `3` | How long a readiness result is reused | Longer than the load balancer's unhealthy-threshold window and it reacts to stale information. |
| `LOG_LEVEL` | `INFO` | Log verbosity | `DEBUG` in a deployed environment consumes the 5 GB CloudWatch allowance and risks logging request bodies. |
| `DB_POOL_SIZE` | `5` | Connections held per process | `db.t3.micro` has roughly 110 maximum connections, and pool size multiplies across processes. Too large exhausts them; too small serialises requests. |
| `DB_POOL_MAX_OVERFLOW` | `2` | Burst connections above the pool | Same ceiling. |
| `DB_STATEMENT_TIMEOUT_MS` | `5000` | The server-side ceiling on a single SQL statement, set on the connection. **`ASSUMED`** — `P-RPT-12` and `P-RPT-07` both branch on an aggregate exceeding it and no figure, variable or row existed anywhere, which by this inventory's closing rule was a defect. | **Both ends are observable and they fail differently.** Too low and a legitimate month-wide dashboard aggregate is killed mid-query and the admin reads `This period's figures could not be loaded` for a period that is simply large — an error for a correct request. **Too high, or absent, is the worse one:** with no timeout a slow aggregate holds one of `DB_POOL_SIZE` + `DB_POOL_MAX_OVERFLOW` = **7 connections per process** indefinitely, and a handful of them exhausts the pool — so **the failure is the whole dashboard, and then the whole API, rather than the one request that was slow.** Replaced by Phase 7's load test. |
| `QUEUE_POLL_WAIT_SECONDS` | `20` | Long-poll wait | Short polling against a mostly-empty queue burns the 1M-request free-tier allowance on empty receives. |
| `QUEUE_SEND_TIMEOUT_MS` | `2000` | The ceiling on one `SendMessage` call, including any SDK-level retry — **retry is disabled on this path, so the wall-clock bound is this value and not a multiple of it**. **`ASSUMED`** — no frozen source names it; the receipt section requires the fast-path send to be bounded and named none, which by this inventory's own rule was a defect. | **This is the only dependency call that runs inside a customer's confirm request** (`P-PAY-10` step 15, `P-TKT-04` step 3), and the confirm response is emitted after it returns. **Absent, the timeout is infinite:** an unreachable queue holds the confirm response open until the load balancer's idle timeout, so a customer whose booking is already committed sees a failed request — the exact cost the transactional outbox exists to prevent. Too high has the same shape more slowly. Too low costs nothing but a relay 30 seconds later. **It must stay well below `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`**, or a SIGTERM during a hung send outlives the drain and SIGKILL lands mid-request; at 2000 ms it is a tenth of it. Replaced by Phase 7's load test. |
| `SES_SEND_TIMEOUT_MS` | `5000` | The ceiling on one `SendEmail` call in the worker. **`ASSUMED`** — no frozen source names it; the receipt and password-reset paths both require the call to be bounded and named no value. | **Absent, a hung call holds the `receipt_dispatch` claim in `sending` and no redelivery can retake the send for `RECEIPT_CLAIM_STALE_SECONDS` — 900 seconds in which the customer has paid, no receipt has gone out and nothing is being attempted** (`P-TKT-05`). The same hole exists on `password_reset_token.email_claimed_at`, on the one message a locked-out account depends on (`P-TKT-12`). **It must be shorter than the worker's drain** — `P-XCT-17` exception 5 makes the drain as long as the message in hand — and **far shorter than the queue's visibility timeout**, so a delivery reaches `sent` or `failed` before its own redelivery arrives. Too low fails ordinary receipts under no fault at all. **A timed-out send has an unknown outcome and the retry may deliver a second copy**; the receipt section states that consequence rather than assuming it away. Replaced by Phase 7's load test. |
| `OUTBOX_RELAY_BATCH_SIZE` | `20` | Rows the worker relays per loop | Too large and the relay starves the queue poll. |
| `OUTBOX_RELAY_MIN_AGE_SECONDS` | `30` | How old a `pending` row must be before the relay claims it | Too short and the relay races the request that is already sending it. **The receipt section's "roughly 30 to 50 seconds" worst-case arithmetic is derived from this number**, so changing it here without changing that figure makes two sections disagree about how late a receipt can be. |
| `RECEIPT_CLAIM_STALE_SECONDS` | `900` | When a `sending` claim is treated as abandoned | **Without it, a worker killed mid-send leaves a claim nobody can ever take and the receipt never goes out.** Shorter than the queue's visibility timeout and two workers send twice. |
| `POSTER_MAX_BYTES` | `2097152` | Upload size ceiling, rejected at the header | Larger risks buffering a big body on a small host. |
| `PRESIGNED_URL_TTL_SECONDS` | `3600` | Poster URL lifetime | Shorter than a page view and images break mid-scroll. |
| `PASSWORD_MIN_LENGTH` | `12` | The length floor | Lower weakens every account. **Customer copy quoting the floor renders this value (`S7.21`).** The 72-**byte** maximum is fixed by bcrypt and is **not** configurable, so copy quoting *that* is correctly a literal — it is `S7.21`'s stated counter-example, and the test is whether the value has a row in this table. |
| `SESSION_TTL_SECONDS` | `43200` | Session lifetime, 12 hours | Too long and a shared device stays signed in; too short and customers are signed out mid-flow. **No frozen source names this value.** It is the build session's under Art III.9 and it is listed in the lane notes for the merge pass to file. |
| `PASSWORD_RESET_TTL_SECONDS` | `1800` | Single-use reset token lifetime, 30 minutes | Too long widens the window on an emailed token. **No frozen source names it either.** Same treatment. **The value is the account section's, not this one's**: its customer-visible copy tells the customer the link expires in 30 minutes, in three places, and a mismatch here expires a link while the screen says it is still good. The *name* is this section's; the *number* is theirs. |
| `STRESS_CONCURRENCY_SPREAD_MS` | `100` | The threshold the stress script's self-concurrency check asserts against | Too loose and a serialised client passes as concurrent, which makes the whole proof worthless. |
| `BCRYPT_THREAD_POOL_SIZE` | `2` | How many bcrypt hashes may run at once. **`ASSUMED`** — no frozen source names it; `P-ACC-03` requires it to be a named setting and named none, which by this inventory's own rule was a defect. The default is the `t3.micro`'s **vCPU count**, because bcrypt at cost 12 is CPU-bound: a larger pool does not parallelise, it queues, and it converts a fast refusal into a slow one. | **This number is the concurrency at which sign-in starts returning `503`**, which is why it may not stay implicit. Too low and the fiftieth stress-script warm-up sign-in waits behind forty-nine others; too high and the host thrashes while every request holds a thread. Replaced by Phase 7's load test. |
| `BCRYPT_HASH_TIMEOUT_MS` | `5000` | How long a single hashing attempt may take, including its wait for a pool slot, before the request is abandoned. **`ASSUMED`** — `P-ACC-03`'s exception 3 fires on "the request times out" and no timeout value existed anywhere. | **Absent, the timeout is infinite and the exception path `P-ACC-03` specifies is unreachable** — a saturated pool then holds requests until the load balancer or the client gives up, which is the failure that looks like a hang rather than an error. Shorter than the load balancer's idle timeout, and comfortably longer than one hash at `BCRYPT_COST` (roughly 300 ms, `[UNPROVEN HERE]`), or ordinary sign-ins fail under no load at all. |
| `BCRYPT_COST` | `12` | bcrypt work factor for password hashing | **The build session's own choice** (`[JUDGMENT CALL]`, the account section), picked to sit near the 300 ms figure carried in `GOTCHAS.md`, which is itself `[UNPROVEN HERE]` and is measured in Phase 7. Too low weakens every stored password; too high is real CPU on a 1 GB host and stalls logins, and the hashing thread pool size is its companion tuning value. |
| `POSTER_REDIRECT_CACHE_SECONDS` | `300` | `Cache-Control: max-age` on the poster redirect | **`ASSUMED`** — no frozen source states one; the browse section owns it and Phase 6 tunes it. **The bound is not assumed:** it must stay below `PRESIGNED_URL_TTL_SECONDS`, or a browser re-uses a cached redirect whose presigned target has already expired and the image breaks mid-page. Cross-checked at boot, check 11. |
| `API_PORT` | `8000` | The TCP port the API's HTTP server binds inside the container | **Below 1024 the container cannot bind it at all** — both images run as a non-root user created in the Dockerfile (`P-XCT-18`), and only root may bind a privileged port, so the process exits at boot. Wrong value above 1024: the container starts, listens on a port nothing points at, and **fails the load balancer's health check while looking perfectly healthy in its own logs**. |
| `WORKER_METRICS_PORT` | `8001` | The TCP port the worker's own small `/metrics` listener binds (`P-XCT-13`) | Same non-root floor. If it collides with `API_PORT` on a host where both containers share a network namespace, **the second process to start fails to bind and the worker dies on boot** — which stops receipts, not requests, so it is the failure nobody notices until a customer has paid. Cross-checked at boot, check 12. |
| `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` | `300` | The minimum gap between two accepted receipt resends **for one booking** | **`ASSUMED`** — `FR-ADR-048` rules that the resend is limited per booking and names no number. Too short and one booking's receipt can be re-sent repeatedly, which is the thing the record asks to prevent; too long and a customer whose first receipt genuinely failed waits for a copy they have already paid for. The customer-visible wait ("in 4 minutes") is **computed from this value, never typed into the string**. See the receipt-resend row in S7.4. |

**The rate-limit buckets are configuration too**, one variable per value, so the Phase 7 load test can
replace them without a code change. **Every one of these numbers is an estimate, not a measurement.**

| Variable | Default | Variable | Default |
|---|---|---|---|
| `RATE_LIMIT_HOLD_USER_PER_MIN` | `20` | `RATE_LIMIT_HOLD_IP_PER_MIN` | `60` |
| `RATE_LIMIT_CONFIRM_USER_PER_MIN` | `10` | `RATE_LIMIT_CONFIRM_IP_PER_MIN` | `30` |
| `RATE_LIMIT_LOGIN_USER_PER_15MIN` | `10` | `RATE_LIMIT_LOGIN_IP_PER_15MIN` | `30` |
| `RATE_LIMIT_REGISTER_IP_PER_HOUR` | `5` | `RATE_LIMIT_RESET_IP_PER_HOUR` | `5` |
| `RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR` | `10` | | |
| `RATE_LIMIT_LOOKUP_USER_PER_MIN` | `20` | `RATE_LIMIT_LOOKUP_IP_PER_MIN` | `60` |
| `RATE_LIMIT_SEATMAP_IP_PER_MIN` | `120` | `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` | `60` |

**Two of those names do not follow the `RATE_LIMIT_*` pattern, and that is deliberate rather than
sloppy.** `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` and `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` are
already carried under those exact names in the API contract and in the sections that own those
surfaces. **Renaming them here to tidy the pattern would put this inventory and the contract out of
step, which is the failure this inventory exists to prevent**, so the names are taken as they are.
`RECEIPT_RESEND_MIN_INTERVAL_SECONDS` sits in the defaults table above rather than here, because it
is an interval rather than a bucket size — S7.4 carries its row.

**The two ports are a Zone C surface, and the specification owes the client the value.** `P-XCT-18`
says the application "listens on a high port and the target group points at it" and `P-XCT-13` says
the worker exposes `/metrics` on its own listener; **neither port nor a variable name for either
appeared anywhere in this document, which by this inventory's own rule below was a defect.** The
container port is what the client's **target group**, **security group ingress rule** and **listener
rule** are all built against — three Zone C artefacts that cannot be built without a number. The
build session writes none of them (`P-XCT-26`, `FR-ADR-004`); it owes the number, the variable name
and what breaks if they disagree, and `docs/30 Deployment/` carries it. **A target group pointing at
the wrong port is the single most common first-deployment failure of this shape**: every task starts,
every container reports healthy to Docker, and the load balancer drains all of them.

**`/metrics` is not routed through the load balancer** (`P-XCT-13`). `WORKER_METRICS_PORT` and the
API's `/metrics` path exist for an operator with a terminal on the host. **No listener rule routes
either**, and the specification says what is disclosed if one does.

#### Read by the seed script only, never by the API or the worker

**These two are in this inventory because the inventory is complete or it is worthless, and they are in
their own table because the API and the worker must not require them.** A variable the seed needs,
listed among the API's required settings, is a container that refuses to boot over a value it never
reads.

| Variable | Default | What it is for | What breaks if it is wrong or absent |
|---|---|---|---|
| `SEED_DEFAULT_PASSWORD` | **none — required by the seed script, and by nothing else** | The one password set on every account `scripts/seed.py` creates (`P-XCT-32`) | **Absent: the seed exits non-zero before writing anything, and there is no other route to a first password** — hashes cannot be read back (`P-XCT-06`) and the reset flow needs SES, which is sandboxed and rejects every seeded address (`FR-ADR-060`). **Phase 2 has no admin who can sign in and Phase 4 has no fifty customers, so the concurrency proof cannot run** (`FR-ADR-034`). Under `PASSWORD_MIN_LENGTH` **characters**, or over 72 **bytes** — the two bounds are in different units and each is checked in its own: bcrypt silently ignores the excess past 72 bytes and a shorter password works, which is worse than a refusal. Equal to the `.env.example` placeholder: refused by value, because the placeholder must never become the deployed password. **It is never committed, never printed and never logged.** **How it reaches a deployed environment** is `P-XCT-32`'s: an SSM `SecureString` referenced from **the seed's own one-off task definition family**, never the service's, which is what lets it be seed-only and still arrive the way `P-XCT-16` requires. |
| `SEED_CHANGEOVER_MINUTES` | `20` | Minutes added to a seeded film's runtime to produce `showtime.ends_at`, which is `NOT NULL` (`P-XCT-30`) | **`ASSUMED`, and deliberately not an answer to `PROPOSED-TURNAROUND-01`**, which asks the client to rule the real changeover between shows. The seed needs *a* number because the column cannot hold an open question. Larger than 50 makes the seeded schedule overlap itself at the 210-minute slot spacing and the seed trips `P-ADM-08`'s own overlap refusal; absent, `ends_at` cannot be computed and the seed exits before its first write. **When the client rules the real figure, that row changes and this follows it.** |
| `SEED_EMAIL_DOMAIN` | `demo.frontrow.invalid` | The domain every seeded address sits at | `.invalid` is reserved by RFC 2606 and can never resolve, which is what makes seeded data identifiable at a glance (`FR-ADR-067`) and makes it impossible for a seeded address to receive real mail. **Set it to a real domain and seeded bookings become hard bounces against the sending identity's reputation**, which can suspend the SES account and take the real receipt path down with it (`FR-ADR-060`). |

**Two values that are deliberately not environment variables.** The **instance id** is generated at
boot, because it must be unique per running process and an operator setting it by hand would
eventually set two the same. The **`service` field** (`api` or `worker`) comes from the entrypoint's
command argument, because it is what the process actually is rather than what someone declared it to
be.

**One value is deliberately absent from this repository entirely:** the client's alert email address.
It lives in the SNS subscription the client creates and in local `.env`. Nothing downstream needs the
literal string.

#### The cross-field checks run at boot

Per-field types are not enough. These are the ones that would otherwise be found in the deployed
environment, and each lives in the Zone B configuration file with a comment saying so.

| # | Check | What it prevents |
|---|---|---|
| 1 | `PAYMENT_SIMULATED_DELAY_MS < SEAT_HOLD_TTL_SECONDS × 1000 × 0.1` | A customer paying for seats whose hold has already expired. |
| 2 | `CURRENCY_MINOR_UNIT_RATIO == 100` while `CURRENCY_CODE == INR` | A one-way door being walked through by a typo. |
| 3 | `CINEMA_TIMEZONE` resolves in the zone database | Failing at the first date comparison instead of at boot, with "today" landing on the wrong day. |
| 4 | `PAYMENT_PROVIDER == "simulated"` — the only permitted value | A deployment believing it has a real provider, which this project never has. |
| 5 | `COOKIE_SECURE` is false unless `PUBLIC_BASE_URL` begins `https://` | A cookie the browser will never send, so nobody can stay signed in. |
| 6 | `FORWARDED_ALLOW_IPS != "*"` | A rate limiter that trusts a forged header and protects nothing. |
| 7 | `MAX_SEATS_PER_BOOKING` is between 1 and 10 inclusive | Exceeding a client ruling. Below 10 is stricter and allowed. |
| 8 | `MAIL_PROVIDER == "ses"` requires `SES_SENDER_ADDRESS` and `AWS_REGION` to be non-empty | Receipts failing at send time rather than at boot. |
| 9 | `RECEIPT_CLAIM_STALE_SECONDS > OUTBOX_RELAY_MIN_AGE_SECONDS` | The relay reclaiming a send that is still in progress. |
| 10 | `SEATMAP_CACHE_TTL_SECONDS + SEATMAP_POLL_INTERVAL_SECONDS <= 15` | Worst-case staleness drifting past what "accurate within a few seconds" can carry. |
| 11 | `POSTER_REDIRECT_CACHE_SECONDS < PRESIGNED_URL_TTL_SECONDS` | A browser re-using a cached redirect whose presigned target has already expired, so posters break mid-page for exactly the customers whose browsers cached best. |
| 12 | `API_PORT` and `WORKER_METRICS_PORT` are each between `1024` and `65535`, and are not equal to each other | A non-root container told to bind a privileged port, which fails at boot with an error that reads like a permissions problem in the wrong layer; and two processes told to bind the same port, where the second dies and takes receipts with it. **Checked at boot in both processes, so each refuses its own bad value rather than only the one that happens to start second.** |
| 13 | `MAIL_PROVIDER` is exactly `ses` or `stub` — the only permitted values | A deployment that starts with a mail transport nobody named. **The failure without this check is the worst shape available**: a typo does not stop the process, it makes `MAIL_PROVIDER == "ses"` false, check 8 then never fires, and the deployment runs with **no transport at all** — bookings succeed, receipts vanish, and the customer has paid and cannot enter the hall. |

**Three checks run at the seed script's own start rather than at the API's boot**, because the seed is
the only process that reads their variables, and they run **before its first write** so a failure
leaves the database exactly as it was (`P-XCT-32`): `SEED_DEFAULT_PASSWORD` is present; it is at
least `PASSWORD_MIN_LENGTH` **characters** and at most 72 **bytes**; and it is not equal to the
placeholder value `.env.example` ships. Each exits non-zero naming the variable. **The two length
bounds are measured in different units on purpose** — the floor is a character count, matching what
`P-XCT-06` enforces at registration, and only the 72 is a byte bound, because only bcrypt's limit is
one. A floor stated in bytes would admit a twelve-byte password of four multi-byte characters that the
registration path refuses.

**Three relationships cannot be checked at boot and must therefore be stated in the Zone C
specification**, because the values live outside the application: the container stop timeout must
exceed the deregistration delay plus `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`; the load balancer's
unhealthy-threshold window must exceed `READINESS_CACHE_TTL_SECONDS`; and **the target group's port,
the security group's ingress port and the container's published port must all equal `API_PORT`**.
**All three break silently** — the third presents as every task failing its health check while the
application logs show a healthy process serving requests nobody is sending it.

**The resolved configuration is logged once at boot, with secret values redacted**, so an operator can
read what the process actually loaded. **`.env.example` is complete and current**: every variable, a
comment saying what it does and what breaks without it, and placeholder values that are obviously
placeholders. **No real value and no credential.**

**The variable list is the input to the Zone C specification** — the client's task definition has to
supply every one of them, and `docs/30 Deployment/` owes them the list with each variable's source.

#### How this inventory stays complete, stated plainly

**This inventory is the single source for every setting the application reads.** There is no second
list. A section that introduces a setting and does not add it here **is a defect**, not a matter of
housekeeping, and it is fixed by adding the row rather than by noting the omission.

The reason is mechanical rather than tidy-minded. This list is what the client's ECS task definition
is built from and what `.env.example` is generated against. A variable that exists in code and not
here is a variable the task definition does not set, so the container **either crashes at boot naming
it — the good outcome — or starts on a default nobody chose**, which is the outcome every "no default"
row above exists to prevent. **A setting owned by another section still lives here**: the section owns
the *value* and the behaviour, this inventory owns the *name and the completeness*, and where the two
disagree the owning section's value wins and this row is corrected to match it.

---

### S7.10 — Graceful shutdown

**On SIGTERM: stop accepting, drain in-flight, release this instance's Redis locks, exit.**

**A stateless instance does not know which locks are its own** — the locks live in Redis, keyed by
seat, and carry a hold token rather than an instance id. So the instance keeps a **registry in
Redis**: each API instance generates an id at boot, and when it grants a hold it adds the hold's keys
to `instance:{instance_id}:holds`, with the same 3-minute TTL as the holds themselves. **In Redis
rather than in process memory**, because statelessness forbids local state and because a process
killed with SIGKILL — which is what follows SIGTERM after the grace period — loses in-memory state
before it can act on it. The TTL means an instance that vanishes leaves no permanent garbage.

**The ordering:**

1. The instance is deregistered from the load balancer target group and stops accepting new
   connections.
2. It waits out the **deregistration delay**, so in-flight requests already routed to it complete.
3. In-flight requests finish, bounded by `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`.
4. The registry is read and the compare-and-delete release is run for each key.
5. The process exits.

**Only holds are released. Bookings are never touched.** A hold whose booking committed had its lock
released at commit and is already gone from the registry, so what remains at shutdown is, by
construction, holds that never became bookings. **The compare-and-delete means this cannot free
someone else's lock:** if a hold expired and another customer re-acquired the seat during the drain,
the token no longer matches and the delete is a no-op.

**Holds that are still legitimately live are dropped, and that is intended.** A customer mid-checkout
on a draining instance loses their hold and re-selects. Keeping their seats locked while the instance
that granted them disappears leaves the seats unbuyable for up to three minutes and does not help that
customer either, because their next request goes elsewhere and they re-select regardless.

**Correctness never depends on the release running. Expiry is the guarantee.** If the release fails,
if the grace period is too short, or if the instance is SIGKILLed, the locks expire in three minutes
and no booking is affected. **That is the property that makes this safe to get wrong** — and it is why
the clause is not redundant with expiry: it exists to *shorten* a window that expiry would eventually
close.

**What a deploy during a busy period costs without it.** Every seat that instance was holding is
unbuyable for the full TTL, **with no error anywhere** — a customer looking at the map sees seats that
are held by nobody and cannot take them. On this project, with one instance and a fixed host port, a
deploy already has a hard downtime window, so this adds nothing a customer would not already notice;
on a larger deployment it would be the difference between a rolling deploy and a block of dead seats.
**It belongs in the runbook: deploy when nobody is buying.**

**The container stop timeout must exceed the deregistration delay plus the drain timeout.** If it does
not, SIGKILL arrives at step 3 and steps 4 and 5 never happen. **That relationship is the thing that
breaks silently, and it is a Zone C configuration the client sets**, so the specification owes the
three values, their required ordering, and what breaks if they are wrong. *(reasoned, not observed.)*

**The worker's shutdown is different.** On SIGTERM it stops polling, finishes the message it is
currently handling, completes any outbox relay batch in progress, and exits. It does **not** abandon an
in-flight message to the visibility timeout, because the claim row makes finishing safe and abandoning
it merely slower.

**Testing this requires sending a real SIGTERM to a running container and asserting the locks are
gone.** A unit test proves the function; only the signal proves the wiring.

---

### S7.11 — Migrations

**Alembic. A separate step. Never on boot, never automatically.**

**There is no code path in the API or the worker that can apply a migration.** Not at import, not in a
lifespan hook, not in the entrypoint's default path, and **not behind a `RUN_MIGRATIONS` flag** — a
flag would be set to true once, during an incident, and never set back.

**The entrypoint takes a command argument.** There are four: `api`, `worker`, `migrate` and `seed`.
`migrate` runs `alembic upgrade head` and exits with the migration's status. **`seed` runs
`scripts/seed.py` and exits with its status, and it is `P-XCT-32`'s** — it is listed here so the
argument set is complete in one place, and it applies no migration. `api` and `worker` start
long-running processes and never touch migrations. In AWS
this is a one-off task using the **same image and the same task definition family**, with the command
overridden — so the migration and the code are the same build. **That run is Zone C**; the build
session ships the entrypoint, heavily commented, and owes the specification.

**Why it is a separate step, and it is not a stylistic preference. Alembic does not take an advisory
lock.** This is widely believed and it is not true, so two tasks booting together race on
`alembic upgrade head`. Making migrations a separate step removes the race, and **that is the reason
for the rule.** Running them in the entrypoint before starting the process is boot-time migration with
extra steps: every task start runs them, so scaling from one task to two races exactly as the clause
warns.

**The deploy order is one-directional:** migrate, confirm it succeeded, then update the service to the
new image. **Which means every migration must be backwards-compatible with the code currently
running**, because there is a window in which the old code runs against the new schema. On one
instance with a hard downtime window that is short — but it exists, and a migration that drops a
column the running code selects turns a short window into an outage.

**No down-migrations are written or run.** Alembic's `downgrade` stub stays a stub that raises.
Nothing is ever deleted, and a downgrade that drops a column destroys data irreversibly, which is a
stop-and-ask rather than something that sits in the repository ready to run. **A bad migration is
corrected by a new forward migration.**

**Locally the same command runs against the compose stack**, so the thing the client runs in AWS is
the thing they have already run twenty times locally. **Compose does not run migrations** — no
`depends_on` chain applies them and no service runs them on start, because automating it locally would
remove the habit the deployed process depends on.

**Build against a restricted role from day one.** Local PostgreSQL gives you superuser and RDS never
does, so a migration that works locally can fail on RDS on superuser, forced SSL, or the allowed
extension list. The compose stack creates an application role without superuser so the difference is
caught on a laptop instead of during a deploy.

**Migrations are reviewed for what they lock.** On a `db.t3.micro` an `ALTER TABLE` that rewrites a
large table blocks it for the duration. `audit_log` and the seat-occupancy table are the two that grow
without bound, and a migration touching either states in a comment what it locks and for roughly how
long.

**A manual snapshot is taken immediately before every migration.** It is one more command in the same
procedure, and manual snapshots persist beyond the automated retention window — they are the only
thing that makes a bad migration recoverable after seven days.

**The common mistake the specification must name:** forgetting the migration produces a running
service against an old schema, and **the symptom is a 500 at the first query touching a new column,
not a startup failure.** The one-off task also needs the same execution role and the same SSM
permissions as the service, because it reads `DATABASE_URL` the same way — a common omission.

---

### S7.12 — The 1 GB memory budget

**Three long-running processes, each with an explicit memory limit. No container runs unlimited** — a
container with no limit takes the host down instead of dying itself, which turns one process's leak
into a total outage.

```
t3.micro total ........................................ 1024 MB
less operating system + Docker daemon + ECS agent ..... 300–400 MB
available to our containers ........................... 624–724 MB
```

| Container | Limit | Basis |
|---|---|---|
| API | ~200 MB | Python, the web framework, the ORM, a connection pool, one uvicorn worker |
| Worker | ~150 MB | the same libraries, no HTTP server, a smaller pool |
| Static frontend | ~15 MB | a static web server and the built assets |
| **budgeted** | **~365 MB** | leaving 259–359 MB of headroom |

**Image size targets:** the backend image under **250 MB**, the frontend well under **50 MB**, both
multi-stage. **ECR holds 500 MB in total, and it holds history, not just the current image** — two
tags of each at target size fills it, which is why an ECR lifecycle policy is not optional
housekeeping. Without one, every push accumulates until the free tier is exhausted, and **the failure
appears as a push rejected during a deploy.**

> **Every figure in this section is `(reasoned from typical figures, not observed)`.** No part of this
> application has ever run, in AWS or anywhere. **They are replaced with measured numbers at the end
> of Phase 1**, which is the first thing that deploys. Recording the resident set size of each
> container under idle and under the load test is a Phase 1 deliverable, not just a deployment.

**Decisions this budget has already driven**, recorded so they are not re-litigated as independent
choices: **three processes, not four** — the scheduler is deleted and there is nothing left for it to
run; **a static frontend container, not a Node process** — roughly 15 MB against roughly 150 MB;
**one uvicorn worker per API container**, because each worker is a full Python process and two roughly
doubles the API's footprint; **a deliberately sized connection pool**, because `db.t3.micro` has
roughly 110 maximum connections and pool size multiplies across processes; **no local S3 or SMTP
stand-in container.**

**What an over-limit container does, and the specification must say it plainly:** with a hard memory
limit, a container that exceeds it is **killed by the kernel with an out-of-memory error. It does not
slow down and it does not warn.** The symptom is a task that restarts with no application log
explaining why, because the process died without a chance to write one. *(reasoned, not observed.)*

**Nothing in this specification is currently known not to fit in 1 GB — and that statement is itself
an estimate.** If a measured figure exceeds its limit, **the client is told, with the number and what
it would take to fit. Not quietly raised, not quietly worked around.** The headroom is deliberate: if
measurement shows the API at 300 MB rather than 200 MB it still fits, which is why the estimate being
wrong is survivable.

**Setting the limits is Zone C.** They live in the task definition; the build session owes the values
and the reasoning.

---

### S7.13 — Accessibility and responsive behaviour

**WCAG 2.2 Level AA is the adopted target.** Nobody asked for it. It is adopted as the build session's
own standard, and adopting a stricter option needs no signature. **No conformance is claimed**, because
a claim would need testing this project has not done, and an untested claim is invented evidence.

**Every contrast figure is computed and recorded, never asserted.** The figures live in
`docs/05 B DesignSystem/CONTRAST.md`, which is **generated** by `contrast.py` from the annotations in
`tokens.css`, **and nowhere else.** A ratio typed by hand into any document is a defect. Every colour
token carries a machine-readable annotation naming what it is — a ground, a foreground held to 4.5:1,
a non-text component held to 3:1, or an exemption that must state its reason — and the grounds it is
allowed to sit on. **A colour without an annotation fails the check, so a colour cannot enter this
system unmeasured.** A pair with no recorded figure has not been checked and a design review may not
pass it.

**A ruling that must not be read wider than it was given.** `OPEN-SEAT-02` ruled out **accessible-seat
marking** — a product feature about wheelchair spaces — on the grounds that this is a demonstration
project. That says nothing about whether the *interface* is usable by a person with a disability, and
reading it as a licence to skip interface accessibility would be reading a ruling wider than it was
given.

**What the target requires here:**

- **Seat states carry a non-colour cue** as well as colour, so "clearly distinguished" holds for a
  colour-blind customer.
- **Every seat has an accessible name** stating its identity, its category and its state. A grid of
  unlabelled buttons is unusable without sight.
- **The seat map is one tab stop with arrow-key grid navigation.** Giving 220 seats their own tab
  stops is technically conformant and unusable.
- **Every interactive element is keyboard-reachable and operable**, focus order follows visual order,
  and the focus indicator is visible against every background it can appear on. The focus ring is
  drawn with an offset so it sits on the surface behind the control, which is what lets one token be
  measured against the three page grounds.
- **Every input has a programmatically associated label**; errors are associated with their field and
  are **announced**, not only coloured.
- **Motion collapses under `prefers-reduced-motion`**, with one exception: the mark on a seat that
  changed under the reader on the last poll survives as a static ring, because it is information
  rather than decoration.

**The one recorded deviation.** The three-minute hold is a time limit, and the AA timing criterion
normally requires a time limit to be adjustable. **It is not adjustable here**, because the limit
exists to release a scarce resource to other customers and an extension would let one customer hold a
seat indefinitely. **This is recorded as a known deviation rather than papered over.** The mitigation
is that the limit is displayed from the start, warned at 60 seconds, and the customer's selection is
restored on expiry so nothing is lost but the seats.

**Explicitly not in scope and not claimed:** accessible-seat marking as a product feature, a
screen-reader-optimised alternative to the seat map, and formal conformance testing or a published
accessibility statement.

**Responsive behaviour.** **The design target is the largest hall's seat map — 220 seats, `ASSUMED` —
on a 375-pixel-wide phone.** Layout uses flexbox and grid with relative units. **The page body never
scrolls horizontally**; anything wider scrolls inside its own container, and the seat map is the only
component that regularly needs this. The seat is 24 pixels, which is the target-size minimum:
**shrinking the seat to make a hall fit is how a product fails a criterion to win an argument with a
layout.** Poster slots reserve a 2:3 box before the image arrives so a listing does not reflow when it
loads. The page gutter is one step on a phone and a larger step above 40rem.

**There is no browser or version matrix in any frozen source, and none is invented here.** The stack
is React and Vite with plain CSS custom properties and CSS Modules; what that supports is a property
of the toolchain, not a decision this document may make. **If the client needs a supported-browser
statement, that is a question for them, not an omission to be filled in.**

---

### S7.14 — What nobody is watching

**One alarm exists: CloudWatch on the ECS service's running task count below 1, delivering through SNS
to the operator's own address.** The alarm, the topic and the subscription are Zone C — the client
builds all three, and the specification owes the metric, the threshold, the evaluation period, the
treatment of missing data, and the acceptance criterion, which is: stop the service, receive an email.

**The mistake that makes this alarm useless: leave missing data at its default.** If the service is
deleted or the metric stops being published, the default treatment leaves the alarm in
`INSUFFICIENT_DATA` and **it never fires.** Set missing data to `breaching`. **An alarm that stays
quiet when the thing it watches disappears is worse than no alarm, because it is believed.**
*(reasoned, not observed.)*

**One alarm is honest. Presenting one alarm as monitoring is not.** The honest list, worst first:

| Not watched | What it would catch |
|---|---|
| **Dead letter queue depth** | **a customer paid and their receipt never sent — they cannot enter the hall** |
| 5xx rate at the load balancer | the application failing while its task is still running |
| Target group unhealthy hosts | readiness failing on PostgreSQL or Redis |
| SES bounce and complaint rate | receipts going nowhere, including into spam folders |
| `outbox_pending` rising | the relay stuck, so receipts are never even enqueued |
| RDS free storage | forever retention filling the 20 GB volume |
| **S3 poster-bucket size and object count** | **the only store in the product with no deletion path at all.** A replaced poster is never deleted (`P-ADM-20`, `FR-ADR-012`), so the bucket only ever grows and nothing reads its size; the first symptom is a failed upload an admin meets mid-task |
| RDS connection count | pool exhaustion against roughly 110 connections |
| Host memory | a container killed for exceeding its limit, with no log explaining why |

**The worst one, named plainly: a customer whose receipt failed repeatedly has paid and cannot enter
the hall, and nobody will be told.** The message lands in the dead letter queue and today nothing looks
there. That is the product's central promise failing invisibly.

**A dead letter queue alarm is the single most valuable thing the client could add.** It is
**recommended in writing and it is not adopted.** One alarm was ruled; adding more is the client's
call, not a stricter version of theirs, and building six alarms nobody asked for would be writing Zone
C and inventing scope in one move. The recommendation sits in `docs/30 Deployment/` beside the ruled
alarm, marked clearly as a recommendation the client may decline. It pairs with `OPEN-EMAILFAIL-01`:
answering that row without adding this alarm would leave the ruled behaviour untriggerable.

**A running but broken application is invisible.** The task-count alarm fires when nothing is running.
It does not fire when everything is running and every request returns 500.

**`/metrics` exists and nothing scrapes it.** It is not an alerting mechanism and must not be counted
as one.

**There is one operator and no backup decider, stated affirmatively rather than left blank. There is
no escalation path and there cannot be.** If the alert email is not read, nothing else happens. That
is a property of the project and it belongs in the runbook, alongside this list as the things to check
by hand during an incident, since nothing will announce them.

---

### S7.15 — Recoverability

**Killing a container mid-request corrupts nothing.** The three mechanisms that make that true are
specified elsewhere and are named here because recoverability is where they add up:

- **The idempotency record is inserted first, inside the booking transaction, before any work.** A
  crash after the payment capture rolls the transaction back, and the retry with the same key finds
  the record and replays rather than capturing again. **No money is captured twice and no seat is
  booked without a capture.**
- **The receipt job is enqueued through a transactional outbox**, so a crash between commit and queue
  send leaves a `pending` row the worker's existing loop picks up. **Receipts are delayed, not lost.**
- **Redis locks expire on their own.** A crash strands nothing beyond the TTL.

**Backups.** RDS automated backups, enabled, retention **7 days**, which is the free-tier maximum
before backup storage exceeds the provisioned database size and starts to cost. Automated backups also
enable **point-in-time recovery**, which is the more useful capability: it recovers to any second
inside the window, not just to a nightly snapshot. **A manual snapshot is taken before every
migration**, and manual snapshots persist beyond the automated window.

**The backup window sits outside Friday and Saturday evenings**, because a `db.t3.micro` has no read
replica and backup work competes with live traffic on one small instance. *(reasoned, not observed.)*

**Redis is not backed up and does not need to be.** It holds locks and cache, both reconstructible or
expendable. Losing the node loses live holds and nothing else, which is already treated as a visible
partial outage by design. **S3 posters are not backed up either** — S3's own durability is the
mechanism, nothing deletes a poster, and a new poster is a new key.

**Forever retention and a 7-day backup window are different guarantees, and the difference matters:**
the data is kept forever, and it is **recoverable for seven days after a mistake.** A corruption
discovered in week three is not recoverable from an automated backup — only from a manual snapshot
that happened to be taken.

**A restore that has never been rehearsed is not a recovery.** The rehearsal is: restore to a new
instance, point a local application at it, and confirm a known booking is present and correct — by
reference, seats and price in paise. **Until that has been done once, this section describes a backup
and not a recovery.** It is a Phase 7 runbook deliverable with a recorded outcome and a recorded date,
held to the same standard as the red-proof drill: **an undated claim that it was performed is not
evidence.**

**Two things the Zone C specification must warn about, because both are common and both are silent:**

- **A restore creates a new RDS instance with a new endpoint. It does not restore in place.** The
  recovery procedure therefore includes a configuration change and a deploy.
- **Deleting an RDS instance deletes its automated backups** unless a final snapshot is taken. A
  cleanup that removes a database also removes the ability to recover it. *(reasoned, not observed.)*

**Enabling backups, setting the window and running a restore are all `aws` commands that create or
modify infrastructure, so all three are Zone C.** Needed by **Phase 2** — the first phase that creates
data worth losing.

---

### S7.16 — Zones and the AWS boundary

**Zone A — written completely.** Backend application code, routers, services, models, migrations; all
frontend code and styling; seat locking and booking logic; unit and integration tests; the seed
script; `docker-compose.yml` for local development only; the load-testing script. *(The movie sync job
that once sat in this list no longer exists, and nothing replaces it.)*

**`docker-compose.yml` is local development only and is never deployed, never the basis for a
deployment, and never a second deployment mechanism** (`SRC-002 §6.1.7`, `FR-ADR-066`). It runs
PostgreSQL, Redis and ElasticMQ alongside the API, worker and frontend. **Two things in it are
deliberately not automated**: migrations are a command the developer types, exactly as the client
will type it in AWS (`FR-ADR-062`), and the local database role is **not** a superuser, because RDS
never grants one and a migration that works only as superuser should fail on a laptop rather than
during a deploy. **The one deliberate divergence from the deployed shape** is the frontend, which
runs Vite's dev server locally and a static container when deployed; it is commented as such in the
file, because an undocumented difference between local and deployed is where "works on my machine"
comes from.

**Zone B — written, heavily commented, because the client must read and edit it.** Production
Dockerfiles, container entrypoint scripts, the health and readiness endpoints, environment
configuration and its validation, graceful shutdown. **Every line that exists for a production reason
carries a comment saying what breaks without it. A Zone B file with tidy code and no explanation has
failed its only purpose.**

**Zone C — not written at all.** Terraform and CloudFormation; ECS task and service definitions; load
balancer, target group, listener rule and security group configuration; VPC and subnet layout; GitHub
Actions and any CI/CD; CloudWatch alarms and dashboards; any `aws` command that creates
infrastructure.

**In place of each, `docs/30 Deployment/` receives a specification**: what to build, what the
application expects of it — ports, health check paths, environment variables, IAM permissions —
acceptance criteria, and two or three common mistakes. **Do not give the answer. Give the
specification and let the client fail against it.** A specification containing a working configuration
is a Zone C violation wearing a document's clothes, and a Zone C artefact marked "reference only" is
the answer with a disclaimer attached.

**The build session creates nothing in AWS.** Its grant is `describe`, `list` and `get`, scoped to the
development environment, so it can compare what the client built against the specification and
**report the difference — never repair it.** It creates, modifies and deletes nothing, at any
confidence, until the client says otherwise in writing; a message from another agent is not that
authorisation. **The account id and the region are not guessed** — they are read from the credentials
at first use and the finding is recorded.

**The standing consequence, stated every time it matters: this product has never been observed running
in AWS.** Every statement about how it behaves there is **reasoned, not observed**, and is labelled
that way. A read-only grant does not change that — describing a task definition is not the same as
watching the application serve a request. **There is also no CI/CD until the client builds it, so
there is no automated test gate on merge; every verification claim on this project is a local run and
is labelled as one.**

**The outbound list. There are six paths, and three of them are not the application's.**

| Destination | Which process | What breaks without it |
|---|---|---|
| **S3** | API | poster upload and the presigned redirect |
| **SQS** | API and worker | receipts are never enqueued or consumed |
| **SES** | worker | no receipt is ever sent — the customer cannot enter the hall |
| **SSM Parameter Store** | the container agent, at task start | **the task will not start** |
| **ECR** | the container agent, at task start | the image cannot be pulled |
| **CloudWatch Logs** | the log driver | logs are lost, including the crash that caused a restart |

**The agent-versus-application distinction is the most useful thing in the whole Zone C
specification**, and it goes in the common-mistakes section: SSM, ECR and CloudWatch Logs are needed
**before the application process exists**, so a security group permitting only what the application
needs produces **a task that never starts, with an error about pulling an image rather than about a
security group.**

There is **no NAT Gateway**, so the application runs in a public subnet with a public IP and strict
security groups. **Being in a public subnet is not the same as being publicly reachable** — inbound is
permitted only from the load balancer's security group, on the container port, and the security group
is the entire control. RDS and ElastiCache sit in the VPC, are not publicly accessible, and need no
egress rule because their traffic never leaves.

**Forbidden and not to be designed around:** EKS, Fargate, NAT Gateway, AWS Secrets Manager, Managed
Grafana, OpenSearch.

**The AWS dependencies this specification implies are listed in the lane return** so they can be added
to `docs/30 Deployment/AWS_PREP_QUEUE.md` with a needed-by phase. **This lane writes nothing to that
file.**

---

### S7.17 — Scope governance

**Reserved to the client, at any confidence:** money; anything irreversible or public; secrets; legal
and data-protection questions; amending the Constitution; what the product is and what "done" means;
scope changes; **waiving any quality check**; anything marked `[HUMAN]`.

**Adopting a stricter option is not a waiver and needs no signature.** Extending the rate limiter to
the credential endpoints, running as a non-root user, enforcing a read-only root filesystem, and
adopting an accessibility target nobody asked for are all stricter and all taken without asking.

**A reversible reserved matter is decided and then batched for the client to reverse.** The rounding
rule is the example: it is money, and it is reversible because the price is snapshotted onto every
booked seat, so changing the rule later reprices nothing already sold. **A reserved-and-irreversible
matter stops and waits, and no timeout defaults past it.**

**Four rows are open. Each is named, never filled in.**

| Row | Class | Status | What this lane may say | What it may not |
|---|---|---|---|---|
| `OPEN-TLS-01` | reserved: product | `DEFERRED` — the client is sourcing a domain | `COOKIE_SECURE` is environment-driven and off in the deployed environment; that environment is never called production and carries no real customer data | **that TLS is or will be terminated anywhere** |
| `OPEN-ATTRIB-01` | reserved: legal | open | demonstration content uses obvious placeholders and no image from anywhere; the redirect endpoint is where a provenance check would live if one were ever needed | **any real title, poster, brand or source** |
| `OPEN-SHOWCANCEL-01` | reserved: money, irreversible | open | **no withdraw-showtime capability exists in v1**, and why: an unbuilt capability is recoverable, an unrefunded customer is not | **any withdrawal endpoint, screen or refund behaviour** |
| `OPEN-EMAILFAIL-01` | reserved: product | open | the reference is on the confirmation screen and in the bookings list independently of the email; the receipt job records its attempts, its state and the provider's error | **any wording shown to a customer whose receipt definitively failed, and any policy about the money already taken** |

**Three rulings are `PROVISIONAL` and are flagged wherever they bite:** the four-role set, one cinema
with six screens, and the sales cut-off falling 15 minutes **after** the advertised start. **Three are
`ASSUMED`:** hall sizes, peak concurrency, and seat category names — the client said "you pick" on
those three and nothing else. **A `PROVISIONAL` reading and an `ASSUMED` choice never harden into a
requirement.**

**This project has already produced the failure that rule exists to prevent.** An assumption of seven
minutes inside a question became a specification in the next document without anyone deciding it, and
when it was finally put to the client it came back as three. **When a number appears in a
specification, find the ruling that produced it. If the only source is an assumption, it is `ASSUMED`,
not `RULED`.**

**Excluded is not blocked.** Nothing on the out-of-scope list may be made impossible. Three places
where that rule is already doing visible work: the `cinema` entity exists with one row; the booking
carries a `status` and a `cancelled_at` column that no v1 endpoint exposes; and the cinema filter's
code path and API parameter exist while the control is not rendered.

**An agent that hits an `OPEN` row and fills in something sensible has committed the cardinal failure
of this project.**

---

### S7.18 — The phase plan, and which rows land where

**Eight phases.** Nothing is built all at once, and a phase closes only when the client has been told
what to test and a short explanation file has been written covering what was built, why, and what
breaks in production if the deployment is got wrong.

| Phase | Scope |
|---|---|
| 1 | skeleton, configuration, health endpoints, structured logging, local compose stack |
| 2 | data model, migrations, seed data, admin CRUD for screens, showtimes and pricing |
| 3 | public browsing, listings, the seat-map read path, caching |
| 4 | seat locking, booking confirmation, idempotency, **the concurrency proof** |
| 5 | SQS worker, the receipt email, dead letter handling |
| 6 | **admin movie management** *(replaced the withdrawn TMDB sync)* |
| 7 | metrics, rate limiting, the load test, the runbook |
| 8 | **the manager and admin dashboard** *(new)* |

**The convention, stated so the merge pass can apply it to every other lane's rows:**

> **A P-row lands in the earliest phase at whose close its behaviour must be observable by the
> client**, per `SRC-002 §12` as revised by `SRC-002 §E E-3`. Where a row is a **floor** over code
> that later phases write, it lands in the phase that first writes code subject to it and **is
> re-checked at the close of every later phase.** Where a row's **mechanism** and its **proof** fall in
> different phases, the row's phase is the mechanism's, and the proof is named separately. A row that
> depends on an earlier phase's deliverable names that dependency rather than moving phase.

**This lane's rows:**

| Phase | Rows | Notes |
|---|---|---|
| **1** | `P-XCT-10` `P-XCT-11` `P-XCT-12` `P-XCT-14` `P-XCT-15` `P-XCT-16` `P-XCT-17` `P-XCT-18` `P-XCT-21` `P-XCT-22` `P-XCT-23` `P-XCT-26` `P-XCT-27` `P-XCT-28` `P-XCT-29` `P-XCT-31` | The floors that must exist before anything else is written. `P-XCT-17`'s lock release has nothing to release until Phase 4; the drain and the signal handling are Phase 1. `P-XCT-21`'s **measurement** is a Phase 1 deliverable, not just a deployment. |
| **2** | `P-XCT-02` `P-XCT-03` `P-XCT-05` `P-XCT-06` `P-XCT-19` `P-XCT-30` `P-XCT-32` | `P-XCT-01`'s unique constraint is created in **this phase's migration**, before any code can write a booking, so no window exists in which bookings are written without it. `P-XCT-20`'s backups are needed by this phase. **`P-XCT-32` ships with the seed and is a hard dependency of Phase 4**: without it the seeded accounts cannot sign in and the concurrency proof has nobody to run as. |
| **3** | `P-XCT-08` `P-XCT-09` `P-XCT-24` `P-XCT-25` | `P-XCT-09`'s cache half lands here; its lock half is re-checked at Phase 4. **ElastiCache Redis is therefore needed by *Phase 3*, not Phase 4** — see the note below. |
| **4** | `P-XCT-01` `P-XCT-04` | The concurrency proof and the red-proof drill. Depends on Phase 2's seed script for fifty authenticated customers. |
| **7** | `P-XCT-07` `P-XCT-13` `P-XCT-20` | Rate limiting and metrics are Phase 7 by the mandate. `P-XCT-20`'s **restore rehearsal** is a Phase 7 runbook deliverable even though the backups themselves are needed by Phase 2. |
| **every phase** | `P-XCT-27` | The phase plan governs itself and closes each phase. |

**Redis is a Phase 3 dependency and the prep queue announces it for Phase 4, which is one phase
late.** Phase 3 is browsing and the seat-map read path. **The seat-map read is rate-limited**
(`FR-ADR-058`, `RATE_LIMIT_SEATMAP_IP_PER_MIN`) **and the limiter runs before the cache and fails
closed**, so with no Redis that read returns `503` and **Phase 3's own acceptance cannot be
demonstrated in AWS at all** — not slower, not degraded: unavailable. `P-XCT-09` is the row that
settles that, and it lands in this phase. The cache half needs Redis in this phase too; only the lock
half waits for Phase 4.

**`docs/30 Deployment/AWS_PREP_QUEUE.md` row 8 carries a needed-by of Phase 4 and must read Phase 3.**
**This lane writes nothing to that file** (`S7.16`, `P-XCT-26`) and names the correction in its return
instead. The obligation this discharges is the one the zone split rests on: **a dependency announced
on the day it blocks has broken the exchange** (`P-XCT-26` exception 3), and announcing it a phase
late is the same failure arriving on time.

**One sequencing consequence worth naming rather than absorbing.** The concurrency proof is Phase 4
and rate limiting is Phase 7, so **the Phase 4 run happens before the limiter exists.** The proof
asserts that the limiter is not disabled for the run, which at Phase 4 is trivially true and at Phase 7
is a real constraint. **The proof is therefore re-run at the close of Phase 7, against the limiter**,
and the Phase 4 result is not treated as covering the Phase 7 configuration.

---

### S7.19 — Dates and times: one rendering rule, owned here

**This section owns the format of every date and time a human reads in this product.** No screen, no
message, no email and no P-row may invent another one, and a surface that needs a format cites this
section rather than choosing.

**It is a `[JUDGMENT CALL]`, the build session's under Art III.9, and the fact that it had to be made
is the point.** **No frozen source and no `APPROVED` record specifies a date or time format
anywhere.** `SRC-003 OPEN-LOCALE-01` rules the **zone** — Asia/Kolkata — and `FR-ADR-018` rules the
**storage and the wire** — `timestamptz` in UTC, ISO-8601 with the `+05:30` offset on the wire. Both
stop short of what a customer reads. Before this section existed the document carried at least six
conventions for one product: `7:30 PM`, `7:45 pm`, `19:15`, `20 August 2026 at 14:00`,
`12 Aug 2026, 15:40` and `Fri 15 Aug` — **and several surfaces rendered a time with no example at
all**, which is a guess the implementer would have had to make alone.

#### The five forms, and nothing else

| Form | Pattern | Example | Where it is used |
|---|---|---|---|
| **time** | `h:mm am/pm`, lowercase, one space before the meridiem, no leading zero on the hour | `7:30 pm`, `9:05 am`, `12:00 pm` | a showtime on a button, a sales cut-off in a message, any bare clock time |
| **date** | `D MMM YYYY` — day, three-letter month, four-digit year, no ordinal suffix and no comma | `15 Aug 2026` | a booking date, a display window, any date standing alone |
| **date with time** | the date form, a comma, a space, the time form | `15 Aug 2026, 7:30 pm` | a receipt, a booking record, an audit entry, anywhere the day is not already obvious from context |
| **short date** | `D MMM` — the date form with the year dropped | `15 Aug` | inside a set already scoped to one year: a date strip, a list of this month's showtimes |
| **weekday with short date** | `Ddd D MMM` — three-letter weekday, then the short date | `Fri 15 Aug` | a date strip, a next-available-date control, anywhere the *day of the week* is what the customer is choosing on |

**The year is dropped only where it cannot be ambiguous**, and never on a receipt or a booking record —
those are read months later and out of context.

#### The rules that go with them

1. **Everything renders in Asia/Kolkata**, from `CINEMA_TIMEZONE`, against the injected clock — never
   the container's, which in AWS is UTC and rolls the date over at 05:30 local (`FR-ADR-018`).
2. **The zone is not printed** next to an ordinary time. There is one cinema in one zone and every
   reader is in it. **It is printed exactly where a reader may be elsewhere**: on the emailed receipt,
   which is read outside the site, as `(Asia/Kolkata)` after the date-with-time.
3. **A 24-hour clock never reaches a customer.** `19:15` is a correct instant and a wrong rendering.
   24-hour times survive only in **worked examples, log lines, ISO-8601 wire values and audit
   payloads**, which are read by an operator and not by a customer — and this section governs what a
   human *customer* reads, not what a developer reads in a code block.
4. **Every number a customer reads is `--fr-font-mono` with `font-variant-numeric: tabular-nums`**
   (`COMPONENTS.md §0.3`), which includes every one of the five forms above. Tabular figures stop a
   column of showtimes from jittering as the digits change width; the month name and the weekday are
   prose and stay in `--fr-font-body`, so a rendered date is two voices in one string and that is
   deliberate.
5. **The formatting is one function**, taking an instant and a form, in one module. A second
   implementation is a second convention arriving quietly, which is what produced six.
6. **A surface may not invent a format.** If a surface needs something none of the five forms covers,
   that is a gap in this section and it is fixed here — **never locally**. **One class sits outside
   the five rather than missing from them, and this rule must be read with it**: a **prose naming of a
   period** — `August 2026`, a week expressed as a range, `Friday 14 August 2026` — **is not a rendered
   instant and is not governed by this section at all.** See *One thing this section deliberately does
   not cover*, below, which draws that boundary and names the three strings it releases. **Reading
   this rule without it is the trap:** `SCR-RPT-01`'s month tab needs a month-only string and its week
   view needs a range, neither of which is one of the five — and the answer is that neither is this
   section's to give, **not** that a sixth form is owed. **A gap in the five is fixed here; a string
   that is not an instant was never in the five to begin with.**
7. **A relative *instant* is never rendered** — no "2 days ago", no "yesterday", no "in three weeks".
   An instant is rendered as one of the five forms above and nothing else. **A duration is a different
   thing and this section does not own it.** A wait a customer is told to observe — the `Retry-After`
   sentence, a resend interval — is rendered by **S7.20**, which owns the threshold, the rounding and
   the pluralisation, so that this section's silence about spans is a pointer rather than a gap. The
   hold countdown is neither: it is a live `m:ss` timer rather than a rendered value, and it is
   `SCR-SEA-02`'s.

#### The existing verbatim examples, checked against this rule

**Stated rather than claimed, and the ones that would have to change are named.**

| Example, as written in this document | Verdict |
|---|---|
| `7:45 pm` — every `SALES_CLOSED` message (`P-HLD-14`) | **conformant.** This section adopted that lane's judgment call verbatim rather than overriding it, so no copy changed |
| `Fri 15 Aug` — the next-date control (`SCR-BRW-02`) | **conformant** — the weekday-with-short-date form |
| `7:30 PM` — two showtime accessible names (`SCR-BRW-02`) | **changed to `7:30 pm`.** Case only; the same instant, the same pattern |
| `19:15` in `P-BRW-07` and `P-HLD-06` | **conformant as they stand** — both are inside worked examples alongside ISO-8601 instants, which rule 3 exempts. Neither is a string a customer reads |
| `20 August 2026 at 14:00` — a bookings-list accessible name (`SCR-ACC-04`, lane E5) | **corrected by that lane, and verified in its file.** It now reads `20 Aug 2026, 2:00 pm` — the date-with-time form, keeping the year because a bookings list is read months later out of context. It was wrong on two counts: the month spelled in full, and a 24-hour time |
| `21 August 2026, 19:15` — the receipt (lane E4, `P-TKT` rows and `SCR-TKT-02`) | **corrected by that lane, and verified in its file.** It now reads `21 Aug 2026, 7:15 pm (Asia/Kolkata)` — the same two counts, plus rule 2's zone suffix, which the receipt is the one surface that carries because it is read away from the site |
| `12 Aug 2026, 15:40` — the audit entry's rendered `occurred_at` (lane E7) | **still standing as this pass closes, and it is E7's to change** to `12 Aug 2026, 3:40 pm`. The date half is already conformant; the time half is 24-hour, and this one is read by an admin **in the interface**, which makes it a reader-facing surface under rule 3 rather than a log line. It is the last of the four |
| `Fri 14 Aug 19:30` and `Fri 19:30` — the "Local (Asia/Kolkata)" column in `P-RPT`'s worked examples (lane E7) | **decided here, and the decision is below.** A dashboard row that renders one showtime's instant uses the **date-with-time** form on a view spanning more than one day and the **time-only** form on a single-day view. So `Fri 14 Aug 19:30` becomes `14 Aug 2026, 7:30 pm` and `Fri 19:30` becomes `7:30 pm`. Where the column sits inside a worked example beside its own ISO instant it is exempt under rule 3, exactly as `P-BRW-07`'s `19:15` is |

#### The dashboard's per-show rows — decided here, not handed back

**A previous revision of this section said the dashboard's format "belongs to that lane, and this
section does not decide it for them", and proposed `Fri 14 Aug, 7:30 pm` — which is not one of the
five forms.** Both were wrong, and wrong in the same way: **a section that declares itself the owner
of a rule does not get to hand one case back**, and rule 6 says in terms that a gap is fixed here and
never locally. Proposing a sixth form in the act of deferring made it worse, because it left another
lane holding a format this section had invented and not adopted. **The proposed weekday-with-time form
is withdrawn and no sixth form exists.**

**The decision, which needs nothing new:**

| The view | Form | Example |
|---|---|---|
| spans **more than one day** — a week, a month, any range | **date with time** | `14 Aug 2026, 7:30 pm` |
| is a **single day** — the day is already named in the period heading above the table | **time only** | `7:30 pm` |

That is exactly this section's existing test — *anywhere the day is not already obvious from context*
— applied to a table rather than to a sentence, and it needs no new form because the five already
cover it. **The weekday is dropped in both**: on a single-day view it is in the heading, and on a
multi-day view the date carries it for any reader who needs it. **The year is kept on the multi-day
form**, because a dashboard row is read months later out of context, which is the same reason a
receipt keeps it.

#### Four more this audit reached over — and why that is the more important finding

**This table was published as an audit. It walked eight examples, corrected four, and passed over
four others that are wrong for the same reasons it was applying** — while, in the row above, flagging
a *sibling* case for exactly the reason that condemns them. **An audit that misses is worse than no
audit**, because the next reader trusts the table instead of looking, which is what happened.

| Example, and where | Verdict |
|---|---|
| `4 September` — `P-ADM-08` exceptions 1 and 2 (lane E6) | **non-conformant.** The month is spelled in full and none of the five forms is `D MMMM`. It becomes `4 Sep 2026` — the **date** form, with the year, because a publication error is read out of context |
| the overlap error's instants — `SCR-ADM-03` (lane E6) | **non-conformant** wherever it renders a 24-hour clock. It takes the **date-with-time** form, `14 Aug 2026, 7:30 pm` |
| `Counted at 14:30 on 14 Aug 2026 (India time)` — `SCR-ADM-04` (lane E6) | **non-conformant on three counts.** A 24-hour clock (rule 3); the zone printed, which rule 2 restricts to the emailed receipt; and `(India time)`, which is not `(Asia/Kolkata)` and is not a form at all. It becomes `Counted at 14 Aug 2026, 2:30 pm` |
| `shown until 2 October at 00:00` — `SCR-ADM-02` (lane E6) | **non-conformant.** Month in full, 24-hour clock, and ` at ` as a separator where the date-with-time form uses a comma. It becomes `shown until 2 Oct 2026, 12:00 am` |

**All four are lane E6's and are named here, not edited.** E6 is correcting the strings; what this
section owed was to stop claiming a completeness it did not have.

**The count, restated honestly.** This audit now covers **twelve** examples, not eight. Of them:
**four were corrected in earlier waves** — `SCR-BRW-02`'s `7:30 PM` here, `SCR-ACC-04`'s and the
receipt's by lanes E5 and E4, both verified in their files; **five are still standing** — the four
above plus the dashboard's `occurred_at`, all in lanes E6 and E7; and **three were conformant as
written.** **Naming a defect and leaving it standing is a defect twice**, so this table records
outcomes rather than repeating requests, and a row stops saying "would have to change" the moment the
owning file says otherwise.

**And the lesson this table now carries about itself:** it was assembled by reading the document for
date-shaped strings, which finds the ones a reader happens to look at. **It is not a substitute for a
lane walking its own file**, and every lane sweeps its own date strings against the five forms rather
than checking whether this table names them.

#### One thing this section deliberately does not cover

**A prose naming of a period is not one of the five forms and is not governed here** — **in a heading,
in a period line, in a control's visible label, or in a control's accessible name.** The class is
stated rather than the one site, because `SCR-RPT-01` names its period in more than one place: the
period line, and the period stepper's accessible name, which `SCR-RPT-01` requires to name the period
type. All of them are the same kind of string and all of them are outside the five.

The dashboard's period line reads `Friday 14 August 2026`, `Monday 10 August to Sunday 16 August 2026`
and `August 2026` (lane E7) — a full weekday, a full month name, and a range expressed in words.
**Those are a sentence naming a span rather than a rendered instant**, they have no equivalent among
the five, and inventing a sixth form here purely to bless them would be this section deciding another
lane's copy from a distance. **They stay `P-RPT`'s, and all three are discharged: `SCR-RPT-01` owes
this section nothing for them and is not in breach of rule 6 by publishing them.**

The boundary is stated so that neither side reads the silence as coverage: **anything that renders one
instant** — a showtime, a cut-off, an `occurred_at`, a booking's date — **is this section's; a string
that names a span in prose is not.** The test is mechanical: *does the string denote a single point in
time?* `14 Aug 2026, 7:30 pm` does and is governed; `August 2026` does not and is not.

**One consequence, so the release is not read as an absence of rules.** A period string that is
released here is still `P-RPT`'s to publish and to keep consistent, and `S7.21` still binds any number
inside it that comes from configuration. **Released from this section is not released from the
document.**

---

### S7.20 — Durations: one rendering rule for every wait a customer is told to observe

**This section owns how an integer number of seconds becomes the words a customer reads, and how that
integer is computed.** `S7.19` owns instants and says so; this owns spans. No screen, no message and
no P-row may pick its own threshold, its own rounding, its own plural or its own arithmetic, and a
surface that needs a span cites this section rather than choosing.

**Ownership is declared here, in the same form `S7.19` declares it.** `S1.2`'s list of sections that
own a rule outright names `S7.19` and, at the time this section was written, not `S7.20` — so on a
literal reading a P-row would outrank the section every other lane has been corrected against. **The
merge owner adds `S7.20` to that list; `S1_reading_rules.md` is not edited from here.** Until it does,
this declaration is the thing that closes the gap, and it is stated rather than assumed because an
unstated ownership is exactly what `S1.2.1` says must be declared by one side.

**Why it exists.** The `Retry-After` header is computed from a bucket's refill rate and is always an
integer number of seconds, and the sentence beside it is computed from the same integer — yet the
published verbatim strings across this document could not all have come from one function: `3
seconds`, `30 seconds`, `45 seconds`, `90 seconds`, `900 seconds`, `4 minutes` (240 s) and `12
minutes` (720 s). **240 and 720 became minutes while 900 stayed seconds.** No threshold, no rounding
and no pluralisation rule existed anywhere, and these are rank-2 published copy under `S1.2`, so an
engineer implementing the limiter could not pick one without overriding somebody's row. **It is a
`[JUDGMENT CALL]`, the build session's under Art III.9** — no frozen source and no `APPROVED` record
specifies a duration format.

#### The rule

```
The Retry-After header is always an integer number of seconds. It is never rendered.
The sentence renders that integer as:

   seconds < 120   ->  "<n> seconds"                 n = the integer itself
   seconds >= 120  ->  "<m> minutes"                 m = ceil(seconds / 60)

   n == 1 -> "1 second"   m == 1 -> "1 minute"       (m == 1 is unreachable: >= 120 gives m >= 2)
```

1. **The header is the machine's value and the sentence is the human's.** They are the same instant of
   truth and two renderings of it; the header is never rewritten to match the sentence, because a
   client reads the header to time its retry.
2. **`ceil`, never `round` and never truncation.** A rounded-down wait tells the customer to retry
   before the bucket has a token, which produces a second 429 and a customer who was told the wrong
   thing. Rounding up is the only direction that cannot do that.
3. **The threshold is 120, not 60.** At 60 a 90-second wait would read "2 minutes" — an overstatement
   of a third, on the one number the customer is being asked to trust. At 120 the shortest string the
   minutes branch can produce is "2 minutes" for a true 120 seconds, which overstates nothing.
   **The threshold is stated because an unstated one is how the next string drifts.**
4. **Both singular forms are specified, and one of them is reachable.** An implementer who finds no
   rule writes `"{n} seconds"` and ships "1 seconds". `n == 1` occurs for **four real buckets** in the
   derivation table below, which names them — so "1 second" is copy that ships, not a defensive
   branch. `m == 1` is unreachable by construction, and saying so is cheaper than a reader deriving it
   twice.
5. **The number is `--fr-font-mono` with `font-variant-numeric: tabular-nums`** (`COMPONENTS.md §0.3`),
   the same treatment `S7.19` rule 4 gives every number a customer reads; the unit word is prose.
6. **The number is never typed into the copy.** Every published string in this document that carries a
   wait shows one worked value; the shipped string substitutes the computed one.

#### Worked examples — these are the real published strings

```
   1 s -> "Try again in 1 second."             3 s -> "Try again in 3 seconds."
  45 s -> "Try again in 45 seconds."          90 s -> "Try again in 90 seconds."
 119 s -> "Try again in 119 seconds."        120 s -> ceil(2.0)  = 2  -> "2 minutes"
 240 s -> ceil(4.0)  = 4  -> "4 minutes"     720 s -> ceil(12.0) = 12 -> "12 minutes"
 900 s -> ceil(15.0) = 15 -> "15 minutes"
```

**Two of those are rendering examples and not published strings, and the distinction matters enough to
state.** The rendering rule is total — it must answer for any non-negative integer — so `45` and `900`
are exercised here to show the function's behaviour either side of the threshold. **Neither is a wait
any bucket in this product actually produces**: the derivation table below gives every real figure,
and `45` and `900` are not among them. **A string published with either number is a defect in the
number, not in the rendering** — which is precisely the mistake this section found in four places,
including two of its own.

#### What this rule does not cover

**A message that carries no number is not a duration rendering and is not governed here.** "Try again
in a few minutes" — the 503 `DEPENDENCY_UNAVAILABLE` copy in `P-XCT-07`, `P-XCT-08`, `P-XCT-09` and
`SCR-XCT-01` — is deliberate: a dependency outage has no computed retry instant, so there is no
integer to render and inventing one would state a recovery time nobody knows. **The boundary is
stated so neither side reads the silence as coverage:** where a `Retry-After` integer exists, this
rule renders it; where none exists, the copy says so in words and names no figure.

**The hold countdown is not a duration rendering either.** It is a live `m:ss` timer, owned by
`SCR-SEA-02`, and `S7.19` rule 7 already carves it out.

#### Where the number comes from — the maximum for every bucket in the product

**The rendering rule above is only half of it.** A string can render correctly and still state the
wrong wait, and that is the commoner defect: the wait is **not** the bucket's window, it is time until
the bucket next holds a token, and the two differ by the capacity. A limit of "30 per 15 minutes"
refills a token every **30 seconds**, not every 900. **`900` is how long the window is; nobody ever
waits it.** Publishing the window is the first mistake this table exists to prevent, and it had
already been made twice in this section before this pass.

**`Retry-After` is computed from the bucket's state at the moment of refusal, and it is not a constant
per bucket.**

```
Retry-After = ceil(seconds until this bucket next holds one token)
```

**This corrects what this section said in its previous revision**, which gave one constant per bucket
and was wrong. A refilling token bucket earns its next token at a moment fixed by **the last refill**,
not by when the caller happens to ask, so a constant is correct only at the instant the bucket empties
and **every later retry is told to wait longer than it must.** `P-ACC-14`'s worked example had it
right and this section had it wrong; the section is what changed.

**The table below is therefore the maximum, not the value.** It is `ceil(window / capacity)` — the
figure at the instant the bucket empties, which is the largest `Retry-After` that bucket can ever
produce — and it is the figure every published example string shows, because an example is written at
the worst case. **No published string changes**: rule 6 already requires the number to be computed and
never typed, and a computed number was always going to be this value or smaller.

```
the maximum, and the figure tabulated below:
    ceil(window_seconds / capacity) = ceil(1 / refill_rate)
```

**Every limited bucket in the product, with its arithmetic and the string it produces at the
maximum.** Capacities are the S7.9 defaults and are **estimates, not measurements** — Phase 7's load
test replaces them, and when it does, **every string in this column changes with them**, which is a
second reason no lane may type one.

| Bucket | Variable | Capacity | Window | Refill (tokens/s) | `Retry-After` **max** | Rendered **at the max** |
|---|---|---|---|---|---|---|
| seat hold, per user | `RATE_LIMIT_HOLD_USER_PER_MIN` | 20 | 60 s | 0.3333 | `ceil(60/20)` = **3** | "3 seconds" |
| seat hold, per IP | `RATE_LIMIT_HOLD_IP_PER_MIN` | 60 | 60 s | 1.0 | `ceil(60/60)` = **1** | "1 second" |
| booking confirm, per user | `RATE_LIMIT_CONFIRM_USER_PER_MIN` | 10 | 60 s | 0.1667 | `ceil(60/10)` = **6** | "6 seconds" |
| booking confirm, per IP | `RATE_LIMIT_CONFIRM_IP_PER_MIN` | 30 | 60 s | 0.5 | `ceil(60/30)` = **2** | "2 seconds" |
| sign-in, per user | `RATE_LIMIT_LOGIN_USER_PER_15MIN` | 10 | 900 s | 0.0111 | `ceil(900/10)` = **90** | "90 seconds" |
| sign-in, per IP | `RATE_LIMIT_LOGIN_IP_PER_15MIN` | 30 | 900 s | 0.0333 | `ceil(900/30)` = **30** | "30 seconds" |
| registration, per IP | `RATE_LIMIT_REGISTER_IP_PER_HOUR` | 5 | 3600 s | 0.0014 | `ceil(3600/5)` = **720** | "12 minutes" |
| password-reset request, per IP | `RATE_LIMIT_RESET_IP_PER_HOUR` | 5 | 3600 s | 0.0014 | `ceil(3600/5)` = **720** | "12 minutes" |
| password-reset **confirm**, per IP | `RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR` | 10 | 3600 s | 0.0028 | `ceil(3600/10)` = **360** | "6 minutes" |
| booking lookup by reference, per user | `RATE_LIMIT_LOOKUP_USER_PER_MIN` | 20 | 60 s | 0.3333 | `ceil(60/20)` = **3** | "3 seconds" |
| booking lookup by reference, per IP | `RATE_LIMIT_LOOKUP_IP_PER_MIN` | 60 | 60 s | 1.0 | `ceil(60/60)` = **1** | "1 second" |
| seat-map read, per IP | `RATE_LIMIT_SEATMAP_IP_PER_MIN` | 120 | 60 s | 2.0 | `ceil(60/120)` = `ceil(0.5)` = **1** | "1 second" |
| reports and change log, per user | `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` | 60 | 60 s | 1.0 | `ceil(60/60)` = **1** | "1 second" |
| receipt resend, per booking | `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` | **an interval, not a bucket** | 300 s | — | `300 − elapsed`; at 60 s elapsed, **240** | "4 minutes" |

#### The rule this table exists to enforce — binding on every lane

**Five strings in four lanes have now been corrected for one defect, and it is one defect and not
five.** In every case **a number that belongs to the bucket was written into copy that wanted the
bucket's refill interval.** Stated in the imperative, because a description of five past mistakes
binds nobody:

1. **Name the bucket beside the string.** Every published wait names the bucket it came from, by its
   `RATE_LIMIT_*` variable. A sentence with a number and no bucket cannot be checked by anyone.
2. **Derive the figure. Never choose it.** The published figure is that bucket's maximum,
   `ceil(window_seconds / capacity)`, and **the division is shown** where the string is published.
3. **A wait that cannot be traced to a row in the table above is a defect** — not a rounding
   difference and not a house-style choice. The number is wrong.
4. **Never publish the capacity and never publish the window.** Both are real numbers belonging to
   that bucket, both are near at hand when someone is writing the sentence, and **both are the wrong
   number.** Four of the five corrections were a capacity; the fifth was a window.
5. **The rendered number is computed at the moment of refusal** and is at most the published figure.
   Rule 6 above forbids typing it, and the worked example below shows why the published figure is the
   ceiling rather than the value.

**The sentence that matters most here is about checking, not about copy.** *Every one of the five
passed a rendering check.* They were correctly formatted — real integers, the right unit word, the
right threshold, the right plural — **and wrong about the number.** `20 seconds`, `30 seconds`,
`45 seconds` and `900 seconds` are all impeccably rendered spans that no bucket in this product can
produce. **A check that validates only the format is exactly what let all five through**, and it is
the check a reviewer builds first because it is the easy one. **The format is the cheap half. The
derivation is the half that is wrong in practice**, and a review that stops at the first has confirmed
nothing worth confirming.

#### Worked example — two retries against one bucket, and the value falling

The sign-in per-user bucket: capacity 10 over 900 s, refill `10 / 900 = 0.0111` tokens per second, one
token every 90 s. A customer empties it at `t = 0`.

```
t =   0   the tenth attempt empties the bucket
          next token at t = 90
          Retry-After = ceil(90 - 0)  = 90   ->  "Try again in 90 seconds."     <- the maximum

t =  30   the same customer retries. Still empty; the refill moment has not moved
          Retry-After = ceil(90 - 30) = 60   ->  "Try again in 60 seconds."

t =  89   retries again
          Retry-After = ceil(90 - 89) =  1   ->  "Try again in 1 second."       <- singular, shipped

t =  90   a token exists. The request proceeds; there is no 429 and no sentence
```

**A constant would have said 90 at every one of those instants**, which is right once and wrong twice,
and wrong by a minute at `t = 30`. **The table's 90 is the first line of this example and nothing
else.**

Two consequences worth stating because they are observable:

- **`n == 1` is reachable on every bucket, not only the four whose maximum is 1.** Any bucket produces
  a 1 for a caller who retries in the last second before its refill. The four named below are the ones
  whose **maximum** is 1 — the only ones where 1 is also the published example — but the singular is
  copy that ships on every limited endpoint in the product, which strengthens rule 4 rather than
  weakening it.
- **The countdown on `SCR-XCT-03` starts from the value it was given** and is not re-derived by the
  client. A second request during the wait returns a smaller number, and the banner takes the new one.

**Three things the table settles that the rule alone does not.**

- **Where two buckets guard one endpoint, the header carries the one that refused**, so sign-in has
  two legitimate figures — 90 and 30 — and a row that publishes only one must say which bucket it is
  showing. `P-XCT-06` rows 7 and 8 now do. **A row that derives only the narrower bucket is
  incomplete**, because the wider one refuses first for a caller sharing an address.
- **Four buckets have a *maximum* of `Retry-After: 1`**, so 1 is their published example as well as
  their worst case: **seat hold per IP** (60/60 s), **booking lookup by reference per IP** (60/60 s),
  **seat-map read per IP** (120/60 s, `ceil(0.5) = 1`) and **reports and change log per user**
  (60/60 s). Those four are where an implementer meets the singular first, because it is the figure
  their example strings carry. **It is not the complete set of places the singular ships** — the
  worked example above shows any bucket producing a 1 for a caller who retries just before its refill
  — so `"{n} seconds"` written unconditionally ships `"1 seconds"` on **every** limited endpoint, not
  only these four.
- **The per-booking resend row is the only entry that is not a refill**, so its figure moves with the
  elapsed time rather than being fixed. It is in this table because a reader looking for "where does
  my number come from" must find every case here or the table is worse than none.

#### The strings in this section, checked against both halves of the rule

| String, as written in this document | Verdict |
|---|---|
| `"Too many requests. Try again in 3 seconds."` — `P-XCT-07` exception 1, `SCR-XCT-03` | **conformant** on both counts: the seat-hold per-user bucket gives 3, and 3 < 120 |
| `"Too many attempts. Try again in 900 seconds."` — formerly `P-XCT-06` exception 7 and `SCR-XCT-03` | **wrong twice, and changed here.** `900` was the sign-in window rather than its refill interval — the per-IP bucket gives **30** — and `900 seconds` also violated the rendering threshold. `P-XCT-06` now carries rows 7, 8 and 9 with 30 s, 90 s and 720 s and names the bucket behind each; `SCR-XCT-03` carries the same three figures |
| `"in 4 minutes"` — the receipt-resend wait, S7.4 and `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` in S7.9 | **conformant.** 240 >= 120, `ceil(4.0) = 4` |
| `Retry-After: 3` and `Retry-After: 30` — S7.4's and `P-XCT-07`'s arithmetic blocks | **conformant, and not copy.** These are header values, which rule 1 says are never rendered |

#### The strings in other lanes this table found, and what became of them

**One defect class, five instances across four lanes and this one, and the class is stated as a rule
above rather than left to be inferred from the list.** In each, **a number belonging to the bucket was
written into copy that wanted the bucket's refill interval.** Each rendered correctly and stated a
wait the arithmetic does not produce, so the defect was the number and not the words. **Each was
corrected by the lane that owns the copy, not from here** — what follows records outcomes, all of them
verified in the files rather than assumed.

| String, and where | What the arithmetic gives | Outcome, verified in the file |
|---|---|---|
| `"Try again in 20 seconds."` — lane E2's hold-limit copy, published twice | **3** per user, **1** per IP | **corrected.** E2 now publishes `3 seconds` and `1 second`, cites this section, and records that `20` was the bucket's *capacity* copied into the string. It had already been publishing the correct `3` elsewhere in the same file |
| `"Try again in 30 seconds."` — lane E3's confirm-limit copy | **6** per user, **2** per IP | **corrected.** E3 now publishes `6 seconds`, with `2 seconds` for the per-IP bucket and the arithmetic beside it |
| `"Try again in 45 seconds."` — lane E4's booking-lookup copy | **3** per user, **1** per IP | **corrected.** E4 now publishes `3 seconds` and `1 second`, names both buckets by variable, and marks the singular as shipped copy |
| `"Too many requests. Try again in 30 seconds."` — lane E7's dashboard and change-log copy, in **three** places | `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` = 60 over 60 s → **1** | **corrected.** E7 now publishes `"Too many requests. Try again in 1 second."` in all three, shows the division once in `P-RPT-12` and points the other two at it. **This section named three wrong strings and missed this one** — and missed it behind a bucket this very table names as one whose maximum is 1. **A rule checked by hand finds what the checker looked at**, which is the argument for the table rather than against it, and the reason the rule above is written in the imperative |
| `"900 seconds"` — **this section's own**, `P-XCT-06` and `SCR-XCT-03` | the sign-in per-IP bucket gives **30** | **corrected**, and listed here rather than only in the section-local table above, because a class with one instance quietly left out of the list is not a class. `900` was the bucket's **window** — the only one of the five that was not a capacity |
| `"Try again in 90 seconds."`, `"Try again in 30 seconds."`, `"Try again in 12 minutes."` — lane E5's sign-in, registration and reset copy | 90, 30 and 720 | **were already right on both counts**, and are the worked proof that the arithmetic and the published copy can agree |

**Two `"30 seconds"` strings still appear in `E7_dashboard.md` and both are correct.** They sit inside
that lane's own record of the correction — the sentence saying what the string used to say and why
thirty was neither the capacity, the window nor the refill interval. **A grep for the wrong figure
hits them, and they are not defects**; this is noted so the next reviewer does not "fix" a lane's
account of a fix. The same is true of `"900 seconds"` in the table above this one.

**Every lane checks its own strings against this table and changes only the copy its own rows
publish.** Nothing above was edited from this section.

---

### S7.21 — A number in customer copy that is configuration is rendered, never typed

**This section owns the rule, and it binds every lane.** `S7.19` owns instants, `S7.20` owns spans,
and this owns the general case both are instances of. **Ownership is declared here in the same form**,
and the merge owner adds it to `S1.2`'s list alongside `S7.19` and `S7.20`; `S1_reading_rules.md` is
not edited from here.

> **Any customer-facing string that quotes a number which is a configuration value renders that
> configuration value at the moment the string is produced. A literal in its place is a defect.**

**Why it needed saying, when the document already says it in three places.** `P-ACC-07` rules it for
the reset window — *a literal `30` in any of those places is a defect* — `S7.20` rule 6 rules it for
every rate-limit wait, and `SCR-ADM-04` rules it for its own figure. **Three rows independently
deciding the same thing is not a rule; it is three rows that happened to think of it**, and the
strings nobody thought of are the ones that break. Two were sitting in the document unmarked:
`Up to 10 seats.` and `at least 12 characters`.

**The failure, worked, because it is not hypothetical.** `MAX_SEATS_PER_BOOKING` defaults to `10`, and
S7.9's boot check **explicitly permits a lower value** — above 10 contradicts a ruling and is refused,
below 10 is stricter and is allowed. So:

```
MAX_SEATS_PER_BOOKING = 6          a permitted, deliberate, stricter setting
customer reads .................... "Up to 10 seats."     <- a literal
customer selects .................. 7 seats
server enforces ................... 6
customer is refused ............... having been told by this product that 7 was allowed
```

**The product told the customer a limit it does not enforce, and then refused them for believing
it.** No test catches it, because at the default the literal and the value agree — **the string is
correct at the default and wrong at every other setting**, which is the shape of defect that survives
a whole test suite.

**The consequence for what is already published: nothing changes.** Every published string in this
document is the rendering **at the default**, and stays exactly as written. What changes is that each
one is **marked with the configuration name it interpolates**, so the next reader sees a template and
not a sentence.

| String, as published | Renders | Owner |
|---|---|---|
| `Up to 10 seats.` and the seat-cap messages | `MAX_SEATS_PER_BOOKING` | E2 marks its own |
| `at least 12 characters` | `PASSWORD_MIN_LENGTH` | E5 marks its own |
| the hold countdown and every "three minutes" | `SEAT_HOLD_TTL_SECONDS` | E2 |
| `expires in 30 minutes` on the reset mail and screens | `PASSWORD_RESET_TTL_SECONDS` | E5, already ruled by `P-ACC-07` |
| `in 4 minutes` on a refused resend | `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` | E4, already computed |
| every `Retry-After` sentence | the refusing bucket's state | `S7.20`, already ruled |

**Two exclusions, so the rule has an edge and not a slope.**

1. **A number that is not configuration is typed, and should be.** `72 bytes` in the password messages
   is bcrypt's fixed limit, not a setting — S7.9 says so in terms — and rendering it from a constant
   that can never change buys nothing. The test is whether the value has a row in S7.9, not whether it
   is a number.
2. **A number that is data is not configuration either.** A price, a seat count, a booking reference
   and a film's runtime all come from rows and are already rendered. **The interpolation rule above is
   about values that live in the environment — but the *grammar* rule below is about every rendered
   number, data included**, and that distinction is what this exclusion originally got wrong.

#### Every rendered count owes a singular and a plural

> **Any published string that interpolates a count carries both forms. A string published with only
> one of them is a defect.**

**This extends the rule past configuration to any rendered number, and the extension is a correction
of the exclusion above.** As first written, this section excluded counts on the ground that *a number
that is data is not configuration* — which is true about **interpolation** and irrelevant to
**grammar**. Nothing then reached `3 seats chosen`, `3 seats held by you`, `Used by 3 films`,
`Used by 3 showtimes`, `6 halls` or `12 changes.` — **six published strings, none with a singular**,
in a document that spends a paragraph on precisely this failure for durations: *"an implementer who
finds no rule writes `{n} seconds` and ships '1 seconds'"* (`S7.20` rule 4). **The same implementer
writes `{n} seats` and ships `1 seats`, and no rule in this document stopped them.**

**Every one of those six can reach 1 in ordinary use**, which is what makes this shipped copy and not
a defensive branch:

| String | Reaches 1 when |
|---|---|
| `3 seats chosen` · `3 seats held by you` | a customer chooses one seat — the commonest booking there is, and `P-XCT-30`'s seed now writes real one-seat bookings |
| `Used by 3 films` · `Used by 3 showtimes` | a lookup row is carried by exactly one film or showtime — the state a mistyped entry is in immediately after it is used once, which is `P-ADM-24`'s own worked example |
| `6 halls` | a manager assigned to exactly one hall, which `S7.5` explicitly contemplates |
| `12 changes.` | the change log's first day, and every filtered view narrow enough to return one row |

**`Up to 1 seats.` is the configuration case of the same defect** — `MAX_SEATS_PER_BOOKING = 1` is a
permitted setting — so the two halves of this section meet here: **interpolating a value does not make
the sentence around it correct.** The value and the grammar are two obligations and a string owes
both.

**Each of the six is published by the lane that owns it** — E2 for the seat counts, E6 for the
reference counts and the hall count, E7 for the change count — **and each is that lane's to fix.**
Named here, not edited.

---

## Lane notes

### Article X candidates raised by this lane

**None.** Every reserved question this lane's surface touches maps onto one of the four rows that
already exist. That is a result, not an absence of looking, and two questions were considered and
deliberately **not** raised as rows:

- **The CloudWatch log retention period.** It is a cost-against-evidence trade the client owns, but it
  is Zone C *configuration* rather than an unruled product question. It is handled the correct way:
  the specification recommends a finite retention and says what is lost, **and names no number**,
  because a number here would be the build session choosing the client's trade.
- **Whether the Phase 4 concurrency proof is valid before the rate limiter exists.** It is a
  sequencing question and it is the build session's. It is resolved in S7.18 by re-running the proof
  at the close of Phase 7 rather than by weakening either phase.

### Assumptions I had to flag

| Flag | Where it bites in this lane |
|---|---|
| **`ASSUMED` — hall sizes (90…220)** | `P-XCT-25` and **`P-XCT-30`**. The 375-pixel design target is derived from the 220-seat hall. A different hall size changes the target and nothing else, which is why the row states that a larger hall simply scrolls further. **`P-XCT-30` now derives an exact grid, row letters and three category bands from each of the six sizes** (`OPEN-SCALE-02`). The *derivation* is deterministic and the *sizes* are still assumed, so a client who names real halls replaces six numbers and the grids recompute; nothing else in this lane moves. |
| **`ASSUMED` — the seeded lookup vocabulary** | `P-XCT-30`. Three languages, two certifications, four genres and two formats, every one of them a `DEMO`-prefixed placeholder. The names sit under `OPEN-SEAT-01`'s "you pick" extended to the same class of naming question, and under `OPEN-ATTRIB-01`'s standing constraint for **why** they are placeholders. **They never harden into a constraint**, and the client replaces the whole catalogue the moment they supply real content. |
| **`ASSUMED` — peak concurrency of 50** | `P-XCT-01`, `P-XCT-07`. It sets the load test's figure and the bucket values it will replace. **It proves nothing about correctness**; the fifty-simultaneous-requests-for-one-seat gate is a separate, non-waivable thing that happens to use the same number. |
| **`PROVISIONAL` — four roles** | `P-XCT-05`, S7.5. The whole router matrix rests on it. If it reverses to three roles, the manager role value, the assignment table and the manager router are removed and the dashboard is served to admins with a screen filter — a contained change, which is why the reading was recorded rather than buried. |
| **`PROVISIONAL` — one cinema, six screens** | S7.5's manager scope. Scoping attaches to the **screen**, matching the ruling's own words, so a second venue changes nothing in this lane. |
| **`PROVISIONAL` — cut-off at start **+** 15 minutes** | `SALES_CUTOFF_MINUTES` in S7.9. It is a **signed** value for exactly this reason. The alternative reading is 15 minutes *before*, and the two are half an hour apart. |
| **Estimate, not measurement — rate-limit buckets** | S7.4. Replaced by the Phase 7 load test. |
| **Estimate, not measurement — memory split and image sizes** | S7.12. Replaced by Phase 1 measurement. |
| **Reasoned, not observed — every AWS behaviour** | S7.7, S7.10, S7.12, S7.16. This product has never run in AWS. |
| **Build-session judgment call — two variable *values* no source names** | `SESSION_TTL_SECONDS` (43200, twelve hours) and `PASSWORD_RESET_TTL_SECONDS` (1800, thirty minutes — **the account section's number, matching the copy it shows the customer**, not this lane's). Neither is reserved and both are reversible in one line of configuration. **The merge pass should file them as `[JUDGMENT CALL]` lines.** |
| **Build-session extension — two rate-limit rows** | S7.4's **receipt resend** (per booking, satisfying `FR-ADR-048`, which `FR-ADR-058`'s table predates) and **reports and change log** (per user, `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`). Both are extensions under Art III.9, both carry starting values that are **estimates, not measurements**, and both are replaced by the Phase 7 load test. |
| **Build-session judgment call — how a seeded account gets a password** | `P-XCT-32`, and `SEED_DEFAULT_PASSWORD` / `SEED_EMAIL_DOMAIN` in S7.9. **No source says**; `FR-ADR-067` lists the accounts and stops. One environment variable, hashed once through the application's own function, deterministic addresses, never printed and never committed. **It is a Phase 2 deliverable and a hard Phase 4 dependency** — without it the concurrency proof has nobody to authenticate as. Reversible in one variable. |
| **Build-session judgment call — one date-and-time rendering rule** | `S7.19`. **No frozen source and no `APPROVED` record specifies a format anywhere**; the zone is ruled and the wire encoding is ruled, and the human-readable form was left to whoever wrote each surface — which produced at least six conventions. The five forms adopted are the build session's, chosen to suit an Indian cinema audience, and `S7.19` names the four existing examples that would have to change, three of them in other lanes' files. |
| **Build-session judgment call — the application shell** | `SCR-XCT-05`. No source describes a header, a footer or navigation, and **no screen in the document contained a sign-out control although `P-ACC-05` specifies signing out in detail.** The shell is the smallest thing that makes the routes reachable; every omission from it is listed on the row so it reads as a decision rather than an oversight. |
| **Build-session judgment call — two port numbers and their variable names** | `API_PORT` (8000) and `WORKER_METRICS_PORT` (8001) in S7.9. `P-XCT-18` required a high port and `P-XCT-13` required a second listener, and **neither number nor name existed anywhere**, which by S7.9's own completeness rule was a defect. The **floor** is not a judgment call — a non-root container cannot bind below 1024 — only the two values are, and both are Zone C inputs the client wires. |
| **Build-session judgment call — variable *names*** | `FR-ADR-053` describes several values without naming them. This lane names `FORWARDED_ALLOW_IPS`, `REDIS_CONNECT_TIMEOUT_MS`, `REDIS_COMMAND_TIMEOUT_MS`, `SHUTDOWN_DRAIN_TIMEOUT_SECONDS`, `READINESS_CACHE_TTL_SECONDS`, `LISTING_CACHE_TTL_SECONDS`, `CACHE_REBUILD_LOCK_TTL_MS`, `DB_POOL_SIZE`, `DB_POOL_MAX_OVERFLOW`, `QUEUE_POLL_WAIT_SECONDS`, `OUTBOX_RELAY_BATCH_SIZE`, `OUTBOX_RELAY_MIN_AGE_SECONDS`, `RECEIPT_CLAIM_STALE_SECONDS`, `POSTER_MAX_BYTES`, `PRESIGNED_URL_TTL_SECONDS`, `PASSWORD_MIN_LENGTH` and `STRESS_CONCURRENCY_SPREAD_MS`, and the `RATE_LIMIT_*` family. Naming a variable is not a reserved decision; **the names are the build session's and another lane may already have chosen different ones.** Five names in S7.9 are **not** this lane's and are carried exactly as their owning sections wrote them — `BCRYPT_COST`, `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`, `POSTER_REDIRECT_CACHE_SECONDS`, `RECEIPT_RESEND_MIN_INTERVAL_SECONDS` and `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` — because the inventory has to match the code and the contract, not the other way round. |
| **`[JUDGMENT CALL]` — the stress script's two phases** | `P-XCT-07`, pointed at from `P-XCT-01` and S7.1. **Decided:** the script warms up by signing fifty seeded customers in through the real endpoint, untimed and unmeasured, and the measured window issues zero sign-ins. **Why:** fifty sign-ins from one address exceed `RATE_LIMIT_LOGIN_IP_PER_15MIN`, so as written the never-waivable gate could not obtain its sessions; a warm-up removes the login bucket from the measured result without disabling anything, and a refused warm-up sign-in waits on `Retry-After` and retries, so the gate runs at the **unchanged** default in ten minutes of warm-up. **Reversible:** two configured bucket values and the phase split, all in the script and the environment, no schema and no application code. |
| **`[JUDGMENT CALL]` — the seed claims the lookup vocabulary and the hall layouts** | `P-XCT-30`. **Decided:** the seed creates twelve `DEMO`-prefixed lookup rows and assigns them to the eight films by a deterministic index function, and each of the six screens gets an exact grid, `I`-skipping row letters and three computed category bands. **Why:** `P-ADM-01` refuses a film without them and `P-ADM-23` correctly claimed none, so no lane claimed them and Phase 2 had no data; and "full layouts" with no definition is a guess an implementer would have had to make alone. **Reversible:** it is seed-script data, replaced wholesale the moment the client supplies real content. |
| **`[JUDGMENT CALL]` — why the listings are the exception to `DEL`-never-`SET`** | `P-XCT-08` and S7.6. **Decided:** this row keeps single-key invalidation and its `DEL` rule verbatim, and records that an unbounded, caller-chosen key set is made unreachable by a generation value instead — the same idea, not a relaxation, and not a `SET` because the value publishes no content. **Why:** a `DEL` names a key and the listings have none to name, so the rule as written could not be satisfied and `immediately` could not be true. **The mechanism, the key format and its exception paths are `P-BRW-12`'s** and are not restated here. **Reversible:** it is a cache strategy; correctness never depended on it. |
| **`[JUDGMENT CALL]` — seeded bookings carry a `suppressed` dispatch row** | `P-XCT-32`, with `P-XCT-30` pointing at it. **Decided:** the seed writes a `receipt_dispatch` row for every seeded booking rather than none, in a state that says no send was attempted and none will be. **Why:** `P-TKT-07` asserts a confirmed booking always has one, so writing none put **11,003** bookings on a branch `P-TKT-05` calls unreachable — a figure this row had been quoting as "roughly sixty", wrong by two orders of magnitude and corrected against `P-XCT-30`'s own occupancy rule. **The state's name, its transitions and the resend refusal copy are E4's** and are not restated here. **Reversible:** it is seed data and one enumerated state. |
| **`[JUDGMENT CALL]` — the seed's showtime identity and its second-run behaviour** | `P-XCT-30`. **Decided:** the placeholder identity is `(screen_id, starts_at)`, unique because `P-ADM-08` forbids two showtimes sharing a start on one screen; and **the anchor is read from the data on every run after the first** — `first_day` is the earliest existing seeded showtime's local date, falling back to the clock only when none exist. A second run therefore recomputes the identical 720, finds them, and inserts nothing. **Why:** showtimes were the one seeded entity with no identifier, and with the window anchored to the clock a re-run addressed a different span and — because the film index is global — changed the film on every overlapping showtime. **This row had already rejected "about one month" for that exact property and the replacement inherited it.** **The cost is stated rather than hidden:** a database seeded three months ago and re-run today keeps its three-month-old window, and refreshing it is what the wipe-and-reseed command is for. **Reversible:** one derivation. |
| **Corrected figure — the `21:30` slot's end instant** | `P-XCT-30`, `X1`. Published as `00:10`, which is `starts_at + runtime` with **the changeover dropped**; the row's own rule gives `21:30 + 160 + 20 = `**`00:30`**. **The fifth arithmetic defect a reader found in this document and the fifth no gate could catch** — `ends_at` is `NOT NULL`, it is the upcoming/past boundary, and four endpoints return it. **Every claim resting on it was re-checked against the corrected figure rather than assumed to carry over**: the no-overlap conclusion holds at either value (the next showtime is 11½ hours later) and the 210-minute slot spacing is measured against the 180-minute occupancy, which this correction confirms. **The error is recorded at the site**, because this is the second wrong figure that block has carried and a quietly corrected worked example teaches nobody. |
| **`[JUDGMENT CALL]` — the seeded 30 days are centred on the clock, not started at it** | `P-XCT-30`, deciding `F2`. **Decided:** day index `d = 0..29` maps to a local date offset of `d - 15`, giving 15 past days, the clock date, and 14 future days. **Why:** the previous shape put no seeded booking in the past, which left `SCR-ACC-04`'s **Past** group empty by construction — one of three zero states written to be distinguishable — every dashboard period beyond today empty on a product whose Phase 8 is the dashboard, and `EP-ADM-09`'s `include_past=false` with nothing to hide. `P-ADM-07` asked for "about a month of historical data" and is rank 4, so this row wins on precedence; **winning on precedence while shipping a demonstration with no history is winning the wrong argument.** **No published figure changes** — 720 showtimes, 58,800 booked seats, 11,003 bookings hold — which is why this shape was chosen over appending a past month. **Reversible:** one offset. |
| **`[JUDGMENT CALL]` — the manager-to-screen mapping** | `P-XCT-30`. **Decided:** `screen_number = floor((m - 1) / 2) + 1`, so `manager-01`/`02` hold Screen 1 and so on. **Why:** *"two per screen"* fixed the shape and not the assignment, so a manager's dashboard covered a different hall in every build and `S7.5`'s mandated scope test — non-empty for their own, denied for another's — had no fixed subject. **`PROVISIONAL`**, resting on the four-role ruling (`SRC-003 C-1`); if that reverses this goes with it. **Reversible:** one formula. |
| **Verified figure — the seed's `booking_index` base, and the published numbers re-derived from it** | `P-XCT-30`, `D13`. The base was never stated, so **11,003 and a mean size of 5.34 could not be checked against the rule that produced them.** Now stated as counting from 0, globally, and **both figures were re-derived from that base before it was written down**: base 0 gives 11,003 / 5.344 and base 1 gives 11,002 / 5.3445. The published figures came from base 0 and are correct. **Had the check come out the other way the published figures would have moved, not the rule** — a rule adjusted to fit a number it did not produce is how a worked example becomes a lie, and `S1.5` transcribes these into tests. |
| **`[JUDGMENT CALL]` — the seed's film assignment, runtimes, `ends_at` and booking distribution** | `P-XCT-30`. **Decided:** `film_index = (k + d) mod 8`; `runtime_minutes = 90 + i*10`; `ends_at = starts_at + runtime + SEED_CHANGEOVER_MINUTES`; `booking_size = 1 + (index mod 10)` with `owner = customer[index mod 50]`. **Why:** the row was exhaustive about days, halls, slots, formats and occupancy and never said which film plays, how long it runs, or what goes in a `NOT NULL` `ends_at` — `scripts/seed.py` could not be written from it. **The changeover is `ASSUMED` and is expressly not an answer to `PROPOSED-TURNAROUND-01`**; the seed needs *a* number because a column cannot hold an open question, and when the client rules the real figure this follows it. **All `ASSUMED`, none hardens.** **Reversible:** seed constants. |
| **Corrected figure — "roughly sixty" seeded bookings was wrong by two orders of magnitude** | `P-XCT-32` and this lane's judgment-call row for `suppressed`, both corrected to **11,003**, computed from `P-XCT-30`'s own occupancy rule (58,800 booked seats at a mean booking size of 5.34). Sixty was never computed from anything and appears to have been read off the sixty-three *accounts*, a different quantity sitting nearby in the same rows. **The `suppressed` decision is unchanged and is strengthened**: at sixty it was a specification defect, at eleven thousand it is also the first thing an operator would see. **Two further sites are lane E4's and are named, not edited.** |
| **`[JUDGMENT CALL]` — the seed publishes its films, against one repo-committed placeholder poster** | `P-XCT-30`. **Decided:** eight films published and inside their windows, one flat design-system placeholder authored in this repository, uploaded once, shared by all eight. **Why:** `P-ADM-05` refuses publication without a poster, so an unpublished seed produced a landing page reading "Nothing is showing right now.", falsified `P-BRW-04`'s worked example and this row's own lookup consequence, and made Phase 3 undemonstrable. **`OPEN-ATTRIB-01` is untouched and the row says so** — it is about real posters and their licensing, and a repo-committed flat shape is neither generated content nor content from an unknown source. **One constraint was deliberately narrowed**, from *generates no image of any kind, from anywhere* to **"invents no film artwork and fetches no image from anywhere"**, and the narrowing is stated at the site. **Reversible:** the client replaces the asset the moment they supply real ones. |
| **`ASSUMED` — the seeded schedule, occupancy and uplifts** | `P-XCT-30`. Four start times (`11:00`, `14:30`, `18:00`, `21:30`), 30 days, 720 showtimes, occupancy `10 + (k mod 9) * 10`, and Standard / Premium / Recliner at `0` / `1250` / `3333` basis points. **No source names any of them.** The uplifts are deliberately the same three numbers the pricing worked examples use as *example input*, and **that identity is now stated rather than left for a reader to infer that an example is data.** All of it is `ASSUMED` under `OPEN-SEAT-01` and `OPEN-SCALE-02` and **never hardens into a constraint**; a client with real programming replaces a handful of numbers. |
| **`[JUDGMENT CALL]` — two bcrypt settings that were called configuration and did not exist** | `BCRYPT_THREAD_POOL_SIZE` (`2`) and `BCRYPT_HASH_TIMEOUT_MS` (`5000`) in S7.9. **Decided:** the pool defaults to the `t3.micro`'s vCPU count, because bcrypt at cost 12 is CPU-bound and a larger pool queues rather than parallelises; the timeout exists because `P-ACC-03`'s exception path fires on a timeout that had no value anywhere and was therefore unreachable. **Why it may not stay implicit: the pool size is the concurrency at which sign-in starts returning `503`.** Both **`ASSUMED`**, both replaced by Phase 7's load test. **Reversible:** two variables. |
| **`[JUDGMENT CALL]` — `METHOD_NOT_ALLOWED`, a code raised by no route** | `P-XCT-11`, and a `newerrorcode` block in S6. **Decided:** for the **never-deleted set only** — `movie`, `showtime`, `screen`, `cinema` and the four lookup vocabularies — no `DELETE` route is mounted, and one global handler renders the framework's method-not-allowed as the product envelope at **405** with one generic entity-blind sentence. **Why:** the document held three mutually exclusive answers, one of them inside a single row, and an unmounted route was publishing a message it could never emit. `P-ADM-20`'s "the absence is the control" is kept intact — a handler creates no route to later make work. **Corrected once since first written**, and the correction matters: an earlier revision claimed *no `DELETE` route is mounted anywhere*, which is **false** — `EP-ADM-21` deletes a seat and a `manager_screen_assignment` row is genuinely removed. The scoping is principled rather than an exception list, on one distinction: **a route that refuses a real request with a real reason has a case where it succeeds; a route mounted only to say no does not.** **Reversible:** one handler and one registry row. |
| **`[JUDGMENT CALL]` — a rate-limited control stays enabled** | `SCR-XCT-03`. **Decided:** the refused control keeps its ordinary enabled state and gains no `disabled` and no `aria-disabled`; the banner carries the wait and the banner announces. **This reverses what this row said in its previous revision**, and the reversal is stated at the site rather than made quietly. **Why:** `SCR-ACC-01` already reasons this way and it is the product's general stance; a client-side countdown is a second clock that drifts, and under `S7.20`'s corrected arithmetic the tabulated figure is a **maximum**, so a customer is frequently allowed *earlier* than the countdown shows. **The server is the authority on refusal.** **Reversible:** one attribute on one component. |
| **`[JUDGMENT CALL]` — the request id's format** | `P-XCT-12`, `B14`. **Decided:** eight lowercase hexadecimal characters, per request; `a1b2c3d4` in roughly forty published strings is that format and not a placeholder for something longer. **Why:** no length, alphabet or format existed anywhere, and the document is explicit elsewhere that an example is not a specification. Eight is chosen for the one property that makes it observable — a person reads it aloud or types it from a screen. **The cost is stated at the point it bites:** it is not unique (about a half chance of a collision by 77,000 ids) and is therefore a correlation aid and never a key. **Reversible:** one generator. |
| **`[JUDGMENT CALL]` — a configured number in copy is rendered, never typed** | **S7.21**, new. **Decided:** any customer-facing string quoting a configuration value renders it; a literal is a defect; the published strings stay as they are, being the rendering at the default, and each is marked with the name it interpolates. **Why:** the document ruled this independently in three places and left `Up to 10 seats.` and `at least 12 characters` unmarked — and `MAX_SEATS_PER_BOOKING` below 10 is a **permitted** setting, so the literal tells the customer a limit the server does not enforce, and no test catches it because the two agree at the default. **Reversible:** it is a rule about how strings are produced, not about their content. |
| **`[JUDGMENT CALL]` — the dashboard's per-show time format, decided rather than deferred** | `S7.19`, `A7`. **Decided:** date-with-time on a view spanning more than one day, time-only on a single-day view — the section's own existing test, applied to a table. **The previously proposed sixth form is withdrawn** and the sentence handing the case back to E7 is deleted. **Why:** this section declares itself the owner of the rule and its own rule 6 says a gap is fixed here and never locally, so deferring one case contradicted both — and proposing a form in the act of deferring left another lane holding a format this section had invented and not adopted. **Reversible:** two rows in one table. |
| **`[JUDGMENT CALL]` — one read-path `DEPENDENCY_UNAVAILABLE` sentence** | `SCR-XCT-01`'s copy table, with the boundary stated on `SCR-XCT-02`. **Decided:** "This could not be loaded right now. Nothing was being saved, so nothing was lost. Try again in a moment.", registered as the default for any read endpoint whose own row publishes none. **Why:** every existing sentence for this code says some version of "Nothing was saved", which is **false on a `GET`**; the admin lane hit this, correctly declined to mint a local variant, and a cross-cutting code belongs in a cross-cutting registry. **What it is not:** a replacement for the two read sentences that already exist — `P-BRW-12`'s seat-map string and the browse section's public-site string both outrank it under `S1.2` and both stay. **No frozen source specifies error copy.** **Reversible:** one string in one table. |
| **`[JUDGMENT CALL]` — one duration-rendering rule** | **S7.20**, with `S7.19` rule 7 pointing at it. **Decided:** the `Retry-After` header is always integer seconds and is never rendered; the sentence reads seconds below 120 and `ceil`-ed whole minutes at 120 and above, with the singular forms specified. **Why:** seven published verbatim strings could not all have come from one function — 240 and 720 became minutes while 900 stayed seconds — and they are rank-2 copy, so an engineer could not pick without overriding a row. The threshold is 120 rather than 60 so a 90-second wait is not overstated by a third. **No frozen source specifies a duration format.** **Reversible:** one function and one constant. **The rendering rule is the judgment call; the arithmetic beside it is not.** The strings changed in this lane are `P-XCT-06` rows 7 to 9 and `SCR-XCT-03`'s copy table, from one wrong figure to three derived ones. **Corrected once since, and the correction is the entry that matters:** the table was published as one constant per bucket, and `P-ACC-14` was right that `Retry-After` is the time actually remaining until the next token. A constant is correct only at the instant the bucket empties and overstates every later retry. The table is **relabelled as the maximum** rather than deleted — the maximum is what it always was, and it is why every published example carries that figure — and a two-retry worked example now shows the value falling. **No published string changed as a result**, because rule 6 already forbade typing the number. |

| **`[JUDGMENT CALL]` — the red-proof drill runs in two stages, and only the second reaches the constraint** | `P-XCT-01` and `S7.1`, deciding `J-XCT-01`. **Decided:** Stage A is the fifty-request hold gate exactly as `SRC-002 §9.1` and `P-HLD-13` require, and it is recorded as exercising the constraint **zero** times; Stage B puts **two live holders on one seat** — by deleting the lock key in Redis inside the `PAYMENT_SIMULATED_DELAY_MS` window of a confirm already in flight — so that two confirms both reach `P-PAY-10` step 7, and *that* is the run the constraint is dropped under. **Why:** the drill as specified could not produce more than one winner. `P-HLD-13` and `P-PAY-11` both fix the gate at the **hold**, where all forty-nine losers are refused by Redis and the constraint is never reached, so dropping it changed nothing — and `P-XCT-01` exception 5 and `P-HLD-13` exception 4 then classified that outcome as a void proof and a stop-the-line finding. **The one gate this project calls never waivable reported failure against a correct implementation.** **Nothing is weakened:** the Redis lock still provides the hold, the constraint plus row locking still provides the truth, and the database half still may not be waived. **It is stricter** — a guard exercised zero times is now exercised, watched failing, and watched working again — so it needs no signature (Art III.10). **Deleting a lock key is a fault injection, not a disabled control:** the lock layer, both `SET … NX` calls, both token re-validations and the rate limiter all run normally, and a key disappearing is what an eviction or a restart does on its own — the very failure `S7.1` names as the reason the second layer exists. **Local only**, because Stage B needs direct Redis access and the constraint drop is a destructive schema change. **Reversible:** it is a test procedure; no schema, no application code and no published customer string changes. **Two cross-file corrections follow from it** — `P-HLD-13`'s acceptance criterion and exception 4 in `E2_seat_hold.md`, and `P-PAY-11`'s worked example in `E3_checkout_payment.md` — **named, not edited.** |
| **`[JUDGMENT CALL]` — how the seed is run against a deployed environment, and how its password gets there** | `P-XCT-32`, deciding `J-XCT-03`. **Decided:** a fourth entrypoint command, `seed`; a one-off ECS task on **its own task definition family**, not the service's; and `SEED_DEFAULT_PASSWORD` as an SSM `SecureString` referenced by `valueFrom` **from that family alone**. **Why:** both this row and `P-XCT-30` assigned the deployed run to the client and neither said how, while `S7.9` makes the variable seed-only so it cannot ride in on the service's `secrets` block — leaving the only route to a first password with no route into the environment. **Phase 2 had no admin who could sign in and Phase 4 had no fifty customers.** **Why a separate family rather than a command override:** overriding a command is ECS's ordinary mechanism and the migration run uses it, but a secret must be *in* a family to be resolved from it, and putting it in the shared family is exactly what the seed-only rule forbids. **Two families, one image**, so the code and the seed stay the same build. **All of it is Zone C and the build session builds none of it** — what is owed is the command, the variable, the parameter path, the execution-role grant and the acceptance criterion. **A prep-queue row with a needed-by of Phase 2 is owed and is named in the return, not written** (`S7.16`). **Reversible:** one entrypoint branch and one task definition. |
| **`[JUDGMENT CALL]` — four rules that say who scrolls the seat map and to where** | `P-XCT-25`, deciding `J-XCT-06`. **Decided:** the container is scrolled to its leading edge on first paint; to the minimum position that brings a keyboard-focused seat **fully** into view; to the first restored seat of a restored selection; and to the first seat an error names. Plus `scroll-padding-inline-start: var(--fr-seat-gutter)`, so no focused cell can come to rest under the pinned row gutter. **Why:** every row in the document said the map *scrolls* and **nothing anywhere moved it**, so arrow-key focus routinely landed on a seat outside the visible strip and the pinned gutter overlaid the leftmost cells. The second of those is **WCAG 2.2 SC 2.4.11 Focus Not Obscured (Minimum)**, new at AA in 2.2 and inside the target `P-XCT-24` adopts. **It is fixed rather than recorded as a deviation**, because `P-XCT-24` carries exactly one deviation — the unextendable hold — and a second one would be a real regression dressed as bookkeeping. **The hall size behind the ten-of-twenty split is `ASSUMED`** under `OPEN-SCALE-02` and does not harden; the rule does not depend on it. **Reversible:** four scroll calls and one CSS property. |
| **`[JUDGMENT CALL]` — the seed writes no `audit_log` row, and the absence is specified** | `P-XCT-30`, deciding `J-ADM-13`. **Decided:** `scripts/seed.py` writes no audit row for anything it creates, and every seeded row is identified instead by its `DEMO` prefix and the reserved `.invalid` domain. **Why:** `P-ADM-19` makes `actor_user_id` non-null and forbids **both** a role name and a service account, and the seed creates the first admin itself — so at its earliest writes no user row exists for an actor column to point at. All three ways out are worse: a null actor breaks the rule in the one table whose value is that its rows are true; a `seed` service account is forbidden in terms; attributing 720 showtimes to `admin-01` is a false statement about who did it. **The scope this rests on:** a privileged write is an admin action arriving through the API, and the seed is provisioning by a script. **It is the only exemption from `P-XCT-03` in the product and no application code path inherits it.** **The gap is recorded, not closed:** the Phase 8 change log shows nothing before the first real admin action, and a reader will assume the catalogue was made by hand. **Reversible:** it is an absence; adding rows later needs an actor the product does not yet have. |

### Where I would have had to guess and did not

1. **What a customer is told when the receipt definitively fails after payment is captured.**
   `OPEN-EMAILFAIL-01`. **No sentence is written for that screen anywhere in this section**, including
   in `SCR-XCT-01`, and the omission is stated in the screen itself so nobody fills it in later. The
   mechanism ships and the message does not.
2. **Whether TLS is or will be terminated anywhere.** `OPEN-TLS-01`. This lane specifies only the
   surface the deferral forces — `COOKIE_SECURE` with no default, the environment never called
   production, no real customer data — and says nothing about the answer.
3. **A supported-browser or version matrix.** **No frozen source contains one.** Inventing one would
   create a testing obligation nobody asked for and a false claim about what has been checked. Named
   in S7.13 as a question for the client rather than an omission.
4. **The load balancer's health check interval, unhealthy threshold and deregistration delay.** Zone C
   values the client sets. The two worked examples that need numbers use them **labelled as
   illustrative and Zone C**, and the specification states the *relationships* those numbers must
   satisfy rather than the numbers themselves.
5. **The CloudWatch log retention period.** See the Article X note above. A finite retention is
   recommended and no number is chosen.
6. **Whether any alarm beyond the ruled one is adopted.** It is not. The dead-letter-queue alarm is
   recommended in writing and left as the client's decision, because one alarm was ruled and adding
   five more is inventing scope and doing the client's Zone C work in one move.
7. **What happens to bookings on a withdrawn showtime.** `OPEN-SHOWCANCEL-01`. This lane states only
   the fail-closed position — **no withdraw-showtime capability exists in v1** — and offers no
   refund, cancellation or withdrawal behaviour of any kind.
8. **Where the client's posters and titles come from.** `OPEN-ATTRIB-01`. The standing constraint is
   applied — obvious placeholders, no image from anywhere — and no source, brand or attribution
   wording is written.
9. **What the ECS deployment's minimum-healthy-percent, stop timeout and memory limits should be set
   to in the client's account.** The relationships and the reasoning are owed and given; **the values
   are the client's to set and the build session sets none of them.**

10. **Whether one shared seed password is acceptable for an environment that will one day carry real
    bookings.** `P-XCT-32` decides only what it may: a mechanism for a **demonstration** environment
    that carries no real customer data by ruling (`R-CON-08`, `P-XCT-29`). **It writes no policy for
    real accounts, no rotation procedure and no rule about who may hold the value** — all three are
    reachable only once `OPEN-TLS-01` closes, and the first is reserved because it is about real
    people's accounts.

11. **What the client's alert or sender addresses are**, and therefore whether any seeded address
    could ever be verified in SES. Not guessed. `SEED_EMAIL_DOMAIN` defaults to a domain that
    **cannot** exist, which makes the question unanswerable-and-harmless rather than open.

12. **A prose format for a period heading.** `S7.19` governs rendered instants and says so; the
    dashboard's `Friday 14 August 2026` heading is a sentence rather than an instant and stays with
    the lane that owns it. **A sixth form was not invented to cover another lane's copy.**

13. **What the client's own header should say beyond navigation.** `SCR-XCT-05` adds a wordmark, the
    links each role can use, sign-out and one honest footer line. **No About, no Contact, no help
    text, no version string** — every one of those is content the client will see and may take as
    real (`FR-ADR-067`), or an internal detail on a public page.

### Contradictions found, with both sides named

1. **The variable name for the sales cut-off.** The lane brief's binding-constants table names
   `SALES_CUTOFF_MINUTES`. **Two `APPROVED` records — `FR-ADR-042` and `FR-ADR-053` — both name
   `SALES_CUTOFF_MINUTES`.** ADRs are `APPROVED` and immutable, so this section uses
   **`SALES_CUTOFF_MINUTES`**. The merge pass must pick one and it should be the ADRs'. *(The value and
   its sign are identical in both: `+15`, `PROVISIONAL`.)*
2. **Phase ordering against a stated proof condition.** `SRC-002 §12` puts rate limiting in **Phase 7**
   while `FR-ADR-034` requires the concurrency proof — **Phase 4** — to run **without the limiter
   disabled**. At Phase 4 there is no limiter to disable, so the condition is vacuous exactly when the
   proof first runs. Neither side is wrong; the clause and the record simply do not meet. Resolved in
   S7.18 by re-running the proof at the close of Phase 7, and **flagged rather than absorbed.**
3. **`CONSTITUTION.md` Art VIII.13's outbound list is stale** — it still names the withdrawn external
   movie source. Already raised in `FR-ADR-065` and not re-opened here. **S7.16 carries the corrected
   six-path list and does not repeat the stale one.** The Constitution is outside this lane's write-set
   and amending it is the client's.
4. **`P-XCT-18` contradicted `P-PAY-10` on money, and `P-XCT-18` also contradicted itself.** Its
   exception row 1 said a retry after a crash between capture and commit "finds the `in_progress`
   record and replays"; `P-PAY-10` crash point 6 says the record rolled back with the transaction and
   the capture simply runs once. **`P-XCT-18`'s own worked example already said what `P-PAY-10` says**,
   so the row disagreed with the owner and with itself in the same breath. `P-PAY-10` owns the confirm
   transaction's crash points and this row is a cross-cutting restatement, which under `S1.2` carries
   no authority — **so the restatement was corrected, not the owner.** The row now defers by name and
   states why it keeps one crash at all. **Resolved here; nothing in `E3_checkout_payment.md` was
   touched.**
5. **Three published rate-limit waits in other lanes state a bucket's capacity or an invented figure
   rather than its refill interval.** `Retry-After` is `ceil(window / capacity)` — S7.4's ruled
   formula — and E2's `20 seconds`, E3's `30 seconds` and E4's `45 seconds` are none of the values
   that formula produces for their buckets. **This section had made the same class of mistake twice
   itself** — `900 seconds`, which is the sign-in *window* — which is why the fix was to tabulate the
   derivation for all thirteen buckets in **S7.20** rather than to correct four strings. **The three
   are named there and not edited**; each is copy its own lane's row publishes.
6. **`P-XCT-05` gave `404` where `P-RPT-09` and the error registry give `405`.** A `POST` on the
   reports router addresses a path that exists and serves `GET`, so `405` is correct and `404` denies
   that the address exists. **The negative test for the read-only router is transcribed from one of
   the two rows**, so a suite built from the old line passed against a wrong implementation while one
   built from the registry failed against a correct one. **This section's line was the wrong one and
   is corrected here**; the `newerrorcode` block in `S6` is widened in the same pass, because it
   described only the `DELETE` case and **the machine-readable copy is the one that reaches the
   artifact.** `P-RPT-09` row 3 additionally calls the response *"the framework's method-not-allowed
   response"*, which contradicts `FR-ADR-052` and `P-XCT-11` — **that half is lane E7's and is named
   here, not edited.**
7. **`P-XCT-05` and `P-RPT-01`/`P-RPT-02`/`P-RPT-08` publish different sentences for the same four
   refusals.** No session, wrong role, an out-of-scope hall, an empty scope — and two of the four
   pairs are different sentences rather than paraphrases. **Both are rank-2 rows, so `S1.2` does not
   settle it and `S1.2.1` case 1 makes an unresolved rank-2 tie a defect rather than the implementer's
   choice.** Resolved the way `SCR-XCT-01` resolves `FORBIDDEN` and `AUTH_REQUIRED`: **the row that
   knows what the caller could not reach owns the words**, and this section's four are the generic
   floor for any router whose own P-row publishes nothing. **Nothing in `E7_dashboard.md` was
   touched.**
8. **`S7.18` puts `P-XCT-08` and `P-XCT-09` in Phase 3 while `AWS_PREP_QUEUE.md` row 8 gives
   ElastiCache Redis a needed-by of Phase 4.** Phase 3's seat-map read is rate-limited and the limiter
   fails closed, so without Redis **Phase 3's own acceptance cannot be demonstrated in AWS at all.**
   The phase table is right and the queue row is one phase late. **This lane writes nothing to that
   file** (`S7.16`); the correction is named in the return.
9. **"This repository is public" appears in several `APPROVED` records, and the repository is now
   private.** Adjudicated in `FR-ADR-071`: no rule changes, one rationale does, and the records are not
   edited. **This section asserts neither**, and states the no-credentials floor as a constitutional
   floor rather than as a consequence of visibility — which is the stronger ground `FR-ADR-071`
   identifies.

*End of `E8 — cross-cutting floors`. Every P-row above carries at least one `[SRC:]` citation and at
least one `[BRD:]` row; where a citation is missing, the row is the defect and not the source.*
