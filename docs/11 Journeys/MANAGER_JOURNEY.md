# The hall manager's journeys

```
Lane .............. MANAGER (GOAL_06, one of five lanes walked independently and blind)
Written ........... 2026-08-22
Persona ........... manager — an account, read only, the dashboard for the screens they are
                    assigned to and nothing else
Sections read ..... docs/03 PRD/sections/S1_reading_rules.md (in full)
                    docs/03 PRD/sections/S3_personas_surfaces.md (in full)
                    docs/03 PRD/sections/E7_dashboard.md (in full — P-RPT-01..12,
                    SCR-RPT-01, SCR-RPT-02, EP-RPT-01..04, lane notes)
                    docs/03 PRD/sections/E8_crosscutting.md (P-XCT-02, P-XCT-03, P-XCT-05,
                    P-XCT-11, SCR-XCT-01, SCR-XCT-05, S7.19)
                    docs/03 PRD/sections/E5_account.md (P-ACC-02, P-ACC-07, P-ACC-08,
                    SCR-ACC-01)
                    docs/03 PRD/sections/E6_admin.md (P-ADM-09, P-ADM-17)
                    docs/03 PRD/api/error_codes.md, docs/03 PRD/api/contract.json
                    CONSTITUTION.md Article X.0 / X.0b / X.0c
Defects filed ..... 14, as J-MGR-01 .. J-MGR-14
Steps walked ...... 45 across six walks
```

> ## ⚠ This whole persona is `PROVISIONAL` and one message from the client deletes it
> `SRC-003 C-1` reconciles two of the client's own answers: `OPEN-ROLE-01` says *"do not make more
> personas… only 1 admin persona"*, and the very next answer, `OPEN-SCOPE-01`, describes *"2 managers
> per cinema hall"* with a dashboard. The build session read that as **four roles** and recorded the
> rejected three-role reading. If the client reverses it, the `manager` role value, the
> `manager_screen_assignment` table, `EP-RPT-03`, `P-RPT-08`'s empty state and the manager half of
> every copy string in `SCR-RPT-01` are deleted, and this document describes nobody.
>
> **This walk does not re-decide that.** It walks the persona as specified and marks each step where
> the provisionality bites.
>
> **"Two managers per hall, twelve in total" is an observation of the client's current staffing, not a
> constraint** (`P-RPT-02`, `P-ADM-17`, `FR-ADR-011`). No check constraint, no trigger and no
> application rule enforces the number two. Nothing below counts managers or fails when a hall has
> one, three, or none.

---

## Walk 1 — A manager reads occupancy and earnings for a hall they are assigned to

**Fixed inputs for the whole walk**, taken from `P-RPT-01`'s and `P-RPT-03`'s worked examples so the
numbers below are transcribed rather than invented. Manager **M** is assigned screens 3 and 5.
Injected clock `2026-08-14T12:50:00Z` = Friday 14 August 2026, 18:20 Asia/Kolkata. Hall sizes are
`ASSUMED` (`SRC-003 OPEN-SCALE-02`) — screen 3 at 150 seats and screen 5 at 220 are the build
session's choice and never a constraint, so **the formula is what this walk exercises and the example
capacity is not**.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ACC-01` `/sign-in` | signed out; no `fr.pending_selection` | submits email and password | API → Postgres: load user by `lower(email)`, one bcrypt verification, `UPDATE users SET last_signed_in_at` | `system` | a session cookie carrying id, email and `role = manager` | `P-ACC-02` | — |
| 2 | `SCR-ACC-01` → the movie listing | authenticated | none — the screen's success rule fires | sign-in → movie listing (`SCR-ACC-01` → listing), because this is a **deliberate** sign-in with no pending selection | `page` | a manager standing on the customer-facing listing | `P-ACC-02` | — |
| 3 | `SCR-XCT-05` shell nav | signed in as manager | follows `Dashboard` | listing → `/dashboard` (`SCR-XCT-05` → `SCR-RPT-01`) | `page` | `SCR-RPT-01` in its Loading state, previous figures cleared | `P-XCT-05` | — |
| 4 | `SCR-RPT-01` `/dashboard` | Loading; `Day` preselected | the screen issues its opening request, `GET /api/reports/dashboard?period=day` with `date` omitted | API → router dependency → Postgres: `report_scope` resolves `{3, 5}` from `manager_screen_assignment`, **from the session and never from a parameter** | `system` | a resolved scope the handler cannot widen | `P-RPT-02` · `P-XCT-05` | `J-MGR-01` |
| 5 | `SCR-RPT-01` | scope resolved | server computes the period from the injected clock | `time`: local day `2026-08-14 00:00` → `2026-08-15 00:00` Asia/Kolkata, converted to `[2026-08-13T18:30:00Z, 2026-08-14T18:30:00Z)` | `time` | a half-open UTC window returned beside every figure, so the number can be reproduced from the response alone | `P-RPT-01` | `J-MGR-02` · `J-MGR-03` |
| 6 | `SCR-RPT-01` | window fixed | one `REPEATABLE READ` transaction sums the money | API → Postgres: `COALESCE(SUM(booking_seat.price_paise), 0)` over showtimes in window and in scope, `b.status='confirmed' AND p.state='captured'`, cast back to an integer type | `system` | `takings_paise: 2783331`, `seats_sold: 109`, `capacity: 370`, `shows: 2` — a JSON **integer**, never a float and never a formatted string | `P-RPT-03` · `P-RPT-07` · `P-XCT-02` | — |
| 7 | `SCR-RPT-01` | takings computed | occupancy computed in the same snapshot | API → Postgres: `(109 × 2000 + 370) // (2 × 370) = 218370 // 740 = 295`, integer arithmetic only | `system` | `occupancy_pct: 29.5` — **not** the 35.1 that the mean of the per-show percentages would give | `P-RPT-04` | — |
| 8 | `SCR-RPT-01` | headline computed | per-film rows grouped in the same snapshot | API → Postgres: group by `movie_id`, order `takings_paise DESC, title ASC, movie_id ASC`, capped at 100 | `system` | one row, `DEMO MOVIE 01`, 2 shows, 109 seats, 370 capacity, 29.5 %, 2 783 331 paise; `films_truncated: false` | `P-RPT-05` · `P-RPT-07` | — |
| 9 | `SCR-RPT-01` | response complete | the whole response lands and every figure renders at once — there is no state in which one figure has a value and its neighbour shows a loading block | API → browser: integer paise formatted at the edge only, `₹27,833.31`, `--fr-font-mono` with Indian digit grouping | `page` | four figures, the occupancy bar, and a per-film table captioned **"Per film, in your halls"** — not "Per film", because a scoped figure read as a cinema-wide one is the reading this caption exists to prevent | `P-RPT-07` · `P-XCT-02` | `J-MGR-01` |
| 10 | `SCR-RPT-01` per-show table | headline rendered | the listing is fetched separately, because a month across six halls is on the order of a thousand rows on a host with roughly 1 GB in total | API → Postgres: `GET /api/reports/showtimes?period=day`, `limit=50`, `offset=0` | `system` | `total: 2`; both rows carry `has_started: false` **and** non-zero takings, and render "Still selling" | `P-RPT-06` | — |
| 11 | `SCR-RPT-01` period tabs | Day rendered | selects `Week` | `time`: ISO-8601 Monday-first — Mon 10 Aug 00:00 → Mon 17 Aug 00:00 local = `[2026-08-09T18:30:00Z, 2026-08-16T18:30:00Z)` | `time` | the week's figures; the previous period's figures **cleared**, not left on screen under a spinner | `P-RPT-01` · `P-RPT-07` | `J-MGR-02` · `J-MGR-14` |
| 12 | `SCR-RPT-01` period tabs | Week rendered | selects `Month` | `time`: the calendar month `[2026-07-31T18:30:00Z, 2026-08-31T18:30:00Z)`, never a rolling thirty days | `time` | August's figures, computed live inside the request — no rollup table, no materialised view, no cached report, because nothing in this system runs on a schedule | `P-RPT-01` · `P-RPT-12` | `J-MGR-03` |
| 13 | `SCR-RPT-01` hall filter | Month rendered | narrows to Hall 3 | API → router: `screen_id=3` intersected with the resolved `{3, 5}` — the third dependency **never widens** | `system` | Hall 3's figures alone, `screen_ids: [3]` | `P-RPT-02` | — |
| 14 | `SCR-RPT-01` | the 61st request inside 60 s | presses a period tab again | API → Redis: the per-user token bucket `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` = 60 is empty; the limiter **fails closed** | `system` | 429 and the banner "Too many requests. Try again in 1 second." — one second because `ceil(60 / 60) = 1`, computed at render time and never typed. The figures on screen are cleared, because they belong to the request that was refused | `P-RPT-12` | — |

**Walked to the number, as required.** What they select: a period type (`day` / `week` / `month`) and,
implicitly, an anchor date; optionally one hall inside their own scope. What the query is scoped by:
`st.starts_at >= period_start_utc AND st.starts_at < period_end_utc AND st.screen_id IN scope`, plus
`b.status = 'confirmed'` and `p.state = 'captured'`. What figures appear: takings, occupancy, seats
sold, shows, a per-film table and a per-show listing. In what currency and format: **integer paise on
the wire**, INR, rendered `₹27,833.31` at the edge only. Over what period: a whole calendar day, a
whole ISO week, or a whole calendar month in Asia/Kolkata — **never a partial one**.

**Two things this walk proves are specified and are easy to get wrong.** The window is computed in
Asia/Kolkata and then converted, so a show starting `2026-08-15 00:30 +05:30` lands on Saturday and not
in Friday's takings; and the aggregate occupancy is total sold over total capacity, which is 5.6
percentage points away from the mean of the per-show percentages on this same data.

**Two things a manager reads here that are not settled fact.** Takings are counted on **the date of
the show**, not the date of purchase — `RULED`, and **batched for the client to reverse**, so a future
period already shows money. And sales close 15 minutes **after** the advertised start, which is
`PROVISIONAL` under `OPEN-BOOK-03`, so Friday's takings can still rise for fifteen minutes into
Saturday.

---

## Walk 2 — A manager reads a hall they are not assigned to, and is refused

**Both halves are walked, because only one of them is a test.** `CONSTITUTION.md` Art VI.5 and
`P-RPT-02`'s own test shape say it in terms: *a test asserting only "denied" passes against a query
that returns nothing for anybody.* Steps 1 and 2 are the half that is usually skipped.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-RPT-01` | M assigned `{3, 5}`; captured bookings exist on screen 3 **and** on screen 1 | opens the dashboard for `period=day&date=2026-08-14` | API → Postgres: the aggregate runs with the scope predicate applied in the `WHERE` clause, never as a filter over fetched rows | `system` | **200 with `takings_paise > 0` and `seats_sold > 0`** — a non-empty, non-zero figure for their own hall | `P-RPT-02` · `P-RPT-03` | — |
| 2 | `EP-RPT-01`, no screen — the access-control assertion | M's figure on screen | the same period is read as an administrator | API → Postgres: the identical query with **no** screen filter | `system` | M's `takings_paise` equals screen 3 + screen 5 **exactly** and is **strictly less than** the administrator's. This is the step that stops the suite passing vacuously; step 1 alone passes against a query that ignores the filter | `P-RPT-02` | — |
| 3 | `SCR-RPT-01` hall filter | scope `{3, 5}` | opens the hall filter | client → `EP-RPT-03`: the control's options are the same set the router resolved, from one source | `system` | "All my halls", Hall 3, Hall 5 — and **Hall 1 is not offered at all**. An out-of-service hall would still be offered, marked, and selectable, because excluding it would make its past takings unreadable | `P-RPT-02` | `J-MGR-01` |
| 4 | browser address bar | wants Hall 1 anyway | hand-types `…/dashboard?screen_id=1` | API → router dependency: `{1}` intersected with `{3, 5}` is empty, refused **before the handler exists** | `system` | **403 `FORBIDDEN`**, "That hall is not assigned to this account." | `P-RPT-02` · `P-XCT-05` | `J-MGR-07` |
| 5 | `SCR-RPT-01` Error state | 403 in hand | reads the banner | 403 → `SCR-XCT-01`'s banner replaces the figures; the tabs and the period stepper stay usable so another period can be tried | `page` | a denial that names the relationship rather than the resource, and **no request id**, because the id renders on 5xx only | `P-XCT-11` · `P-RPT-02` | `J-MGR-07` |
| 6 | browser address bar | wants to know which halls exist | hand-types `?screen_id=9`, a hall that does not exist | API → router: a manager receives the **same** 403 whether or not the hall exists; only an administrator ever sees `404 NOT_FOUND` here | `system` | 403 again — the response is not an oracle for which screen ids exist | `P-RPT-02` | — |
| 7 | `SCR-RPT-01` | an administrator removes M's Hall 5 assignment mid-session | refreshes | API → Postgres: `report_scope` now resolves `{5}` removed; if both go, `{}` and the handler short-circuits with no aggregate query and **no `IN ()` predicate** | `system` | 200 with `scope_empty: true` — deliberately **no** distinct "you have been removed" message, because nothing tells the server that an assignment was removed rather than never granted | `P-RPT-08` · `P-RPT-02` | `J-MGR-06` |

**The denial is distinguishable, and the PRD says how.** 403 `FORBIDDEN` with the verbatim string
"That hall is not assigned to this account." is published by `P-RPT-02` and again in `SCR-RPT-01`'s copy
table. It is distinct from the wrong-role 403 ("This page is for managers and administrators.") and
from the administrator's 404 ("That hall does not exist."). **Nothing needed to be filed for a missing
denial.** What was filed is that a second P-row publishes a *different* string for the same condition
(`J-MGR-07`).

**The empty-set trap is specified and is a required negative test.** When the effective scope is
empty the handler short-circuits; it must never build a SQL predicate from an empty list, because an
`IN ()` clause dropped by a query builder produces an unfiltered query and hands a manager with no
assignments the whole cinema's takings.

---

## Walk 3 — A manager tries to write something, anything, and is refused

**The result first, because it is the answer to the question this walk was set:** no privileged write
is reachable by a manager. Every write in the product sits behind `/api/admin`, whose router
dependency admits exactly `{admin}`; the reports router mounts no `POST`, `PUT`, `PATCH` or `DELETE`
route; and `SCR-RPT-01` contains no control that writes and no control that downloads.

**What *is* reachable, and it is not nothing:** the generated `api/contract.json` admits `manager` on
**five non-`GET` endpoints** — `EP-HLD-01`, `EP-HLD-03`, `EP-HLD-04`, `EP-PAY-01` and `EP-TKT-02` —
plus the five public auth `POST`s. None is a *privileged* write, and `S3.6`'s capability matrix grants
a manager hold and pay deliberately. But `P-ADM-17` states flatly that **"a manager writes nothing,
ever"**, and against the contract that sentence is false. Whether a manager may buy a ticket — and
specifically in a hall whose takings they report on — is `OPEN-MGRBOOK-01`, reserved, and it is
**not** decided here (`J-MGR-09`).

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-XCT-05` nav → browser address bar | M believes a figure is wrong; `SCR-RPT-01` offers no correction, no adjustment, no note and no export control, and the shell renders **no admin link at all** for a manager — absent from the DOM, not disabled and not greyed | hand-types `/admin/showtimes` | frontend route → admin router: `GET /api/admin/showtimes` refused by the `{admin}` dependency before any handler runs | `system` | **403 `FORBIDDEN`**, "This page is for administrators. Your account cannot change films, showtimes, prices or halls." Hiding a link is presentation; refusing the request is the control | `P-XCT-05` · `P-ADM-09` · `P-RPT-10` | `J-MGR-08` |
| 2 | direct API call, manager session cookie | wants to correct the base price behind the figure | `PATCH /api/showtimes/101 {"base_price_paise": 30000}` | API → admin router dependency: rejected **before the request body is parsed** — nothing read, nothing validated, nothing locked, nothing enqueued | `system` | 403; `showtime` row 101 unchanged; `audit_log` gains **no** row, because refusals are not audited — only writes are; one structured JSON log line carries the request id, the actor and the refused route | `P-RPT-09` · `P-XCT-03` | `J-MGR-08` |
| 3 | direct API call | wants to cancel a show they can see is empty | looks for a withdraw endpoint and issues one | API → routing: **no such route exists for anybody**, including an administrator. `OPEN-SHOWCANCEL-01` is open and no withdraw capability was invented | `system` | 404 `NOT_FOUND`, "That page does not exist." The absence is specified, not accidental | `P-RPT-09` · `P-XCT-11` | — |
| 4 | direct API call | wants to change the reported figure itself | `POST /api/reports/dashboard` | API → the reports router, which mounts no write method | `system` | **three different documented answers to one request**: `P-RPT-09` says 405 with *no error code from the registry* and the framework's own body; `P-XCT-11` and `api/error_codes.md` say 405 rendered by a global handler in the standard envelope as `METHOD_NOT_ALLOWED`; `P-XCT-05`'s worked example says **404, no such route** | `P-RPT-09` · `P-XCT-11` · `P-XCT-05` | `J-MGR-04` · `J-MGR-05` |
| 5 | seat map → checkout, as an ordinary signed-in user | M holds the `manager` role and a valid session | holds two seats in **Hall 3 — their own hall** — and pays through the simulated provider | API → Redis: hold token with a 3-minute TTL; API → Postgres: booking and payment rows committed under the `(showtime_id, seat_id)` unique constraint | `system` | a booking, made by a manager, whose money now appears **inside the takings figure that manager reports on**. Not a privileged write, and not refused by anything | `P-RPT-03` | `J-MGR-09` |

**Every `—` in the manager column of `S3.6`'s capability matrix is `SRC-003 OPEN-OPS-03` doing its
work**, and this walk confirms each of the three attempts a real person would make from a dashboard —
correcting a figure, cancelling an empty show, editing a showtime's time — has **no surface and no
endpoint**. Step 5 is the exception that is not an exception: it is the customer router, not the
admin router, and the question it raises is already filed.

---

## Walk 4 — A newly created manager with no screen assignment signs in

**The empty dashboard is the correct state for a new account and must not render as an error.** It
does not. What this walk found instead is a gap one layer earlier — nothing in the product tells the
new manager the account exists (`J-MGR-13`) — and a silence in the empty state's own state row
(`J-MGR-06`).

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-06` (administrator's surface) | the administrator is creating manager **P** | submits an email address with `screen_ids: []` — zero is a valid state, because "two per hall" is not a constraint | API → Postgres, one transaction: `user` row with `role='manager'` and **no usable password**, plus an `audit_log` row `manager.created`, and **zero** assignment rows | `system` | an account P cannot sign into and has not been told about. No outbox row is written and no SES message is sent | `P-ADM-17` · `P-XCT-03` | `J-MGR-13` |
| 2 | `SCR-ACC-02` `/account/reset` | P has learned of the account out of band — the PRD specifies no mechanism | requests a reset for their address | API → Postgres + the transactional outbox in one transaction; worker → SES sends the link | `process` | a single-use link that expires in 30 minutes, the number rendered from `PASSWORD_RESET_TTL_SECONDS` and never typed | `P-ACC-07` | `J-MGR-13` |
| 3 | `SCR-ACC-03` `/account/reset/confirm` | holding the token | sets a password | API → Postgres, one transaction: `used_at` set by a conditional update that must affect exactly one row, `password_hash`, `password_version + 1`, and `last_signed_in_at` — **this path is the only way a manager account created by an administrator ever signs in for the first time** | `system` | a fresh session cookie carrying the new `pv`; signed in as a manager | `P-ACC-08` | — |
| 4 | `SCR-XCT-05` nav → `SCR-RPT-01` | signed in, zero assignments | follows `Dashboard` — the manager's nav is exactly two links, `Dashboard` and `My bookings` | listing → `/dashboard` | `page` | `SCR-RPT-01` in its Loading state | `P-XCT-05` | — |
| 5 | `SCR-RPT-01` | Loading | the opening request `GET /api/reports/dashboard?period=day` | API → router: `report_scope` resolves an empty set and the handler **short-circuits**; no aggregate query runs at all | `system` | **200**, not 403, not 404, not 500: `scope_empty: true`, `screen_ids: []`, `shows: 0`, `seats_sold: 0`, `capacity: 0`, `takings_paise: 0`, `occupancy_pct: null`, `films: []` | `P-RPT-08` · `P-RPT-02` | — |
| 6 | `SCR-RPT-01`, **Empty — no halls assigned** | 200 in hand | reads the screen | 200 → the empty state: period tabs live, all four figures render `—`, the occupancy bar absent, both tables absent, one line: *"No halls are assigned to this account. Ask an administrator to assign one."* | `page` | a correct empty state — **no danger surface, no danger ink, no error banner, no `role="alert"`**. Rendering `₹0.00` here would be a claim about the business when it is a fact about the account | `P-RPT-08` | `J-MGR-06` |
| 7 | `SCR-RPT-01` | the administrator assigns P to Hall 4, which has showtimes today but sold nothing | P refreshes | API → Postgres: scope `{4}`, `capacity > 0`, `seats_sold = 0` | `system` | Takings `₹0.00`, Seats sold `0`, **Occupancy `0.0 %` with its bar at zero width**, Shows the real count, and *"No seats were sold in this period."* — **a zero is a fact** | `P-RPT-08` · `P-RPT-04` | — |
| 8 | `SCR-RPT-01` period stepper | reading Hall 4 | presses `Previous day`, landing on a day with no showtimes at all on Hall 4 | `time`: the anchor moves by one whole period, never producing a partial one; `capacity(P) = 0` so the division is undefined | `time` | Takings `₹0.00`, **Occupancy `—`, never `0.0 %`**, and *"No shows were scheduled in this period."* Rendering `0.0 %` would claim the halls were empty when in fact nothing was scheduled | `P-RPT-08` · `P-RPT-04` | — |

**The PRD does specify the empty state, and it specifies more than the prompt asked for: three zeros,
not two.** Steps 6, 7 and 8 are three different states which `P-RPT-08` requires to render three
different ways, and `SCR-RPT-01`'s states table publishes all three with their own copy. The
difference between "no assignment" and "assigned but zero sales today" is carried on the wire by
`scope_empty` as its own boolean, rather than being inferred from zeros — which is what makes the
distinction implementable rather than aspirational. **The third state, a period with no showtimes at
all, is the one `COMPONENTS.md §10` does not name**, and `P-RPT-08` adds it explicitly rather than
collapsing it into the second.

**What the empty state does not specify** is whether the scope line and the hall filter render at all
when the scope is empty, and no scope-line string is published for that case — the two published forms
are "Halls shown: Hall 3, Hall 5." and "Halls shown: every hall." (`J-MGR-06`). This is the same class
of defect `P-RPT-02` closed for the administrator, whose `[]` would have rendered `Halls shown:` with
nothing after it; the manager half of it is still open.

---

## Walk 5 — A manager assigned today opens the dashboard · `OPEN-RPTSCOPE-01`

> **`OPEN-RPTSCOPE-01` is `OPEN` and reserved: access to financial data.** `CONSTITUTION.md` X.0b.
> **Nothing below decides it.** The PRD specifies the behaviour that follows from `FR-ADR-011` as
> written — current assignment, all history — and deliberately did not invent a validity window,
> because adding start and end dates to `manager_screen_assignment` would change an `APPROVED` ADR's
> table shape. This walk records what happens and what the documents cannot answer.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-06` | Hall 3's previous manager has left; manager **Q** is created and assigned Hall 3 today, 2026-08-14 | the administrator submits the complete screen set | API → Postgres: one `manager_screen_assignment` row plus an `audit_log` row `manager.screen_assigned`. **The row carries no validity period — no start date, no end date** | `system` | an assignment that is a statement about now and says nothing about when | `P-ADM-17` | `J-MGR-12` |
| 2 | `SCR-RPT-01` | Q signed in, scope `{3}` | selects `Month` | `time`: `[2026-07-31T18:30:00Z, 2026-08-31T18:30:00Z)` | `time` | August's takings and occupancy for Hall 3 **in full**, including the fortnight before Q's account existed | `P-RPT-01` · `P-RPT-02` | `J-MGR-12` |
| 3 | `SCR-RPT-01` period stepper | reading August | presses `Previous month` repeatedly | `time`: the anchor moves back with **no lower bound** — `P-RPT-01` places none, because nothing is ever deleted and inventing a retention window would create a silent data cliff | `time` | every month since the system started, with real money figures, for a hall Q was assigned to this morning | `P-RPT-01` | `J-MGR-12` |
| 4 | `SCR-RPT-01` period stepper | reading the past | presses `Next month`, past today | `time`: a **future** anchor is legitimate and returns real figures, because takings are attributed to the date of the show and next month's tickets are already paid for | `time` | next month's advance sales; every per-show row carries `has_started: false` and renders "Still selling" | `P-RPT-01` · `P-RPT-03` · `P-RPT-06` | — |
| 5 | `SCR-RPT-01` | the administrator unassigns Q from Hall 3 tomorrow | Q opens the dashboard | API → Postgres: the assignment row is **genuinely deleted** — it is current state, not the historical record, and the `manager.screen_unassigned` audit row is what carries the history | `system` | the empty-scope state. Last month's figures Q was reading yesterday are gone, and no message says why — deliberately, because nothing tells the server that an assignment was removed rather than never granted | `P-RPT-08` · `P-RPT-02` | `J-MGR-12` · `J-MGR-06` |

### What the documents cannot answer — recorded, not decided

1. **May a manager assigned today read periods before their assignment existed?** As specified, yes,
   with no bound. No frozen source, no client ruling and no `APPROVED` record says otherwise.
2. **Should removal from a hall take away read access to periods already read?** As specified, yes,
   immediately and silently. Nothing states whether that is intended.
3. **Should the assignment carry a validity window at all?** `FR-ADR-011` is `APPROVED` and models it
   without one; changing that is an ADR change and not a PRD change.
4. **A manager's own future-period access is a second, quieter half of the same question.** Steps 3
   and 4 differ in direction and not in kind: both are "how far may this account see", and only the
   backward half is filed.

**All four are `OPEN-RPTSCOPE-01`. The class is reserved — access to financial data — so the build
session may not close any of them at any confidence.**

---

## Walk 6 — A showtime is edited after bookings exist · `OPEN-RPTIMMUT-01`

> **`OPEN-RPTIMMUT-01` is `OPEN` and reserved: reporting integrity.** `CONSTITUTION.md` X.0b.
> **Nothing below decides it.** Two remedies exist and both belong to other lanes — refuse the edit
> once bookings exist, which is an administration write path, or snapshot `movie_id` onto the booking,
> which is a data-model change. This walk records what the manager sees before and after.

Continuing walk 1's data: ST-101 on Hall 3, Friday 14 August, `DEMO MOVIE 01`, 97 seats sold, 64.7 %,
2 483 331 paise; the day's headline is 2 783 331 paise and 29.5 % across two shows.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-RPT-01` | M reading Friday 14 August | reads the per-film table and the per-show row for ST-101 | API → Postgres: the aggregate runs live inside the request; nothing is precomputed and nothing is cached, because a cached report is a stale report a manager will act on | `system` | `DEMO MOVIE 01` — 2 shows, 109 seats, 29.5 %, ₹27,833.31; ST-101 at 64.7 % and ₹24,833.31 | `P-RPT-03` · `P-RPT-04` · `P-RPT-06` · `P-RPT-12` | — |
| 2 | `SCR-ADM-03` (administrator's surface) | ST-101 already carries 97 sold seats | corrects the film to `DEMO MOVIE 02` and submits with `version` | API → Postgres, one transaction: version compared, the overlap check re-run excluding this row, the change applied, `version` incremented, `audit_log` row `showtime.updated` inserted | `system` | a booked showtime whose `movie_id` has changed. `seat_count_at_creation` is **deliberately not recomputed**, and the seat set is **deliberately not rewritten** — both because recomputing them would change last month's reported occupancy | `P-ADM-09` · `P-XCT-03` | `J-MGR-10` |
| 3 | `SCR-RPT-01` | M reloads the same period | presses the same `Day` tab | API → Postgres: `P-RPT-05` reaches the film as `showtime.movie_id → movie`, joined **live at read time** and never snapshotted | `system` | the per-film table now holds **two** rows where it held one; 97 seats and 2 483 331 paise have moved from `DEMO MOVIE 01` to `DEMO MOVIE 02` for a period already reported and already acted on | `P-RPT-05` | `J-MGR-10` · `J-MGR-11` |
| 4 | `SCR-ADM-03` | the same booked showtime | moves it from 19:30 Friday to 00:30 Saturday — `starts_at` becomes `2026-08-14T19:00:00Z` | API → Postgres: `starts_at` updated. The sales cut-off re-derives automatically, because it is computed at evaluation time and never stored | `time` | a showtime that has left Friday's window and entered Saturday's | `P-ADM-09` · `P-RPT-01` | `J-MGR-10` |
| 5 | `SCR-RPT-01` | M reloads Friday | reads the headline | `time`: the period filter reads `starts_at` live, and `19:00:00Z` is **not** less than `18:30:00Z`, so ST-101 is no longer in Friday | `time` | Friday's takings fall by 2 483 331 paise to 300 000, and Friday's occupancy falls from 29.5 % to 5.5 %. `R-RPT-04` requires reported figures not to move. They moved | `P-RPT-01` · `P-RPT-03` · `P-RPT-04` | `J-MGR-10` |
| 6 | `/dashboard/audit` | M wants to know why the number changed | hand-types the route, because **no `Change log` link exists in a manager's DOM at all** | frontend route → reports router: `EP-RPT-04` narrows to `admin` alone; the manager is refused before the handler runs | `page` | 403 `FORBIDDEN` and the whole panel replaced by one line, *"This page is for administrators."* — no filters, no empty list, nothing implying a different query would work. **The manager has no surface anywhere that can explain the change** | `P-RPT-11` | `J-MGR-11` |

**What the manager sees before and after, stated plainly.** Before: a per-film table with one film and
a day headline of ₹27,833.31 at 29.5 %. After two administrator edits that the PRD explicitly permits
on a showtime with bookings: a per-film table with two films, and a day headline of ₹3,000.00 at
5.5 % — for a period that had already been read, reported and acted on. Nothing was wrong with either
figure at the moment it was computed. `P-RPT-12` is the reason both are honest and the reason neither
is stable: every figure is recomputed from stored rows on every request.

**`P-ADM-09` states that "editing a showtime that already has bookings is permitted and changes
nothing about them."** That sentence is true of the bookings and false of the reports, and the row
protects `seat_count_at_creation` for exactly the reason it leaves `movie_id` and `starts_at`
unprotected (`J-MGR-10`).

### What the documents cannot answer — recorded, not decided

1. **May an administrator edit a booked showtime's film or start time at all?** `P-ADM-09` says yes;
   `R-RPT-04` says reported figures must not move. Both are `RULED` and they cannot both hold.
2. **If the edit is permitted, should the report snapshot the film and the period the way it already
   snapshots the price and the seat count?** That is a data-model decision, not a reporting one.
3. **What should the manager see when a figure they reported yesterday is different today?** Nothing
   in the PRD answers this, and the one surface that records who changed what is administrator-only.

**Items 1 and 2 are `OPEN-RPTIMMUT-01`, reserved: reporting integrity. Item 3 is filed here as a new
PRD gap (`J-MGR-11`), because it survives whichever way the client rules item 1.**

---

## Coverage note

Twelve of the twelve `P-RPT` rows are exercised. Four `P-XCT` rows (`02` money, `03` audit, `05`
authorisation, `11` the error envelope), three `P-ACC` rows (`02`, `07`, `08`) and two `P-ADM` rows
(`09`, `17`) are exercised where a manager's walk crosses them. **21 distinct P-rows, every one of
which was read in full in its own section before being cited.** No `P-BRW`, `P-SEA`, `P-HLD`, `P-PAY`
or `P-TKT` row is cited: walk 3 step 5 crosses the booking path, but this lane read the `P-RPT-03`
side of that crossing and not the booking rows themselves, so it cites only what it read.
