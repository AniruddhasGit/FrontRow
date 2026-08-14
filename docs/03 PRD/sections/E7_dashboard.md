# E7 — The manager and admin dashboard

This epic is the reporting surface. A manager or an administrator signs in and reads three figures —
takings, occupancy, and per-film performance — for a whole calendar day, a whole ISO week, or a whole
calendar month, in Asia/Kolkata. A manager reads the halls they are assigned to. An administrator
reads every hall, and only an administrator can also read the change log that records who altered a
price, published a film, or configured a hall. Nothing on this surface writes anything, and nothing on
this surface produces a file. This is **Phase 8, the last phase** (`SRC-003 OPEN-SCOPE-01`,
`SRC-002 §E E-3`), so every table it reads already exists and is already populated by the time this
epic starts.

The one thing that will be got wrong is the **period boundary**. Every figure on this screen is a sum
over a time window, and the window has to be computed in Asia/Kolkata and then converted to UTC before
it touches a `timestamptz` column. A boundary taken in UTC — which is what a container in AWS will do
if nobody stops it — moves the window by five and a half hours, so "today's takings" starts and ends
at half past five in the morning and a late show lands on the wrong date. The second thing that will
be got wrong is quieter: an aggregate occupancy computed as the **mean of the per-show percentages**
instead of as total seats sold over total capacity. Both produce a number that looks plausible, and a
manager will act on it. `P-RPT-01` and `P-RPT-04` each carry a worked example with the expected answer
for exactly this reason.

**Three things this epic rests on are not settled facts.** The manager role itself is `PROVISIONAL`
(`SRC-003 C-1`) — one message from the client removes it and this whole surface becomes an
admin-only screen filtered by hall. One cinema with six screens is `PROVISIONAL` (`SRC-003 C-2`), and
manager scoping attaches to the **screen**, not the cinema. Hall sizes are `ASSUMED`
(`SRC-003 OPEN-SCALE-02`) — every occupancy percentage in this document divides by an assumed
denominator, and the shape of the formula is what is specified, never the example number.

---

## S4 — Product specifications

### `P-RPT-01` · Compute the period boundary in Asia/Kolkata, then convert to UTC · `RULED`
`[SRC: SRC-003 OPEN-REPORT-01 · SRC-003 OPEN-SCOPE-01 · SRC-003 OPEN-LOCALE-01 · FR-ADR-043 · FR-ADR-018]`
`[BRD: R-RPT-01]`

**Behaviour.** Every dashboard request names a **period type** — `day`, `week` or `month` — and an
**anchor date**. The server computes the whole calendar period containing that anchor date in
Asia/Kolkata, converts both edges to UTC instants, and every query in this epic uses that pair. The
interval is **half-open**: `starts_at >= period_start_utc AND starts_at < period_end_utc`.

**Who may do it.** manager, admin. Enforced by the router dependency in `P-RPT-02`, which is mounted
on the router and therefore applies to every route on it including any route added later.

**Preconditions.**
- The cinema row carries its IANA zone name, `Asia/Kolkata` (`FR-ADR-018`). The zone is read from the
  cinema row, never from a global constant and never from the container's local time.
- A clock is injected. The default anchor date is "today in Asia/Kolkata" computed from the injected
  clock. **Nothing in this epic calls the system clock.** A test that reads the wall clock is a defect.

**Happy path.**
1. Read `period` and `date` from the query string. If `date` is absent, take the current instant from
   the injected clock, convert it to Asia/Kolkata, and use that local date.
2. Compute the local period, as a pair of local midnights in Asia/Kolkata:
   - `day` — the anchor date at 00:00, to the next date at 00:00.
   - `week` — the **Monday** on or before the anchor date at 00:00, to the following Monday at 00:00.
     ISO-8601, Monday-first (`FR-ADR-043`).
   - `month` — the first of the anchor's month at 00:00, to the first of the following month at 00:00.
     A calendar month, never a rolling thirty days.
3. Convert both local midnights to UTC instants through the zone database using the stored zone name.
4. Return the pair alongside every figure, so the number can be reproduced from the response alone.

**Two kinds of instant appear on this surface and they are serialised differently on purpose.**

| Kind | Fields | Serialisation |
|---|---|---|
| **A rendered instant** — something a reader sees as a wall-clock time | `starts_at` (`EP-RPT-02`), `occurred_at` (`EP-RPT-04`) | ISO-8601 **with the cinema's offset**, `2026-08-14T19:30:00+05:30`, as every customer-facing endpoint does (`P-BRW-06`). **The client never converts.** |
| **A boundary instant** — the window the figures were computed over | `period_start_utc`, `period_end_utc`, `window_start_utc`, `window_end_utc`, `evaluated_at_utc` | **Bare UTC, and the `_utc` suffix says so.** Nothing renders these as a clock time; they exist so a reader can reproduce the figure from the response alone. |

**The suffix is the tell, and it is load-bearing rather than decorative.** A field named `_utc` is a
boundary and is never rendered; a field without it is rendered and carries the offset. **That is why
`starts_at_utc` and `occurred_at_utc` were renamed** — they were rendered fields wearing a boundary's
name, and both screens were reading a wall-clock time off them with no offset to read it against.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `period` is absent or is not one of `day`, `week`, `month` | 422 `VALIDATION_FAILED` | "Choose day, week or month." |
| 2 | `date` is present but is not an ISO-8601 calendar date | 422 `VALIDATION_FAILED` | "The date must be written as YYYY-MM-DD." |
| 3 | `date` is a well-formed but impossible date, for example `2026-02-30` | 422 `VALIDATION_FAILED` | "That date does not exist." |
| 4 | No token, or an expired token | 401 `AUTH_REQUIRED` | "Sign in to see the dashboard." |
| 5 | The caller is a guest or a customer | 403 `FORBIDDEN` | "This page is for managers and administrators." |

**Server-side validation.**

| Field | Type and bound | On failure |
|---|---|---|
| `period` | string, exactly one of `day` \| `week` \| `month`. Required. | 422 `VALIDATION_FAILED`, row 1 |
| `date` | string, ISO-8601 calendar date `YYYY-MM-DD`, interpreted in Asia/Kolkata. Optional; defaults to today from the injected clock. | 422 `VALIDATION_FAILED`, rows 2 and 3 |

**No upper or lower bound is placed on `date`.** Nothing is ever deleted (`SRC-003 OPEN-OPS-02`,
`FR-ADR-012`), so every past date is a legitimate anchor. A **future** anchor is also legitimate and
returns real figures, because takings are attributed to the date of the show and a ticket for next
Friday has already been paid for — see `P-RPT-03`.

**Worked example.** Required, and it is the reason this row exists.

Inputs: injected clock = `2026-08-14T12:50:00Z`. Cinema zone = `Asia/Kolkata`, fixed offset `+05:30`,
no daylight saving. Anchor date not supplied.

- Local evaluation instant: `2026-08-14 18:20:00 +05:30`, a **Friday**. Default anchor = `2026-08-14`.

| Period | Local window (Asia/Kolkata) | UTC window used in the query |
|---|---|---|
| `day` | `2026-08-14 00:00:00` → `2026-08-15 00:00:00` | `2026-08-13T18:30:00Z` → `2026-08-14T18:30:00Z` |
| `week` | `2026-08-10 00:00:00` → `2026-08-17 00:00:00` | `2026-08-09T18:30:00Z` → `2026-08-16T18:30:00Z` |
| `month` | `2026-08-01 00:00:00` → `2026-09-01 00:00:00` | `2026-07-31T18:30:00Z` → `2026-08-31T18:30:00Z` |

All three end instants are **exclusive**.

**The failure this prevents, with the same numbers.** A showtime starting at `2026-08-15 00:30 +05:30`
is `2026-08-14T19:00:00Z`. Its local date is Saturday the 15th. If the day window were taken in UTC —
`2026-08-14T00:00:00Z` → `2026-08-15T00:00:00Z` — that showtime falls inside it, and Saturday's first
show is counted in Friday's takings. With the boundary computed above, `19:00:00Z` is not less than
`18:30:00Z`, so it correctly belongs to Saturday.

---

### `P-RPT-02` · Resolve the caller's screen scope once, on the router · `PROVISIONAL`
`[SRC: SRC-003 C-1 · SRC-003 C-2 · SRC-003 OPEN-SCOPE-01 · SRC-003 OPEN-OPS-03 · SRC-001 §4.4 · SRC-001 §7.4 · FR-ADR-009 · FR-ADR-010 · FR-ADR-011]`
`[BRD: R-RPT-03]`

**Status is `PROVISIONAL` because the manager role is.** `SRC-003 C-1` reconciles two of the client's
own answers and records the rejected three-role reading. If the client reverses it, this row's screen
filter is deleted and the dashboard is served to administrators only.

**Behaviour.** Authorisation is applied **once, on the router, as a dependency**. The dependency
resolves the caller's assigned screen ids and hands the handler a resolved scope object. **No handler
reads a screen id from the request and checks it for itself.**

**Who may do it.** manager, admin. guest and customer are refused before any handler runs.

**Preconditions.**
- `manager_screen_assignment` exists, one row per `(manager user, screen)`, unique on the pair
  (`FR-ADR-011`).
- "Two managers per hall" is an **observation of the client's current staffing, not a constraint**
  (`FR-ADR-011`). No check constraint, no trigger and no application rule enforces the number two, and
  nothing in this epic assumes it. A hall may have one manager, three, or none.

**Happy path.**
1. The reports router is mounted with a role dependency admitting exactly `{manager, admin}`. It runs
   for every route on the router. A route added to this router later inherits it without anyone
   remembering to add it.
2. A second dependency, `report_scope`, runs after it and returns:
   - **admin** → `screen_ids = None`, meaning *no screen filter is applied at all*. An administrator's
     scope does not come from assignment rows; it comes from the role (`FR-ADR-011`). **`None` is an
     internal value and never reaches the wire** — see below.
   - **manager** → `screen_ids = ` the frozen set of `screen_id` values from
     `manager_screen_assignment` for that user. **Possibly empty.**
3. If the request carries the optional `screen_id` narrowing parameter, a third dependency intersects
   it with the resolved scope and produces the **effective scope**. It never widens. A `screen_id` a
   manager does not hold is refused here, before the handler exists.
4. Every query in this epic takes the effective scope as a parameter and applies it as a filter.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No token, or an expired token | 401 `AUTH_REQUIRED` | "Sign in to see the dashboard." |
| 2 | The caller's role is `guest` or `customer` | 403 `FORBIDDEN` | "This page is for managers and administrators." |
| 3 | A manager passes `screen_id` for a hall they are not assigned to — **whether or not that hall exists** | 403 `FORBIDDEN` | "That hall is not assigned to this account." |
| 4 | An admin passes a `screen_id` that does not exist | 404 `NOT_FOUND` | "That hall does not exist." |
| 5 | A manager's resolved scope is empty | **200**, not an error | see `P-RPT-08` |

**Row 3 and row 4 differ on purpose.** A manager receives the same 403 for a hall that exists and one
that does not, so the response is not an oracle for which screen ids exist. An administrator sees
every hall anyway, so a 404 discloses nothing to them.

**`screen_ids` on the wire carries the halls the response actually covers — for an administrator,
every screen — and the internal `None` is never serialised.** The resolver's `None` means *apply no
filter*, which is a statement about a SQL predicate. The response field answers a different question,
*which halls am I looking at*, and for an administrator the honest answer is a list of all six, not an
absence.

**`[]` therefore means exactly one thing: a manager with no assignment**, whose response covers
nothing (`P-RPT-08`). That is what makes the field readable at all.

> **This overturns the earlier reading**, under which an administrator emitted `[]` for "no filter".
> `[]` was then **byte-identical** to an unassigned manager's response while meaning its opposite —
> every hall against no hall — and `SCR-RPT-01`'s scope line, which renders `Halls shown: {names}`,
> would have rendered **nothing at all** for the one caller who can see everything. Two opposite
> states must not share a wire value.

**An out-of-service hall stays in scope, and it is offered in the hall filter.** A screen withdrawn
from service (`P-ADM-16`) keeps every showtime, booking and payment it ever had, and `P-ADM-16`
already rules that it *"still appears wherever a dashboard figure names it"*. **Excluding it would
make a retired hall's past takings unreadable** — last month's figures would silently shrink the day
the hall was withdrawn, and `R-RPT-04` requires reported figures not to move. That is a reporting
integrity problem, not a tidiness one, and tidiness is the only thing exclusion would buy.

It is included for **managers and administrators alike**, on the same rule: a manager assigned to a
hall that is later withdrawn keeps reading it. **It is marked as out of service where it is offered**
— `SCR-RPT-01`'s hall filter renders the suffix — so a reader who selects it and finds no future
showtimes knows why, rather than reading an empty period as a broken filter. **The mark is a label,
not a filter**: the option stays selectable and the figures are unchanged.

**`EP-RPT-03` was already right and is left alone**, which is worth saying so the two are visibly
consistent rather than accidentally different: it carries `all_halls: true` for an administrator
**and** the full `screens` array, so it never had this ambiguity. `EP-RPT-01`'s `screen_ids` now agrees
with it — the same halls, named the same way, from the same resolver.

**Server-side validation.**

| Field | Type and bound | On failure |
|---|---|---|
| `screen_id` | integer, positive, optional. Must be a member of the resolved scope for a manager; must exist for an admin. | 422 `VALIDATION_FAILED` if not a positive integer; 403 `FORBIDDEN` or 404 `NOT_FOUND` per rows 3 and 4 |

**The empty-set trap, and the rule that closes it.** When the effective scope is an empty set, the
handler **short-circuits and returns the empty-scope response without running any aggregate query.**
It must never build a SQL predicate from an empty list. An `IN ()` clause dropped by a query builder
produces an unfiltered query, and an unfiltered query hands a manager with no assignments the whole
cinema's takings. This is a required negative test, not a stylistic preference.

**The test shape this row must satisfy** (`CONSTITUTION.md` Art VI.5, `FR-ADR-011`):

1. Seed manager **M** assigned to screen 3 only. Seed captured bookings on screen 3 **and** on screen 1.
2. `GET /api/reports/dashboard?period=day&date=2026-08-14` as M returns **200** with
   `takings_paise > 0` and `seats_sold > 0` — a **non-empty, non-zero** result for their own hall.
3. The same response's `takings_paise` **equals screen 3's figure exactly** and is **strictly less
   than** an administrator's figure for the same period. This step is what stops the test passing
   vacuously — step 2 alone passes against a query that ignores the filter.
4. The same request with `&screen_id=1` as M returns **403 `FORBIDDEN`**.
5. An administrator's response for the same period includes both screens.
6. A manager with **no** assignments returns **200** with `scope_empty: true` and zero figures —
   **not 403, and not the whole cinema's figures.**

**A test asserting only step 4 passes against a dashboard that returns nothing for anybody.** Steps 2,
3 and 6 are not optional.

---

### `P-RPT-03` · Takings are money actually captured, counted on the date of the show · `RULED` · **batched for the client to reverse**
`[SRC: SRC-001 §5.5.2 · SRC-001 §2.4 · SRC-001 §7.6 · SRC-003 OPEN-REPORT-01 · SRC-003 OPEN-LOCALE-01 · FR-ADR-043 · FR-ADR-039 · FR-ADR-041 · FR-ADR-036]`
`[BRD: R-RPT-02 · R-RPT-04]`

**Behaviour.** The takings figure for a period is the sum of the **snapshotted per-seat prices** of
every seat on a confirmed booking whose payment reached `captured`, for every showtime whose
`starts_at` falls inside the period and whose screen is inside the effective scope.

**Who may do it.** manager (own halls), admin (all halls), via the router dependency in `P-RPT-02`.

**Preconditions.**
- `booking_seat.price_paise` is the price snapshotted at confirmation and is never recomputed
  (`FR-ADR-039`). The figure is summed from it, never from a current base price times a current uplift.
- `payment.state` is one of `pending`, `authorized`, `captured`, `failed` (`FR-ADR-041`).
- Money is an integer number of paise. Currency INR, minor-unit ratio **100**, held as a named
  configuration value (`FR-ADR-036`). **No float appears anywhere in this path**, including the JSON.

**Happy path — the formula.**

```
takings_paise(period, scope) =
  COALESCE(SUM(booking_seat.price_paise), 0)
  FROM showtime st
  JOIN booking b        ON b.showtime_id = st.id
  JOIN payment  p       ON p.id          = b.payment_id
  JOIN booking_seat bs  ON bs.booking_id = b.id
  WHERE st.starts_at >= period_start_utc
    AND st.starts_at <  period_end_utc
    AND (scope.screen_ids IS NULL OR st.screen_id IN scope.screen_ids)
    AND b.status = 'confirmed'
    AND p.state  = 'captured'
```

**Four things in that statement are load-bearing.**

1. **`COALESCE(..., 0)`.** `SUM()` over an empty set returns `NULL`, not zero. Without the coalesce a
   period with no sales renders as an absent figure rather than as `₹0.00`, and a zero is a fact
   (`COMPONENTS.md §10`).
2. **The `SUM()` is cast back to an integer type in the query.** `SUM()` over a `bigint` column
   returns `numeric`, which arrives in Python as `Decimal` and either fails to serialise or mixes
   badly with `int`. `GOTCHAS.md` records this and this is the query where it bites.
3. **`p.state = 'captured'`.** Held seats contribute nothing — a hold is not revenue and counting it
   would make the figure move as customers browse. A booking whose payment failed contributes nothing.
4. **`b.status = 'confirmed'`.** In v1 no code path sets any other booking status
   (`FR-ADR-013` keeps `status` and `cancelled_at` in the schema with no endpoint exposing them), so
   this predicate is currently redundant. It is written anyway so the definition survives unchanged if
   `OPEN-SHOWCANCEL-01` ever closes.

**The response returns `takings_paise` as a JSON integer.** Never a float, never a formatted string.
Formatting to `₹27,833.31` happens at render time only (`FR-ADR-036`). A month's takings for one
cinema stays many orders of magnitude below 2^53, so a JSON number is safe here.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The aggregate query fails or times out | 500 `INTERNAL_ERROR` | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |
| 2 | Redis is unreachable, so the rate limiter cannot be evaluated | 503 `DEPENDENCY_UNAVAILABLE` | "The dashboard cannot be loaded right now. A service it depends on is unreachable." |
| 3 | The per-user rate limit is exhausted | 429 `RATE_LIMITED`, with `Retry-After` | "Too many requests. Try again in 1 second." — singular; the arithmetic is in `P-RPT-12` |

The request id is shown on the 5xx only, never on a 4xx (`FR-ADR-052`).

**Server-side validation.** All inputs are `P-RPT-01`'s `period` and `date` plus `P-RPT-02`'s
`screen_id`. This row adds no field of its own.

**Worked example.** All example inputs; none is a configured value.

Fixed inputs:
- Injected clock `2026-08-14T12:50:00Z`. `period=day`, anchor `2026-08-14`. UTC window
  `[2026-08-13T18:30:00Z, 2026-08-14T18:30:00Z)` from `P-RPT-01`.
- Manager **M** assigned to screen 3 and screen 5. Manager **N** assigned to screen 1.
- Base price `25000` paise (₹250.00). Uplifts: Standard `0` basis points, Premium `3333`.
- Per-seat price by `FR-ADR-038`: `(base * (10000 + uplift_bp) + 5000) // 10000`.
  - Standard: `(25000 * 10000 + 5000) // 10000` = **25000** paise.
  - Premium: `(25000 * 13333 + 5000) // 10000` = `333330000 // 10000` = **33333** paise.

Showtimes:

| Showtime | Screen | `starts_at` (UTC) | Local (Asia/Kolkata) | In the Friday window? |
|---|---|---|---|---|
| ST-101 | 3 | `2026-08-14T14:00:00Z` | Fri 14 Aug 19:30 | yes |
| ST-102 | 5 | `2026-08-14T18:15:00Z` | Fri 14 Aug 23:45 | yes — `18:15 < 18:30` |
| ST-103 | 1 | `2026-08-14T14:00:00Z` | Fri 14 Aug 19:30 | yes, but outside M's scope |
| ST-104 | 3 | `2026-08-14T19:00:00Z` | Sat 15 Aug 00:30 | **no** — `19:00 >= 18:30` |

Sales:
- ST-101 — 90 Standard and 7 Premium on captured bookings: `90 × 25000 = 2,250,000` plus
  `7 × 33333 = 233,331` = **2,483,331** paise. Also one booking of 3 seats whose payment is `failed`
  (contributes 0) and one live 2-seat hold that never became a booking (contributes 0).
- ST-102 — 12 Standard on captured bookings: `12 × 25000` = **300,000** paise.
- ST-104 — 40 seats sold. Excluded from Friday; counted on Saturday.

**Expected answer.** Day takings for manager M on 2026-08-14 =
`2,483,331 + 300,000` = **2,783,331 paise**, rendered `₹27,833.31`.

The booking total is the sum of already-rounded per-seat prices and is **never rounded again**
(`FR-ADR-038`); the period total is a sum of those, so it inherits the same property.

**The reading that is batched for the client to reverse.** A show's takings are counted against **the
date of the show**, not the date of purchase. A ticket bought on Monday for Friday's show is Friday's
takings, because the manager is reading how each show performed and `SRC-001 §5.5.2` asks for revenue
**per show**. **An accountant would reasonably want it counted on Monday**, the date the money moved.
That is the other defensible answer, it is a money definition, and **the client owns which one applies**
(`R-RPT-04`, `FR-ADR-043`). It is reversible at no data cost: every figure is recomputed from stored
rows on every request, so changing the definition changes the report and rewrites nothing.

**Two consequences of the showtime-date reading, both stated rather than hidden.**

*A future period already shows money.* Asking for `period=day&date=2026-08-21` a week early returns
the takings already captured for that day's shows. That is correct under this definition and it is
the single clearest illustration of what the client is being asked to confirm.

*A finished day's takings can still rise, briefly.* Sales close at the advertised start **plus 15
minutes** (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042` — and that direction is itself `PROVISIONAL`).
Worked: ST-105 on screen 3 starts `2026-08-14T18:20:00Z` (Fri 23:50 local), so its cut-off is
`2026-08-14T18:35:00Z` (Sat 00:05 local). A payment captured at `2026-08-14T18:33:00Z` — three minutes
into Saturday — attaches to a showtime whose local date is Friday, and **Friday's takings increase
after Friday ended.** The effect is bounded: Friday's figure is final at Friday's last showtime's
`starts_at` plus the configured offset, not at midnight. Under the alternative reading of
`OPEN-BOOK-03` — 15 minutes *before* the start — the effect disappears entirely.

---

### `P-RPT-04` · Occupancy divides by the seat count recorded when the showtime was created · `RULED`
`[SRC: SRC-001 §5.5.2 · SRC-001 §3.5 · SRC-001 §2.4 · SRC-003 OPEN-REPORT-01 · FR-ADR-043 · FR-ADR-022]`
`[BRD: R-RPT-02 · R-RPT-04]`

**Behaviour.** Occupancy is seats sold over capacity, expressed as a percentage to one decimal place.
The denominator is **`showtime.seat_count_at_creation`** — the seat count as it was when that showtime
was created — so retiring a seat next month never changes last month's figure.

`seat_count_at_creation` is the size of the showtime's seat set, materialised when the showtime was
created; `P-ADM-14` owns that rule and this row does not restate it. **Occupancy therefore cannot
exceed 100 %**: the numerator counts sold seats out of the same set the denominator counts.

**Who may do it.** manager (own halls), admin (all halls), via `P-RPT-02`.

**Preconditions.**
- Every showtime row carries `seat_count_at_creation`, an integer, set at creation and never updated
  (`FR-ADR-022`).
- The denominator is **never** computed live from `SELECT count(*) FROM seat WHERE screen_id = …`, and
  never from `seat.is_active`. A seat taken out of service is flagged inactive, not deleted, and it is
  excluded from **future** showtimes' creation counts only (`FR-ADR-022`).

**Happy path — the formulas.**

*Numerator, for one showtime:*
```
seats_sold(st) = COUNT(booking_seat rows)
  joined as in P-RPT-03, with the same b.status = 'confirmed' and p.state = 'captured' predicates
```

*Per showtime:*
```
capacity(st)          = st.seat_count_at_creation
occupancy_tenths(st)  = (seats_sold(st) * 2000 + capacity(st)) // (2 * capacity(st))
occupancy_pct(st)     = occupancy_tenths(st) / 10      # rendered, one decimal place
```

*For a period, or for a film, or for the whole scope — capacity-weighted:*
```
seats_sold(P)         = SUM(seats_sold(st))              over every showtime in P and in scope
capacity(P)           = SUM(st.seat_count_at_creation)   over the SAME set of showtimes
occupancy_tenths(P)   = (seats_sold(P) * 2000 + capacity(P)) // (2 * capacity(P))
```

**Three rules that are not obvious and each of which changes the number.**

1. **The aggregate is total sold over total capacity, never the mean of the per-show percentages.**
   The worked example below shows the two answers 5.6 percentage points apart.
2. **Showtimes with zero sales are in the denominator.** Every showtime whose `starts_at` falls in the
   period and whose screen is in scope contributes its capacity, whether or not it sold a seat.
   Dropping empty shows inflates occupancy, which is the direction a manager would least notice.
3. **The arithmetic is integer only.** `(sold * 2000 + capacity) // (2 * capacity)` is exact half-up
   to one decimal place with no float anywhere. The formula shape mirrors `FR-ADR-038`'s money
   rounding, though occupancy is not money and no ADR governs it — the rule is stated here so two
   screens cannot disagree.

**Capacity zero is not zero per cent.** When `capacity(P) = 0` — the period contains no showtimes in
scope, or the caller has no halls assigned — the division is undefined. The response carries
`occupancy_pct: null`, **never `0.0`**. Rendering `0.0%` would claim the halls were empty when in fact
nothing was scheduled. `P-RPT-08` and `SCR-RPT-01` say what renders instead.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A showtime row has `seat_count_at_creation = 0` or null | 500 `INTERNAL_ERROR`, and the request is not partially rendered | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |
| 2 | The aggregate query fails | 500 `INTERNAL_ERROR` | as row 1 |

Row 1 is a data defect, not a user error. `seat_count_at_creation` is set at creation and is
non-nullable; a zero or a null there means the showtime was written by something that did not honour
`FR-ADR-022`, and returning a plausible percentage from it would hide that.

**Server-side validation.** No field of its own. Inputs are `P-RPT-01`'s and `P-RPT-02`'s.

**Worked example.** Continuing `P-RPT-03`'s inputs. **Hall sizes are `ASSUMED`**
(`SRC-003 OPEN-SCALE-02`) — screen 3 is taken as 150 seats and screen 5 as 220 seats, and both figures
are the build session's choice, never a constraint. The *formula* is what is specified.

| Showtime | Sold | Capacity | `(sold*2000 + cap) // (2*cap)` | Occupancy |
|---|---|---|---|---|
| ST-101 (screen 3) | 97 | 150 | `(194000 + 150) // 300 = 194150 // 300 = 647` | **64.7 %** |
| ST-102 (screen 5) | 12 | 220 | `(24000 + 220) // 440 = 24220 // 440 = 55` | **5.5 %** |

**Day occupancy for manager M, capacity-weighted (correct):**
`sold = 97 + 12 = 109`, `capacity = 150 + 220 = 370`.
`(109 × 2000 + 370) // (2 × 370)` = `(218000 + 370) // 740` = `218370 // 740` = `295` → **29.5 %**.
Check: `109 / 370 = 0.294594…` → 29.5 % to one decimal, half-up. ✓

**The wrong answer, for comparison:** the mean of the per-show percentages is
`(64.7 + 5.5) / 2` = **35.1 %**. Five point six percentage points higher, from one word.

**A half-up boundary case, so the rounding rule is testable:** 1 seat sold of 16 capacity is exactly
6.25 %. `(1 × 2000 + 16) // 32` = `2016 // 32` = `63` → **6.3 %**, not 6.2 %.

**Occupancy for a show that has not happened yet is the same formula, unchanged.** No projection, no
forecast, no estimate. Each per-show row carries a `has_started` boolean derived from the injected
clock against `starts_at`, so the interface can state a fact — the show is still selling — rather than
imply that a partial figure is a final one.

---

### `P-RPT-05` · Per-film performance is the same two figures, grouped by film, inside the caller's scope · `RULED`
`[SRC: SRC-001 §5.5.2 · SRC-001 §2.4 · SRC-003 OPEN-REPORT-01 · SRC-003 OPEN-SCOPE-01 · FR-ADR-043 · FR-ADR-021]`
`[BRD: R-RPT-02]`

**Behaviour.** The dashboard groups the period's showtimes by film and reports, per film: the number
of shows, seats sold, capacity, occupancy and takings — computed by `P-RPT-03` and `P-RPT-04` over
that film's showtimes only.

**Who may do it.** manager (own halls), admin (all halls), via `P-RPT-02`.

**Preconditions.**
- The film is reached as `showtime.movie_id → movie` (`FR-ADR-021`). A film has no natural key and no
  unique title; two rows may share a title and a re-release is a legitimate second row, so rows are
  keyed by `movie_id` and carry `title` for display.
- Demonstration content uses obvious placeholders such as `DEMO MOVIE 01` (`SRC-003 OPEN-SEED-01`).
  No real title, poster or brand appears anywhere, because `OPEN-ATTRIB-01` is open.

**Happy path.**
1. Take the period window from `P-RPT-01` and the effective scope from `P-RPT-02`.
2. Group the in-window, in-scope showtimes by `movie_id`.
3. For each group compute `shows`, `seats_sold`, `capacity`, `occupancy_pct` and `takings_paise`.
4. Order by `takings_paise` descending, then `title` ascending, then **`movie_id` ascending**. All
   three keys, always.
5. Cap the list at **100 rows**. Set `films_truncated: true` if the period held more.

**A per-film row is that film's performance *inside the caller's scope*, not at the cinema.** A film
playing on six screens shows a manager only the portion on their halls. The interface must say so —
`SCR-RPT-01`'s table caption reads "Per film, in your halls" for a manager and "Per film" for an
administrator. Left unsaid, a manager reads a scoped figure as a cinema-wide one.

**`movie_id` is the final key, and without it this order is not total.** This row's own preconditions,
four lines above, say a film has **no unique title** — two rows may share one and a re-release is a
legitimate second row. So `takings_paise DESC, title ASC` can leave two rows genuinely tied, and the
list is then **capped at 100** (step 5): two engineers implementing the same period ship two different
100-row tables, and which film falls off the end is decided by whatever order the database happened to
return. `movie_id` is a sequential identity column, so the third key always breaks the tie and always
the same way.

This document fixes exactly this three times elsewhere with the same reasoning — `P-BRW-03` adds
`id DESC` because "an unordered tie makes the listing shuffle between two requests", `P-ACC-11` adds
two tiebreakers because "without a total order, paging can show one booking twice and hide another",
and five admin lists carry `name ASC, id ASC`. **A cap over a non-total order is the worst case of it**,
because the row that disappears is the one nobody can see is missing.

**Every client-side sort of this table falls back to the same total order.** `SCR-RPT-01`'s per-film
table is sortable by any column, and no column is unique: sorting by `shows` or `occupancy_pct` ties
constantly. Each sort is *chosen column*, then `title ASC`, then `movie_id ASC`. Without the fallback
a reader toggling a column and toggling back would not get their original rows in their original
order, which reads as data changing under them.

**The default ordering is a build-session judgment call, not a ruling.** `SRC-001 §2.4` asks for
visibility into "popular showtimes" and does not say what popular is measured by — seats sold,
occupancy, or takings are three different orderings. Takings-descending is the default **and every
column is sortable**, so no single definition of popular is imposed on the client. Reversible.

**The summary figures are never derived from this list on the client.** `P-RPT-07` says why. The 100-row
cap can truncate the list; it never truncates the totals, which are computed over every film in the
period.

**When the cap fires, `films_truncated` is `true` and `P-RPT-07`'s parts-equal-the-whole identity no
longer holds** — it is conditioned on `films_truncated` being `false`, and `P-RPT-07` owns that
condition and the test shape that goes with it. **`SCR-RPT-01` must then say the table is short**,
because a reader comparing a 100-row table against a headline that counts more films has been handed
two numbers that disagree with no explanation.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The period contains no showtimes in scope | 200, `films: []` | "No shows were scheduled in this period." |
| 2 | The period contains showtimes but no captured bookings | 200, rows present with zero takings | figures render; each row shows `₹0.00` and `0.0 %` |
| 3 | The aggregate query fails | 500 `INTERNAL_ERROR` | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |

**Server-side validation.** No field of its own.

**Worked example.** Continuing the same inputs. ST-101 and ST-102 are both `DEMO MOVIE 01`; ST-103 is
`DEMO MOVIE 02` on screen 1 and is outside M's scope.

Manager M, `period=day`, `date=2026-08-14`:

| Film | Shows | Seats sold | Capacity | Occupancy | Takings |
|---|---|---|---|---|---|
| `DEMO MOVIE 01` | 2 | 109 | 370 | 29.5 % | `2783331` paise → `₹27,833.31` |

`DEMO MOVIE 02` does not appear, because no showtime of it fell inside M's effective scope. An
administrator's response for the same period carries both rows.

---

### `P-RPT-06` · The per-show listing is a listing, and it is paginated · `RULED`
`[SRC: SRC-001 §5.5.2 · SRC-003 OPEN-REPORT-01 · SRC-002 §5.4.1 · FR-ADR-043]`
`[BRD: R-RPT-01 · R-RPT-02]`

**Behaviour.** A separate endpoint returns one row per showtime in the period and in scope, each
carrying its start instant, hall, film, seats sold, capacity, occupancy and takings. It is paginated
and it carries the total row count.

**Who may do it.** manager (own halls), admin (all halls), via `P-RPT-02`.

**Preconditions.** The same period and scope as the dashboard request it accompanies. The client
passes the identical `period`, `date` and optional `screen_id`.

**Happy path.**
1. Resolve the period and the effective scope exactly as `P-RPT-01` and `P-RPT-02` do.
2. Select the in-window, in-scope showtimes ordered by `starts_at` ascending, then `screen_id`
   ascending as a stable tiebreak.
3. Apply `limit` (default 50, maximum 200) and `offset`.
4. Return the rows, the `total` count, and the resolved period instants.

**Why this is a separate endpoint from `P-RPT-07`'s single-snapshot dashboard.** A month across six
halls is on the order of a thousand showtime rows. Returning that inside the figures response would
put an unbounded payload on a host with roughly 1 GB of memory in total (`SRC-002 §5.4.1`). **A
truncated *listing* is not a half-summed *figure*** — the figures in `P-RPT-07` are always complete and
always cover every showtime, and this list is a detail view of the same period. The interface **never
sums this list to produce a headline figure.** It renders the rows it was given and reads the totals
from the dashboard response.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `limit` is not an integer in `1..200` | 422 `VALIDATION_FAILED` | "Ask for between 1 and 200 rows." |
| 2 | `offset` is negative or not an integer | 422 `VALIDATION_FAILED` | "The row offset cannot be negative." |
| 3 | The period holds no showtimes in scope | 200, `rows: []`, `total: 0` | "No shows were scheduled in this period." |
| 4 | The query fails | 500 `INTERNAL_ERROR` | "This period's shows could not be loaded. If you need help, quote `a1b2c3d4`." |

**Server-side validation.**

| Field | Type and bound | On failure |
|---|---|---|
| `period`, `date`, `screen_id` | as `P-RPT-01` and `P-RPT-02` | as those rows |
| `limit` | integer, `1..200`, default `50` | 422 `VALIDATION_FAILED`, row 1 |
| `offset` | integer, `>= 0`, default `0` | 422 `VALIDATION_FAILED`, row 2 |

**Worked example.** Manager M, `period=day&date=2026-08-14&limit=50&offset=0` returns `total: 2` and
two rows:

| `starts_at` (UTC) | Local | Hall | Film | Sold | Capacity | Occupancy | Takings (paise) | `has_started` |
|---|---|---|---|---|---|---|---|---|
| `2026-08-14T14:00:00Z` | Fri 19:30 | Hall 3 | `DEMO MOVIE 01` | 97 | 150 | 64.7 % | 2483331 | `false` |
| `2026-08-14T18:15:00Z` | Fri 23:45 | Hall 5 | `DEMO MOVIE 01` | 12 | 220 | 5.5 % | 300000 | `false` |

Both rows carry `has_started: false`, because the injected clock is `2026-08-14T12:50:00Z` and both
showtimes start after it. **Both nevertheless carry non-zero takings**, because the tickets were bought
in advance and takings are attributed to the show's date (`P-RPT-03`). A reader who expects a figure
to appear only once a show has happened will read these rows wrongly, which is why `has_started` is on
the row and why the interface renders "Still selling" against it.

---

### `P-RPT-07` · A complete period or nothing — partial is never rendered · `RULED`
`[SRC: SRC-001 §5.5.2 · SRC-001 §7.6 · SRC-003 OPEN-REPORT-01 · FR-ADR-043 · FR-ADR-052]`
`[BRD: R-RPT-01 · R-RPT-04]`

**Behaviour.** The headline figures and the per-film breakdown for one period are produced by **one
request, inside one database transaction, at one snapshot.** If any part of that computation fails,
the endpoint returns an error and no figure at all. There is no response in which some figures are
present and others are missing.

**Who may do it.** manager, admin, via `P-RPT-02`.

**Preconditions.** The transaction is opened at `REPEATABLE READ` — or the whole result is produced by
a single statement — so that a booking committing mid-request cannot be inside the headline takings and
outside the per-film breakdown.

**Happy path.**
1. Open the read transaction.
2. Compute the headline figures — `takings_paise`, `seats_sold`, `capacity`, `occupancy_pct`, `shows`.
3. Compute the per-film rows over the same snapshot.
4. Commit and return both, together, with the period's UTC start and end instants and the evaluation
   instant that produced them.

**Why the snapshot matters, concretely.** Without it, the sum of the per-film takings can differ from
the headline takings by one booking that committed between the two queries. A manager who adds up the
film rows and gets a different number than the headline stops trusting the dashboard, and they are
right to. `R-RPT-04` requires reported figures not to move; two figures in one response that disagree
have already moved.

**The interface enforces the same rule.** A figure is rendered only when the whole response has
arrived. There is no state in which one figure has a value and its neighbour shows a loading block.
`SCR-RPT-01`'s state table has a row named `partial` and it says **never**.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Any part of the computation fails | 500 `INTERNAL_ERROR`, no partial body | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |
| 2 | The request times out at the database | 500 `INTERNAL_ERROR` | as row 1 |
| 3 | Redis is unreachable, so the limiter cannot be evaluated | 503 `DEPENDENCY_UNAVAILABLE` | "The dashboard cannot be loaded right now. A service it depends on is unreachable." |

**Server-side validation.** No field of its own.

**Worked example.** With the day figures from `P-RPT-03` and `P-RPT-04`, one response carries:

```
takings_paise   2783331
seats_sold      109
capacity        370
occupancy_pct   29.5
shows           2
films           [ { movie_id, title, shows: 2, seats_sold: 109, capacity: 370,
                    occupancy_pct: 29.5, takings_paise: 2783331 } ]
period_start_utc  2026-08-13T18:30:00Z
period_end_utc    2026-08-14T18:30:00Z
evaluated_at_utc  2026-08-14T12:50:00Z
```

`SUM(films[].takings_paise) = 2783331 = takings_paise`, and
`SUM(films[].seats_sold) = 109 = seats_sold`.

**Both identities hold in every response in which `films_truncated` is `false`, and both are
assertions in the test suite under exactly that condition** — they are what proves the snapshot is
real.

**The condition is not a weakening, and stating it is the point.** `P-RPT-05` caps `films` at 100
rows, so above 100 distinct films in one period the list is short by construction and **the sums of a
truncated list cannot equal totals computed over every film.** An invariant asserted "in every
response" would then be false in the one case it was most likely to be checked, and `S1.5`
transcribes tests from these examples — so the test would fail against correct behaviour.

**The headline figures stay right when the list is short, and the reason is the whole design.**
`takings_paise`, `seats_sold`, `capacity`, `occupancy_pct` and `shows` are computed **over every
showtime in the period**, in the same snapshot, and are **never summed from `films`** (`P-RPT-05`,
`P-RPT-06`). The cap truncates a **listing**; it never truncates a **figure**. So a truncated response
carries a complete headline beside an incomplete table, which is correct — and is exactly why the
reader has to be told, which `SCR-RPT-01` does.

**When `films_truncated` is `true` the test asserts the other direction instead**: every identity
becomes an inequality in one direction — `SUM(films[].takings_paise) <= takings_paise` and
`SUM(films[].seats_sold) <= seats_sold` — and `len(films) == 100`. A suite that simply skipped the
truncated case would pass against a dashboard whose cap silently dropped the totals too.

**One cinema with six halls will not reach 100 distinct films in a day, a week or plausibly a month**,
so this is a bound that exists rather than a bound that binds. It is specified because a bound nobody
has reasoned about is the one that fires first in the period an operator most wants to read.

---

### `P-RPT-08` · A manager with no halls assigned sees an empty dashboard, and it is not an error · `PROVISIONAL`
`[SRC: SRC-003 C-1 · SRC-003 OPEN-SCOPE-01 · FR-ADR-011 · FR-ADR-009]`
`[BRD: R-RPT-03]`

**Behaviour.** A manager whose resolved screen scope is empty receives **HTTP 200** with a fully-formed
response carrying `scope_empty: true`, `screen_ids: []`, `shows: 0`, `seats_sold: 0`, `capacity: 0`,
`takings_paise: 0`, `occupancy_pct: null` and `films: []`. **It is not a 403, not a 404 and not a
500.** It is the correct state for a newly created account before anyone has assigned it a hall
(`FR-ADR-011`).

**Who may do it.** manager. An administrator's scope is never empty, because it comes from the role
rather than from assignment rows (`FR-ADR-011`).

**Preconditions.** The caller holds the `manager` role and has zero rows in
`manager_screen_assignment`.

**Happy path.**
1. `report_scope` resolves an empty set.
2. The handler **short-circuits**. No aggregate query runs. See `P-RPT-02`'s empty-set trap — building
   a predicate from an empty list is the bug this short-circuit exists to make impossible.
3. The response is returned with `scope_empty: true`.

**What renders, and why it is not a row of zeros.** `SCR-RPT-01` renders the period tabs live, the
figures as `—`, and one sentence: *"No halls are assigned to this account. Ask an administrator to
assign one."* Rendering `₹0.00` here would be a claim about the business's performance when it is a
fact about the account — the cinema did take money, this account simply cannot see any of it. That
distinction is why the response carries `scope_empty` as its own flag rather than leaving the
interface to infer it from zeros.

**This extends `COMPONENTS.md §10` rather than contradicting it.** `§10` specifies that a *period with
no bookings* renders `₹0.00` and `0%` — "a zero is a fact" — and separately that a *manager with no
screens assigned* renders a line stating so. This row keeps both and adds the third case `§10` does
not name: a period with **no showtimes at all**, where capacity is zero and occupancy is therefore
undefined. It renders `—`, not `0%`, for the reason in `P-RPT-04`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Manager with no assignments, any period | **200**, `scope_empty: true` | "No halls are assigned to this account. Ask an administrator to assign one." |
| 2 | Manager with assignments, but the period holds no showtimes on their halls | 200, `scope_empty: false`, `capacity: 0` | "No shows were scheduled in this period." Occupancy renders `—`; takings render `₹0.00`. |
| 3 | Manager with assignments, showtimes exist, no seats sold | 200, `capacity > 0` | Takings render `₹0.00` and occupancy renders `0.0 %`. |

**Rows 1, 2 and 3 are three different states and must render three different ways.** Collapsing them
into one "no data" screen loses the information the reader actually needs.

**Server-side validation.** No field of its own.

**Worked example.** Manager P is created and not yet assigned. `GET /api/reports/dashboard?period=month&date=2026-08-14`
returns 200 with `scope_empty: true`, `capacity: 0` and `occupancy_pct: null`. The identical request
from manager M returns `scope_empty: false`, a `capacity` equal to the sum of `seat_count_at_creation`
over every August showtime on screens 3 and 5 — a positive integer — and a real occupancy figure.
**The test asserts both**, because a suite that only checks P's response would pass against a
dashboard that returns nothing for anybody.

---

### `P-RPT-09` · The dashboard writes nothing, and a manager who reaches a write path is refused at the router · `PROVISIONAL`
`[SRC: SRC-003 OPEN-OPS-03 · SRC-003 C-1 · SRC-001 §7.4 · FR-ADR-009 · FR-ADR-019 · FR-ADR-052]`
`[BRD: R-RPT-03]`

**Behaviour.** Every endpoint in this epic is a `GET`. **The reports router mounts no `POST`, `PUT`,
`PATCH` or `DELETE` route, and the dashboard interface contains no control that writes anything.** A
manager who issues a request to an administrator's write endpoint is refused by that router's role
dependency before the handler runs.

**Who may do it.** Nobody. This row specifies the absence of a capability.

**Preconditions.** Every privileged write belongs to the administrator alone
(`SRC-003 OPEN-OPS-03`). A manager endpoint that writes anything is a defect, not a feature
(`FR-ADR-009`).

**Happy path — what the router actually does.**
1. The write endpoints live on the administration router, which is mounted with a role dependency
   admitting exactly `{admin}`.
2. A manager's request to any of them is rejected by that dependency with **403 `FORBIDDEN`**.
3. **The rejection happens before the request body is parsed.** Nothing is read, nothing is validated,
   nothing is locked, nothing is enqueued.
4. **No audit row is written.** `FR-ADR-019` audits writes; no write occurred, and auditing refusals
   would fill the largest table in the system with rejected requests.
5. The refusal is logged as a structured JSON line with the request id (`SRC-002 §7.6`), which is where
   a repeated refusal is visible to the operator.

**Reading the dashboard is not audited either** (`FR-ADR-019`: writes only). A manager opening a
dashboard writes no row. Auditing reads here would produce a table dominated by page loads.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A manager sends any request to an administration write endpoint | 403 `FORBIDDEN` | "This action is for administrators." |
| 2 | A customer or guest sends any request to a reports endpoint | 403 `FORBIDDEN` (401 `AUTH_REQUIRED` if unauthenticated) | "This page is for managers and administrators." |
| 3 | Any non-`GET` method against a `/api/reports/…` path | **405**, no error code from the registry — the route does not exist for that method | The interface never produces this request; a direct caller receives the framework's method-not-allowed response |

**Server-side validation.** Not applicable. There is no writable field on this surface.

**Worked example.** Manager M sends `PATCH /api/showtimes/101 {"base_price_paise": 30000}`. The
administration router's role dependency rejects it with 403 `FORBIDDEN`. `showtime` row 101 is
unchanged, `audit_log` gains no row, and the log carries one line naming the request id, the actor and
the refused route. If the same request came from an administrator it would change the price **and**
insert an audit row in the same transaction (`FR-ADR-019`) — which is the row `P-RPT-11` lets an
administrator read back.

---

### `P-RPT-10` · No export of any kind · `RULED`
`[SRC: SRC-003 OPEN-REPORT-02 · FR-ADR-043]`
`[BRD: R-RPT-05]`

**Behaviour.** There is no CSV export, no spreadsheet export, no PDF, no download link, no
print-to-file path, and **no control anywhere on this surface that offers one.** The dashboard is read
on screen.

**Who may do it.** Nobody, including an administrator. The client answered `"No"`.

**Preconditions.** None. This row removes a capability.

**Happy path — what is absent, stated so a reviewer can check for it.**
1. **No endpoint** under `/api/reports/` produces any media type other than `application/json`.
2. **No response** in this epic carries a `Content-Disposition` header, of any disposition.
3. **Content negotiation is not implemented.** An `Accept: text/csv` header is ignored and JSON is
   returned. The API does not acknowledge the concept of another representation.
4. **No frontend control** renders a download anchor, a `download` attribute, a Blob or object URL, a
   client-side CSV or XLSX builder, or a "copy all rows" action.
5. **No print stylesheet** is written that paginates the dashboard into a document.

**Why, beyond the ruling.** It keeps customer-level booking data off any download path. That reason
is reinforced by a stronger property of this epic: **no reports response contains a customer-level row
at all.** No customer name, no email address, no booking reference, no per-booking row is returned by
any endpoint here. The dashboard returns aggregates, per-show rows and per-film rows. Even a
screenshot discloses no customer.

**Stated honestly, because the alternative would be a false claim:** a browser's own "Print" and "Save
page as" are not under this product's control and are not prevented. What is specified is that **this
product ships no export**, not that data cannot leave a screen a person is looking at.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A caller sends `Accept: text/csv` | 200, `Content-Type: application/json` | The interface never sends this header. A direct caller receives JSON. |
| 2 | A caller requests a path such as `/api/reports/dashboard.csv` | 404, no route exists | The interface offers no such link. |

**Server-side validation.** Not applicable.

**Worked example.** Not applicable — this row computes no number. It is listed here so the absence is
checkable: a reviewer greps the frontend for `download`, `Blob`, `createObjectURL` and
`Content-Disposition` and expects zero hits inside the dashboard module.

---

### `P-RPT-11` · The administrator reads the change log · `RULED` · stricter than the ruling requires
`[SRC: SRC-003 OPEN-OPS-03 · SRC-001 §7.6 · FR-ADR-019 · FR-ADR-012 · FR-ADR-018]`
`[BRD: R-ADM-06 · R-RPT-05]`

**Scope note, stated because it crosses a lane.** `R-ADM-06` covers both halves of the audit trail.
The **writing** half — which actions are audited, the controlled `action` vocabulary, and the
same-transaction guarantee — belongs with the administration write paths and is not specified here.
This row specifies **only the reading surface**, which `FR-ADR-019` places in Phase 8: *"The screen
that reads this table is Phase 8."*

**Behaviour.** An administrator can read `audit_log` through a paginated, filtered list. It answers
the question the client asked: who changed a price, and what was it before.

**Who may do it.** **admin only.** A manager is refused with 403 `FORBIDDEN` by the router dependency
and never sees the link.

**Admin-only is a stricter adoption, and it is recorded as one.** `SRC-003 OPEN-OPS-03` says the
administrator is the only persona who makes privileged changes; it does not say who may read the
record of them. `SRC-001 §7.6` says only that the business must be able to answer. Restricting the
reader to the administrator is the narrower of the two available choices, and adopting a stricter
option needs no signature (`CONSTITUTION.md` Art III.10). It is written down here so that widening it
to managers later is a decision someone makes rather than a default that drifts.

**Preconditions.**
- `audit_log` is append-only and enforced as such: the application role holds `INSERT` and `SELECT` on
  it and no `UPDATE` or `DELETE` (`FR-ADR-019`).
- Rows carry `occurred_at`, `actor_user_id`, `actor_role`, `action`, `entity_type`, `entity_id`,
  `before`, `after` and `request_id` (`FR-ADR-019`).

**Happy path.**
1. Resolve the role dependency. Manager and below are already refused.
2. Read the filter parameters. `from` and `to` are ISO-8601 dates in Asia/Kolkata and are converted to
   a half-open UTC interval by exactly the mechanism in `P-RPT-01` — `from` at local 00:00 inclusive,
   the day after `to` at local 00:00 exclusive.
3. Select matching rows ordered by `id` **descending** — newest first — with a cursor on `id`.
4. Return the rows, each joined to the acting user for `actor_email`, plus two option sets computed
   over the same window: `available_actions`, the distinct `action` values **present inside the
   queried window**, and `available_actors`, the distinct acting users **present inside the queried
   window**.
5. Render `before` and `after` as a key / previous value / new value table.

**`available_actions` is computed from the window, not from a vocabulary this lane defines.** The
controlled `action` list is **closed** and is owned and published by the administration write paths
(`FR-ADR-019` requires the PRD to enumerate it there); **this lane coins none of its own.** Deriving
the filter's options from the data means the reading surface can never disagree with the writing
surface, and bounding it to the queried window keeps the query off the whole table — `audit_log` is
the largest table in the system and it never shrinks (`FR-ADR-019`, `FR-ADR-012`).

**`available_actors` is the same mechanism applied to the other filter, and it exists because the
administrator select had no data source.** `SCR-RPT-02` renders a select that filters by acting user
and `actor_user_id` is the parameter behind it, but **no endpoint in this product lists staff
accounts**, and none is added here. The options come from the window, exactly as the action options
do.

Each entry carries `actor_user_id` — the value the filter submits — and `actor_email`, the label it
renders. **It carries no role.** `actor_role` is a property of an audit *row*, copied at the time of
the write (`FR-ADR-019`), not a property of the person: one account can appear in one window under
two roles if its role changed inside it, and putting a single role on a filter option would be a
claim about which of them. The rows carry the role; the option does not.

**Why the window and not a list of every administrator.** Three reasons, and the first is the one
that matters:

- **A filter offering an actor who wrote nothing in the window returns an empty result and looks
  broken.** The option set and the data then disagree, which is precisely the defect
  `available_actions` was shaped to avoid.
- **A list of all administrators is a staff directory**, served to answer a filter's dropdown.
  `P-ADM-17`'s manager list exists behind `/api/admin` for account administration; the change log is
  a reading surface and has no reason to enumerate accounts nobody changed anything with.
- **It needs no new endpoint and no second authorisation rule.** The rows are already being scanned
  for the page; the distinct set falls out of the same window and stays off the whole table
  (`FR-ADR-012`, `FR-ADR-019`).

**Both option sets are computed over the DATE WINDOW ALONE — `from` and `to` — ignoring the `action`
and `actor_user_id` filters, and ignoring the page.** They are the distinct values present in
`[window_start_utc, window_end_utc)`, and **only the dates move them.**

**Why, and it is the difference between a usable filter pair and a trap.** Under the other reading —
options computed over the query as sent — selecting an action collapses `available_actions` to the one
option already chosen, and selecting an actor collapses `available_actors` to that one person. **A
reader can then never switch from one filter value to another**; they must first clear the filter they
are on to make the alternatives reappear, and nothing on the screen tells them that. Worse, the two
selects cascade: `SCR-RPT-02` rules that *a selected option which leaves the option set is dropped and
the change is announced*, so choosing an action would eject an actor who made no change of that kind,
which would then re-widen the action set, which could re-admit the actor. **A pair of filters that
rewrite each other is not a pair of filters.**

The rule is identical for `available_actions` and `available_actors`; neither is special.

**Neither set is computed over the page**, for the same family of reason: a filter's options moving
under the reader as they page back through older rows is indistinguishable from data disappearing.
**Only `from` and `to` change either set** — that is the whole rule, and it is one sentence long so
that it can be checked.

**An `actor_user_id` that is well-formed and not a member is not rejected**, for the same reason a
non-member `action` is not: it is a legitimate query that matches no row, and it returns 200 with
`rows: []`. Because the options come from `available_actors` rather than from a list typed into the
interface, a user cannot reach that state through the interface; a direct caller can.

**A hand-typed `action` that is not a member is the quiet failure here.** It is well-formed, it
passes validation, and it matches nothing — an empty change log that looks like a working one. The
published member for a base-price change is **`showtime.base_price_changed`**, and that exact string
is what the worked example below filters on. Because the options rendered on screen come from
`available_actions` rather than from a list typed into the interface, a user cannot reach this state
through the interface; a direct caller can.

**`before` and `after` values are rendered verbatim, with the field name, and are never unit-converted.**
A row reading `base_price_paise: 25000 → 30000` is displayed exactly so. The renderer cannot know that
a field is money, and a generic renderer that guessed would eventually divide something by 100 that was
not paise. The field name carries the unit; that is what `FR-ADR-019`'s naming does for this screen.

**Actor identity is staff identity.** `actor_email` is an administrator's or a manager's account
address, never a customer's. No customer appears in this table, because a customer booking a seat is
not a privileged write (`FR-ADR-019`).

**No export from here either**, and for a stronger reason than `P-RPT-10`'s: these rows carry the
before-and-after values of privileged changes. `SRC-003 OPEN-REPORT-02` covers it; the same five
absences listed in `P-RPT-10` apply here without exception.

**Reading this table is not itself audited** (`FR-ADR-019`: writes only).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A manager requests the change log, or follows a stale link to it | 403 `FORBIDDEN` | "This page is for administrators." |
| 2 | A customer or guest requests it | 403 `FORBIDDEN` (401 `AUTH_REQUIRED` if unauthenticated) | "This page is for administrators." |
| 3 | `from` is later than `to` | 422 `VALIDATION_FAILED` | "The start date must be on or before the end date." |
| 4 | `from` or `to` is malformed | 422 `VALIDATION_FAILED` | "The date must be written as YYYY-MM-DD." |
| 5 | `limit` outside `1..200` | 422 `VALIDATION_FAILED` | "Ask for between 1 and 200 rows." |
| 6 | `cursor` is malformed — not an integer, or not positive | 422 `VALIDATION_FAILED` | "That page of results is no longer valid. Start again from the newest change." |
| 6a | `cursor` is a **well-formed integer naming no `audit_log` row** | **200**, not an error. It is a bound, not a lookup: the query returns rows with a lower `id`, and an id that matches nothing still bounds the set perfectly well | the page of changes older than that id, or the empty state if there are none. **Nothing tells the reader their cursor was unknown**, because nothing went wrong |
| 7 | No rows match | 200, `rows: []` | "No changes were recorded in this period." |
| 8 | The query fails | 500 `INTERNAL_ERROR` | "The change log could not be loaded. If you need help, quote `a1b2c3d4`." |

**Server-side validation.**

| Field | Type and bound | On failure |
|---|---|---|
| `from` | ISO-8601 date in Asia/Kolkata, optional; defaults to 30 days before `to` | 422, rows 3 and 4 |
| `to` | ISO-8601 date in Asia/Kolkata, optional; defaults to today from the injected clock | 422, rows 3 and 4 |
| `action` | string, 1..64, exact match against the published vocabulary, optional. **A well-formed non-member is not rejected** — it is a legitimate query that matches no row, and returns 200 with `rows: []` per row 7 | 422 if longer than 64 |
| `entity_type` | string, 1..64, exact match, optional | 422 if longer than 64 |
| `entity_id` | integer, positive, optional. Requires `entity_type` to be present. | 422 `VALIDATION_FAILED`, message "Choose a record type before filtering by record id." |
| `actor_user_id` | integer, positive, optional. **A well-formed id that is not a member of `available_actors` is not rejected** — it returns 200 with `rows: []` per row 7, exactly as a non-member `action` does | 422 if not a positive integer |
| `limit` | integer `1..200`, default `50` | 422, row 5 |
| `cursor` | integer, positive, optional. **A well-formed id naming no row is not rejected** — the cursor is a *bound*, not a lookup, and `id < cursor` is well defined for any integer. It returns 200 per row 6a, exactly as a well-formed non-member `action` and a well-formed non-member `actor_user_id` already do on this endpoint | 422, row 6, for a malformed or non-positive value only |

**Worked example — the client's own question, answered end to end.** An administrator changed a
showtime's base price from ₹250.00 to ₹300.00 on 2026-08-12 at 3:40 pm local time.

Request: `from=2026-08-12&to=2026-08-12&action=showtime.base_price_changed`.
Converted window: `[2026-08-11T18:30:00Z, 2026-08-12T18:30:00Z)`.
One row returns:

| Field | Value |
|---|---|
| `occurred_at` | `2026-08-12T10:10:00Z`, rendered **`12 Aug 2026, 3:40 pm`** — `S7.19`'s date-with-time form. **Not `15:40`**: rule 3 forbids a 24-hour clock on any surface a reader reads, and an admin reads this **in the interface**, which makes it reader-facing rather than a log line. **No zone suffix**, by rule 2 — the panel's own zone note carries it once and the emailed receipt is the only surface that prints it per-instant |
| `actor_email` | the administrator's account address |
| `actor_role` | `admin` — the role held **at the time**, copied not joined (`FR-ADR-019`) |
| `action` | `showtime.base_price_changed` — the exact member of the published vocabulary. A filter written against a shortened paraphrase of it matches no row and renders an empty change log that looks like a working one |
| `entity_type` / `entity_id` | `showtime` / `101` |
| `before` | `{"base_price_paise": 25000}` |
| `after` | `{"base_price_paise": 30000}` |
| `request_id` | joins this row to every log line of the request that made the change |

The screen renders `base_price_paise` with `25000` and `30000` side by side, as stored. **It does not
render ₹250.00 and ₹300.00**, because the value in the column is paise and the renderer does not
interpret units.

**Worked example — the option sets, on a window that distinguishes the two readings.** The example
above holds one row, so both readings give the same answer on it and it settles nothing. This one has
**three rows and two distinct actions**, which is the smallest shape that separates them. Same day,
same window `[2026-08-11T18:30:00Z, 2026-08-12T18:30:00Z)`; the audit rows present are:

```
id  occurred_at, as rendered  actor_user_id  actor_email  action
--  ------------------------  -------------  -----------  ------------------------------
31  12 Aug 2026, 3:40 pm      1              admin-a@…    showtime.base_price_changed
30  12 Aug 2026, 11:05 am     1              admin-a@…    movie.published
29  12 Aug 2026, 9:20 am      4              admin-b@…    movie.published
```

Now issue the **filtered** request from the example above — `action=showtime.base_price_changed` —
which matches **row 31 only**:

```
rows              [ row 31 ]                      <- the FILTER decides this

available_actions ["movie.published",
                   "showtime.base_price_changed"] <- the WINDOW decides this
available_actors  [ {"actor_user_id": 1, "actor_email": "admin-a@…"},
                    {"actor_user_id": 4, "actor_email": "admin-b@…"} ]
```

**`rows` has one entry and the option sets have two each. That gap is the answer.** Both sets are
computed over the date window and ignore `action` and `actor_user_id` entirely — so
`movie.published` stays on offer even though nothing matching it was returned, and `admin-b@…` stays
on offer even though they made no base-price change.

**Under the rejected reading both sets would collapse to one entry each** —
`["showtime.base_price_changed"]` and `[admin-a@…]` — and the reader would be **stuck**: the only
action they could select is the one already selected, and `admin-b@…` would have vanished from a
control the reader would have to clear a *different* filter to get back. `SCR-RPT-02` then drops a
selected option that leaves its set and announces the change, so the two selects would rewrite each
other on every interaction. That is the failure this decision exists to prevent, and it is invisible
on a one-row window.

**Add `&actor_user_id=4` to the same request** and `rows` becomes empty — actor 4 made no base-price
change — while **both option sets are byte-identical to the block above**, because neither filter
touches them. The reader can see at once that the combination is wrong rather than that the page is
broken, and can change either filter without clearing the other.

**Only `from` and `to` move either set.** Widen to `from=2026-08-01&to=2026-08-12` and each grows to
the distinct values actually present across those twelve days — never to every member of
`P-ADM-19`'s vocabulary, and never to every account that holds the admin role. **An administrator who
made no change anywhere in the window is not offered**, because selecting them would return nothing
and read as a fault in the page rather than as an accurate answer.

**If the same account acted under two roles inside one window** — created as a manager, later an
administrator — it appears **once** in `available_actors`, and twice in `rows` with a different
`actor_role` on each. The option set is keyed on `actor_user_id` alone.

---

### `P-RPT-12` · Nothing is precomputed, because nothing runs on a schedule · `RULED`
`[SRC: SRC-003 OPEN-PROC-01 · SRC-003 OPEN-TMDB-01 · SRC-002 §5.4.1 · SRC-001 §8.2 · FR-ADR-043 · FR-ADR-005 · FR-ADR-012 · FR-ADR-057]`
`[BRD: R-RPT-01 · R-RPT-02]`

**Behaviour.** Every figure in this epic is computed live from `showtime`, `booking`, `payment` and
`booking_seat` on every request. **There is no rollup table, no materialised view, no nightly summary,
no cached report and no background warm-up.**

**Who may do it.** Not applicable — this row constrains how the figures are produced.

**Preconditions.** **Nothing in this system runs on a schedule** (`SRC-003 OPEN-PROC-01`, `FR-ADR-005`).
The scheduler process is deleted and there is no EventBridge rule. There are three long-running
processes: the API, the worker, and a static frontend container.

**Happy path.**
1. A request arrives. The aggregate runs inside the request.
2. It is driven from `showtime`, filtered by `starts_at` and `screen_id` first, so the row set is
   bounded by the period rather than by the size of the tables.

**Required indexes**, because the driving filter is what keeps this bounded:
`showtime(starts_at)`, `showtime(screen_id, starts_at)`, `booking(showtime_id)`,
`booking_seat(booking_id)`, `booking(payment_id)`, `payment(state)`.

**The join runs `payment.id = booking.payment_id`, not the reverse.** `P-PAY-07` records why the
foreign key points that way and it is an ordering fact, not a preference: `FR-ADR-029` captures
payment at step 6 and inserts the booking at step 7, so a `payment.booking_id` column could not be
satisfied at insert time — the booking does not exist yet. A dashboard query written the other way
round would reference a column that is not there.

**If a precomputation is ever wanted, it has to happen on the read path.** There is nowhere else for
it to live. Maintaining a rollup on the **write** path would put reporting work inside the booking
confirmation transaction — the transaction that carries the oversell guard — which is the one
transaction in this system that must stay as small as possible. That trade is stated rather than
taken.

**No Redis cache of a dashboard response is specified.** A cached report is a stale report a manager
will act on, and `R-RPT-04` requires figures not to move. It also means a Redis outage does not make
the dashboard wrong; it makes it unavailable, through the rate limiter, which is a visible failure
rather than a silent one (`FR-ADR-028`).

**`/metrics` is not the dashboard's data source.** The Prometheus endpoint exists (`SRC-002 §7.7`),
**nothing in the approved stack scrapes it, nothing stores its history and nothing alerts on it**
(`FR-ADR-057`). It measures the process, not the business, and it is owned by a different epic. No
figure on this dashboard is read from it.

**What it costs, stated as a reasoned estimate and labelled as one.** The cost of a month view grows
with a month's bookings, not with the whole database, provided the query drives from `showtime` on the
indexes above. Nothing is ever deleted (`FR-ADR-012`), so the tables only grow and the *number of
months* grows without bound while the *cost of one month* does not. At one cinema with six halls this
is small for a long time. **These statements are reasoned from the data shape, not observed — this
system has never run.** The dashboard's response time belongs in the runbook as a figure to measure in
Phase 8 and to watch afterwards, and the rollup above is the thing to reach for if measurement says so.

**A modest rate limit is applied, and it is a build-session judgment call.** One per-user token bucket
(`FR-ADR-058`'s mechanism), named **`REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`** — the same name the API
contract carries — starting value **60**, an estimate to be tuned once measured, in the same language
`FR-ADR-058` uses for its own table. **No per-IP bucket**: every
caller here is authenticated and there are at most thirteen of them, and a per-IP bucket would put
twelve managers in one building into one bucket, which is the failure mode `FR-ADR-058` exists to
avoid.

**This row is one row, and this lane restates none of the others.** The rate-limit table and the
configuration inventory both live in the cross-cutting floor (`P-XCT-07`, `P-XCT-15`), which is the
**single source** for every bucket and every setting; this lane adds `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`
to them and copies nothing back. A second copy of that table here would be a second thing to keep in
step, and it is the copy that would go stale.

The limiter **fails closed** — Redis unreachable returns 503 `DEPENDENCY_UNAVAILABLE`
(`FR-ADR-028`, `FR-ADR-058`) — and the cost of that coupling is that the dashboard needs Redis even
though PostgreSQL alone could serve it. That cost is accepted because `/health/ready` already returns
503 on Redis loss and removes the instance from the load balancer regardless (`FR-ADR-055`,
`FR-ADR-028`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The aggregate exceeds the statement timeout | 500 `INTERNAL_ERROR` | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |
| 2 | Redis unreachable, limiter fails closed | 503 `DEPENDENCY_UNAVAILABLE` | "The dashboard cannot be loaded right now. A service it depends on is unreachable." |
| 3 | The per-user bucket is exhausted | 429 `RATE_LIMITED` with `Retry-After` | "Too many requests. Try again in 1 second." |

**The wait is one second, and here is the arithmetic — stated once, in this row, because the other two
places that publish the string point here.** `S7.20` renders a retry span from the bucket's **refill
interval**, not from its capacity and not from its window:

```
bucket        REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE = 60 over a 60 s window
refill        ceil(window_seconds / capacity) = ceil(60 / 60) = 1 second
render        1 < 120, so seconds, and n == 1 takes the singular (S7.20)
published     "Too many requests. Try again in 1 second."
```

`S7.20` names "reports and change log, per user" as one of the four buckets where **the singular is
the shipped copy**, so `1 second` is not an edge case being handled — it is this bucket's ordinary
string. A bucket that refills sixty times a minute makes a caller wait about a second, which is what a
60-per-minute limit means.

> **This corrects a defect this document introduced.** All three places previously published
> `Try again in 30 seconds.` **Thirty is neither this bucket's capacity, nor its window, nor its
> refill interval** — it is a number that arrived from somewhere else and was never checked against
> the bucket sitting beside it.
>
> **The class, which matters more than this instance.** This is the **fourth** occurrence of one
> defect: *a bucket's capacity or window written into customer-facing copy that wanted its refill
> interval.* `S7.20` caught three in other lanes and missed this one, which is itself the lesson — the
> check has to run against **every** published retry string in the document, not against the ones a
> reader happened to look at. **Any string quoting a wait is derived from `ceil(window / capacity)` for
> its own named bucket, and the bucket is named beside the string** so a reader who does not trust the
> number can re-run it. The value is computed at render time and **a literal is a defect**
> (`S7.20` rule 6).

**Server-side validation.** `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE` is validated at boot as a
positive integer. The application crashes at startup with a clear message if it is absent or invalid
(`SRC-002 §7.1`).

**Worked example.** The August 2026 month view for an administrator covers
`[2026-07-31T18:30:00Z, 2026-08-31T18:30:00Z)`. With six halls and the seed's roughly one month of
data (`SRC-003 OPEN-SEED-01`), the query touches on the order of one month of `showtime` rows and the
`booking_seat` rows reachable from them, and nothing outside that window. Adding a second month of
history does not change the cost of reading August. *(Reasoned from the query shape and the index set,
not observed.)*

---

## S5 — UX specification

### `SCR-RPT-01` · The dashboard
**Route.** `/dashboard` · **Who reaches it.** manager, admin · **Component basis.** `COMPONENTS.md §10`
(the dashboard panel), with `§0` foundations, `§6` for the error banner and `§11` for the filter
controls.

**What the user arrives with / leaves with.** They arrive signed in as a manager or an administrator,
with nothing else. They leave with four figures for a chosen period, a per-film breakdown, a per-show
listing, and — for an administrator — a link to the change log. They leave with **no file**.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, padding `--fr-space-5`, `--fr-shadow-card` | The single container for the figures. | — |
| Period tabs — Day / Week / Month | `--fr-text-sm`; selected `--fr-surface-accent` on `--fr-ink-on-accent`; min height `--fr-tap-min` | Changes `period` and refetches. Exactly one is selected at all times, and **`Day` is selected on arrival** — see below. | Server rejects anything else with `VALIDATION_FAILED` (`P-RPT-01`) |
| Period stepper — previous / next | `--fr-control-edge` 1px, `--fr-radius-md`, min height `--fr-tap-min` | Moves the anchor date by one whole period. Never produces a partial period. **Both controls carry a visible label and an accessible name that names the period type**, so "previous" is never ambiguous between a day and a month | Server validates `date` (`P-RPT-01`) |
| Period line | `--fr-text-sm`, `--fr-ink-muted` | States the period being read and the zone. Not editable. | — |
| Hall filter | as `COMPONENTS.md §11` field; `--fr-surface-inset`, `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min` | Narrows within the caller's scope. A manager sees only their own halls; an administrator sees all, **including halls that are out of service** (`P-RPT-02`, `P-ADM-16`). **The first option is always the all-halls option and submits no `screen_id`.** An out-of-service hall renders its name followed by the out-of-service suffix in `--fr-ink-muted`, and stays selectable | Server refuses an out-of-scope hall with `FORBIDDEN` (`P-RPT-02`) |
| Figure — Takings | `--fr-font-mono`, `--fr-text-2xl`, `--fr-weight-black`, `--fr-ink-strong` | Rendered from integer paise at render time, Indian digit grouping, `tabular-nums`. | — |
| Figure — Occupancy | as above | One decimal place. `—` when capacity is zero. | — |
| Figure — Seats sold, Shows | as above | Integers. | — |
| Figure labels | `--fr-text-xs`, `--fr-ink-muted`, uppercase, `--fr-track-caps` | — | — |
| Occupancy bar | track `--fr-surface-inset` + `--fr-radius-pill`; fill `--fr-countdown-fill` | Accompanies the numeric percentage; **never replaces it**. Absent entirely when occupancy is `—`. | — |
| Per-film table | rows separated by `--fr-rule-quiet`; section head `--fr-rule`; figures `--fr-font-mono` | Sortable by any column. Default order: takings descending. Scrolls inside its own `overflow-x: auto` container. | — |
| Per-show table | as per-film | Ordered by start time ascending. **Not sortable** — `EP-RPT-02` accepts no sort parameter, and a client-side sort of one page would misdescribe the period (see Accessibility). Paginated (`P-RPT-06`). Scrolls inside its own container. | `limit` `1..200` server-side |
| Per-show pagination | control `--fr-control-edge` 1px, `--fr-radius-md`, min height `--fr-tap-min`; position line `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` | Two controls and a position line, below the per-show table. **Direction is named by time, not by page number** — the table is ordered by start time, so "earlier" and "later" are what the reader is actually moving through. A control at the end of its range is **absent**, not disabled | `offset` `>= 0`, `limit` `1..200` (`P-RPT-06`) |
| Per-film truncation line | `--fr-text-xs`, `--fr-ink-muted`, directly under the per-film table | Rendered **only** when `films_truncated` is `true`. States that the table is short and that the headline figures are not | — |
| Change log link | `--fr-accent-ink`, `--fr-text-sm`, underlined | **Rendered for an administrator only.** Absent from a manager's DOM entirely, not hidden with CSS. | Server enforces (`P-RPT-11`) |
| Error banner | `COMPONENTS.md §6` | Replaces the figures. Tabs stay usable. | — |

**There is no control on this screen that writes anything, and no control that downloads anything.**
That is `P-RPT-09` and `P-RPT-10`, and it is checkable by reading the component's markup.

**The screen's first request, stated because a screen that cannot issue one is not specified.**
`EP-RPT-01` makes `period` **required** and deliberately gives it no default, so the screen must name
its own opening value. **`SCR-RPT-01` opens on `period=day` with `date` omitted**, which the server
resolves to today in Asia/Kolkata from the injected clock (`P-RPT-01`). It is one request:
`GET /api/reports/dashboard?period=day`.

**`Day`, and the choice costs something, which is why it may not be left to the implementer.** Day and
Month return **entirely different headline figures** — a different takings total, a different
occupancy, a different show count — on the first screen a manager ever sees, and neither is more
"correct" than the other. Two implementers reading `exactly one is selected at all times` would ship
two dashboards that disagree on landing, and each would look right to the person who built it.

**Why `Day` and not `Month`.** Today's takings are a figure the reader can check against the building
they are standing in; a month's are not. The narrowest period is also the cheapest aggregate on a host
with roughly 1 GB of memory (`SRC-002 §5.4.1`, `P-RPT-12`), so the landing request is the smallest one
the screen can make rather than its largest. **A reader who wants the month is one tab away and the
tabs are live during the first load** — the reverse, landing on a month and stepping down, is not
symmetrical, because the expensive request has already been paid for by then.

**`date` is omitted rather than sent as today.** The server owns "today" (`P-RPT-01`), it computes it
from the injected clock in the cinema's zone, and a client that computed and sent its own date would
be a second implementation of the one thing this epic's opening paragraph says will be got wrong.

**States.**

| State | What renders |
|---|---|
| **Empty — no halls assigned** | Period tabs live. All four figures render `—`. The occupancy bar is absent. One line: *"No halls are assigned to this account. Ask an administrator to assign one."* The per-film and per-show tables are absent. **This is not styled as an error** — no danger surface, no danger ink, no error banner. |
| **Empty — no shows in this period** | Period tabs live. Takings renders `₹0.00`; Seats sold and Shows render `0`; Occupancy renders `—` and its bar is absent. One line: *"No shows were scheduled in this period."* |
| **Empty — shows but no sales** | Takings `₹0.00`, Seats sold `0`, Occupancy `0.0 %` with its bar at zero width, Shows the real count. One line: *"No seats were sold in this period."* A zero is a fact. |
| **Loading** | Figure-sized `--fr-surface-inset` blocks in place of every figure at once. The period tabs stay live. The previous period's figures are **cleared**, not left on screen under a spinner — a stale figure beside a live tab is a wrong number. |
| **Error** | `COMPONENTS.md §6` banner replaces the figures. The tabs and the period stepper stay usable so another period can be tried. On a 5xx the request id line renders; on a 4xx it does not (`FR-ADR-052`). |
| **Success** | All four figures, the occupancy bar, the per-film table and the first page of the per-show table. |
| **Success, per-film table truncated** | As **Success**, plus the truncation line under the per-film table. **The four headline figures are unchanged and complete** — they are computed over every showtime in the period, never summed from the table (`P-RPT-07`). Only the table is short. **Not an error, and not styled as one**: no danger surface, no banner, no request id. |
| **Partial** | **Never.** A figure renders only when the whole response has arrived (`P-RPT-07`). There is no state in which one figure has a value and another shows a loading block. The per-show listing arriving separately is a listing, not a figure, and it has its own loading state inside its own container. |
| **Rate limited** | The banner states the wait. The figures already on screen are cleared, because they belong to the request that was refused. |
| **Future period selected** | Renders normally. Every per-show row carries *"Still selling"* where `has_started` is false. No projection and no estimate is shown. |

**Copy.** Every string a reader sees on this screen.

| Where | Verbatim |
|---|---|
| Panel heading | "Dashboard" |
| Zone note, once, under the heading | "All dates and times are Asia/Kolkata." |
| Period tabs | "Day" · "Week" · "Month" |
| Period line, day | "Friday 14 August 2026" |
| Period line, week | "Monday 10 August to Sunday 16 August 2026" |
| Period line, month | "August 2026" |
| Figure labels | "TAKINGS" · "OCCUPANCY" · "SEATS SOLD" · "SHOWS" |
| Scope line, manager | "Halls shown: Hall 3, Hall 5." |
| Scope line, admin | "Halls shown: every hall." |
| Per-film table caption, manager | "Per film, in your halls" |
| Per-film table caption, admin | "Per film" |
| Per-show table caption | "Every show in this period" |
| Per-film table column headers | "Film" · "Shows" · "Seats sold" · "Capacity" · "Occupancy" · "Takings" |
| Per-show table column headers | "Start" · "Hall" · "Film" · "Seats sold" · "Capacity" · "Occupancy" · "Takings" |
| **Per-film table only** — a sortable header's accessible name, unsorted | the header text, then ", sort by this column" |
| **Per-film table only** — a sortable header's accessible name, sorted descending | the header text, then ", sorted highest first. Activate to sort lowest first" |
| **Per-film table only** — a sortable header's accessible name, sorted ascending | the header text, then ", sorted lowest first. Activate to sort highest first" |
| Per-show row marker | "Still selling" |
| Occupancy when capacity is zero | "—" |
| No halls assigned | "No halls are assigned to this account. Ask an administrator to assign one." |
| No shows in the period | "No shows were scheduled in this period." |
| No sales in the period | "No seats were sold in this period." |
| Load failure (5xx) | "This period's figures could not be loaded. If you need help, quote `a1b2c3d4`." |
| Dependency unavailable (503) | "The dashboard cannot be loaded right now. A service it depends on is unreachable." |
| Rate limited (429) | "Too many requests. Try again in 1 second." — singular, and computed from `REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`, never typed (`P-RPT-12`, `S7.20`) |
| Hall outside scope (403) | "That hall is not assigned to this account." |
| Hall does not exist (404, admin) | "That hall does not exist." |
| Bad period (422) | "Choose day, week or month." |
| Bad date (422) | "The date must be written as YYYY-MM-DD." |
| Wrong role (403) | "This page is for managers and administrators." |
| Not signed in (401) | "Sign in to see the dashboard." |
| Change log link, admin only | "Change log" |
| Period stepper, previous — day view | "Previous day" |
| Period stepper, previous — week view | "Previous week" |
| Period stepper, previous — month view | "Previous month" |
| Period stepper, next — day view | "Next day" |
| Period stepper, next — week view | "Next week" |
| Period stepper, next — month view | "Next month" |
| Hall filter label | "Hall" |
| Hall filter, first option — manager | "All my halls" |
| Hall filter, first option — admin | "All halls" |
| Hall filter, an out-of-service hall | the hall's name, then " — out of service" |
| Per-show pagination, earlier | "Earlier shows" |
| Per-show pagination, later | "Later shows" |
| Per-show pagination, position line, more than one | "Shows 1 to 50 of 214" |
| Per-show pagination, position line, exactly one | "Showing the only show in this period" |
| Per-film table truncated | "Showing the top 100 films by takings. The figures above cover every film in this period." |

No string above apologises, exclaims, or uses a figure of speech (`SRC-002 §2.2`, `FR-ADR-052`).

**Accessibility.**
- **Focus order** follows visual order: period tabs → period stepper → hall filter → change log link
  (admin only) → per-film table → per-show table → per-show pagination. The focus ring is
  `--fr-stroke-bold` solid `--fr-focus-ring` with `outline-offset: 2px`, never removed
  (`COMPONENTS.md §0.2`). **Every control in that order has a published string in the copy table
  above** — a control named in a focus order and nowhere else is a control whose words were left to
  the implementer, which is a defect and not a detail.
- **The period stepper's labels change with the period type**, so its accessible name is `Previous
  week` on a week view and `Previous month` on a month view. One label reading `Previous` would leave
  a screen-reader user to infer the unit from a heading they may not have reached.
- **The per-show pagination names direction by time, not by page number.** `Earlier shows` and
  `Later shows` map onto the table's own ordering without the reader first working out which way
  page 2 runs. The position line is a polite live region: moving a page announces
  `Shows 51 to 100 of 214`. A control at the end of its range is **removed from the tab order**, not
  disabled, so nobody is told to activate something inert.
- **The truncation line is ordinary content, announced once on load through the panel's live region
  and carrying no `role="alert"`.** A short table is a correct state, not an error.
- **Period tabs** are a `tablist` with `aria-selected`, operable with arrow keys, one tab stop for the
  group. Minimum target `--fr-tap-min`.
- **Accessible names** state the value, not only the label: the takings figure is named
  "Takings, twenty-seven thousand eight hundred and thirty-three rupees and thirty-one paise" via the
  element's accessible text, and occupancy as "Occupancy, twenty-nine point five per cent".
- **The occupancy bar is decorative** and carries `aria-hidden="true"`. The percentage text is the
  only carrier of the value, which is why `P-RPT-04` requires the number to be rendered whenever the
  bar is.
- **Live region**, polite: on every period change the new period and the headline figures are
  announced once — "Day, Friday 14 August 2026. Takings twenty-seven thousand eight hundred and
  thirty-three rupees and thirty-one paise. Occupancy twenty-nine point five per cent." The loading
  state is announced as "Loading figures." Errors are announced, not only coloured (`FR-ADR-051`).
- **Tables** are real `<table>` elements with `<caption>` and `<th scope="col">`. **Every header cell
  in both tables has a published string in the copy table above** — thirteen cells, six per-film and
  seven per-show — which is the same obligation a control with no words fails.
- **Only the per-film table is sortable, and only its six headers are buttons carrying `aria-sort`.**
  The per-show table's seven headers are plain `<th scope="col">` with no button, no `aria-sort` and
  no sort affordance of any kind.
- **The per-show table is deliberately not sortable, and the reason is that it cannot honestly be.**
  `EP-RPT-02` accepts **no sort parameter** — it returns one page of a period ordered by `starts_at`
  ascending, and the period can run to a thousand rows across six halls (`P-RPT-06`). A client-side
  sort would reorder **the current page only**, so a header reading `sorted highest first` would be a
  claim about fifty rows dressed as a claim about the period, and the highest-takings show of the
  month would sit unfound on page four. **The requirement was removed rather than the parameter
  invented** (`S1.2.1` case 2): adding server-side sorting to a paginated endpoint is a real feature
  with a real cost, and no source asks for it.
  *(An earlier revision of this clause claimed sortable headers "for both tables". That was a screen
  requiring what its endpoint cannot carry, and it is corrected here rather than left to whoever
  implemented it first.)*
- **A sortable header's accessible name states its current sort and what activating it will do**, so a
  screen-reader user is not left to infer the direction from `aria-sort` alone. The three forms are
  published above and **apply to the per-film table alone**. **The takings column is its default sort,
  highest first** (`P-RPT-05`), so it carries the sorted-descending name on first render. Each table
  scrolls inside its own `overflow-x: auto` container and the **page body never scrolls horizontally**
  (`COMPONENTS.md §0.1`).
- **The empty-scope state is not announced as an error** and carries no `role="alert"`. It is ordinary
  content, because it is an ordinary state.

---

### `SCR-RPT-02` · The change log
**Route.** `/dashboard/audit` · **Who reaches it.** **admin only** · **Component basis.**
`COMPONENTS.md §10` for the panel, `§11` for the filter fields, `§6` for the error banner.

**What the user arrives with / leaves with.** They arrive as an administrator, usually from the
dashboard link, sometimes with a date in mind. They leave knowing who changed a thing, when, and what
it was before. **They leave with no file.**

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-space-5`, `--fr-shadow-card` | — | — |
| From / To date fields | `COMPONENTS.md §11` field tokens; label always visible, never a placeholder | Dates in Asia/Kolkata, converted server-side (`P-RPT-11`) | 422 `VALIDATION_FAILED` for malformed or inverted ranges |
| Action select | as above | Options come from `available_actions` in the response — the distinct actions inside the queried window. Never a hardcoded list. | 422 if longer than 64 characters |
| Record type / record id | as above | Record id is disabled until a record type is chosen. | 422 if an id is sent without a type |
| Administrator select | as above | Filters by acting user, submitting `actor_user_id`. **Options come from `available_actors` in the response** — the distinct acting users inside the queried window, labelled with `actor_email` and valued with `actor_user_id`. **Never a hardcoded list and never a list of every administrator account** (`P-RPT-11`). The first option is always "Any administrator" and submits nothing. **No role is rendered on an option**, because a role belongs to a row and not to a person | 422 if not a positive integer |
| Row list | rows separated by `--fr-rule-quiet`; timestamps and ids in `--fr-font-mono` | Newest first. Cursor pagination. | `limit` `1..200` |
| Before / after detail | key column `--fr-ink-muted`; values `--fr-font-mono`, `--fr-ink` | Two value columns, previous and new, rendered **verbatim with the field name** and never unit-converted. | — |
| Apply control | `--fr-surface-accent`, `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min` | Submits the filter set as one request. **The filters do not auto-submit** — a date pair is two fields and re-querying between them would fire a request against a half-entered range, including an inverted one that 422s while the reader is still typing | Server validates the whole set (`P-RPT-11`) |
| Error banner | `COMPONENTS.md §6` | — | — |

**Both selects are populated from the response and from nothing else.** The action options come from
`available_actions` and the administrator options from `available_actors` (`P-RPT-11`). Neither is a
list typed into the interface, and neither is fetched from a second endpoint — **there is no endpoint
that lists actions and none that lists staff accounts**, and this screen needs neither.

**Neither select narrows the other, and neither narrows itself.** Both option sets come from the
**date window alone** (`P-RPT-11`), so choosing an action leaves every actor on offer and choosing an
actor leaves every action on offer. **Only From and To change what either control holds.** This is why
the reader can move from one action straight to another without first clearing anything — and it is
why the drop-and-announce rule below fires on a **date** change and essentially never on a filter
change.

**When the window holds no rows both option sets are empty**, so both selects render with their "any"
option alone and nothing else. That is correct rather than broken: there is nothing in this window to
filter by. The selects stay enabled, because the reader's next action is to widen the dates, and a
disabled control cannot say why it is disabled.

**A selected option that leaves the option set when the dates change is dropped, not silently kept —
and this applies to BOTH selects, in the same words.** If an administrator is selected and **the
window is then narrowed** to one where that person made no change, the filter clears back to "Any
administrator". If an **action** is selected and the narrowed window holds no row of that action, it
clears back to "Any action". **Either clearance is announced through the same live region as the
result count**, and each has its own published sentence below — the action case had none until this
pass, while its administrator twin was published in full. Leaving a filter applied that the reader can no longer see in the
control is how an empty page gets read as an empty period.

**A date change is the only thing that can trigger that drop**, because the date window is the only
input to either option set (`P-RPT-11`). Selecting an action never ejects an actor and selecting an
actor never ejects an action, so the two selects cannot cascade into each other.

**No export control, no copy-all control, and no download link** (`P-RPT-10`, `P-RPT-11`).

**States.**

| State | What renders |
|---|---|
| **Empty** | The filters stay live, both selects showing their "any" option alone because both option sets are empty. One line: *"No changes were recorded in this period."* Not an error. |
| **Loading** | Row-height `--fr-surface-inset` blocks. Filters stay live. Previous rows are cleared. |
| **Error** | `COMPONENTS.md §6` banner replaces the list. Filters stay usable. Request id on 5xx only. |
| **Success** | Rows newest first, with a "Load older changes" control while a cursor remains. |
| **Partial** | **Never** for a single page: a page of rows arrives whole or not at all. Paging to older rows is an explicit action, and the page marker states which rows are shown. |
| **Forbidden** | A manager who follows a stale link sees the whole panel replaced by one line: *"This page is for administrators."* No filters, no empty list, nothing that implies the page would work with a different query. |

**Copy.**

| Where | Verbatim |
|---|---|
| Panel heading | "Change log" |
| Subheading | "Every change an administrator made, with what it was before and what it became." |
| Zone note | "All dates and times are Asia/Kolkata." |
| Field labels | "From" · "To" · "Action" · "Record type" · "Record id" · "Administrator" |
| Administrator select, first option | "Any administrator" |
| Administrator select, an option | the acting user's `actor_email`, exactly as returned. No role, no id, no decoration |
| Administrator select with an empty option set | "Any administrator" alone, plus the help line "Nobody changed anything in this period." |
| A selected administrator dropped by a date change | "The administrator filter was cleared. That account made no changes in this period." |
| Action select, first option | "Any action" |
| Action select with an empty option set | "Any action" alone, plus the help line "Nothing was changed in this period." |
| A selected action dropped by a date change | "The action filter was cleared. No change of that kind was recorded in this period." |
| Apply control | "Apply" |
| Result count announcement, one | "1 change." |
| Result count announcement, zero or more than one | "0 changes." · "12 changes." |
| Column headers | "When" · "Who" · "Action" · "Record" · "Before" · "After" |
| Pagination control | "Load older changes" |
| End of list | "That is the oldest change in this period." |
| Empty | "No changes were recorded in this period." |
| Wrong role (403) | "This page is for administrators." |
| Inverted range (422) | "The start date must be on or before the end date." |
| Bad date (422) | "The date must be written as YYYY-MM-DD." |
| Row id without a type (422) | "Choose a record type before filtering by record id." |
| Stale cursor (422) | "That page of results is no longer valid. Start again from the newest change." |
| Bad limit (422) | "Ask for between 1 and 200 rows." |
| Load failure (5xx) | "The change log could not be loaded. If you need help, quote `a1b2c3d4`." |

**Accessibility.**
- **Focus order:** From → To → Action → Record type → Record id → Administrator → Apply → row list →
  "Load older changes". **Every control in that order has a published string in the copy table
  above**, including the Apply control, which appeared in this focus order for several revisions
  with no words and no row in the fields table.
- Every input has a programmatically associated label, always visible, never a placeholder
  (`COMPONENTS.md §11`).
- A validation failure is associated with its field and **announced**, not only coloured
  (`FR-ADR-051`).
- The row list is a `<table>` with `<th scope="col">`. The before/after detail is a nested description
  structure with the field name as the term, so a screen reader reads
  "base_price_paise, before 25000, after 30000" rather than three unlabelled cells.
- A polite live region announces the result count after every filter change: **"1 change." at exactly
  one and "12 changes." at two or more** — the count is interpolated, so the string owes both forms
  and a string published with only the plural ships "1 changes" (`S7.21`). **Zero takes the plural**,
  "0 changes.", which is the ordinary English form and is also the empty state's own sentence one
  announcement earlier. The same
  region announces the administrator filter being cleared when its option leaves the option set, so a
  screen reader user is told the filter changed rather than finding a different result set with no
  explanation.
- The administrator select's options are labelled with the email address alone. **No option carries a
  role**, so no option can state a role the rows contradict.
- Target size `--fr-tap-min` on every control, including the pagination control.

---

## S6 — API endpoints

All paths sit under `/api/reports/`. Every one is a `GET`; the router mounts no write method
(`P-RPT-09`). Every one applies the role dependency and the scope dependency from `P-RPT-02` at the
router, never in a handler.

---

The dashboard endpoint. It returns the headline figures for one whole period and the per-film
breakdown, computed in one transaction at one snapshot so the parts always sum to the whole. This is
the only endpoint a manager or administrator needs in order to see a period's numbers.

```endpoint
{
  "id": "EP-RPT-01",
  "method": "GET",
  "path": "/api/reports/dashboard",
  "summary": "Return the headline figures and the per-film breakdown for one whole period",
  "auth": "role",
  "roles": ["manager", "admin"],
  "request": {
    "path_params": {},
    "query": {
      "period": "string, one of day|week|month, required",
      "date": "string, ISO-8601 date in Asia/Kolkata, optional, defaults to today from the injected clock",
      "screen_id": "integer, positive, optional, narrows within the caller's resolved scope and never widens it. An out-of-service hall is a valid value: it stays in scope so its past figures stay readable (P-RPT-02, P-ADM-16)."
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The complete figures for the period. Never partial.",
      "body": {
        "period": "string, the period type that was applied",
        "period_start_utc": "string, ISO-8601 instant, inclusive",
        "period_end_utc": "string, ISO-8601 instant, exclusive",
        "evaluated_at_utc": "string, ISO-8601 instant taken from the injected clock",
        "timezone": "string, the cinema's IANA zone, Asia/Kolkata",
        "scope_empty": "boolean, true when the caller has no halls assigned",
        "screen_ids": "array of integer, the halls this response actually covers. For an admin this is EVERY screen, never an empty array and never omitted — the resolver's internal None, meaning apply no screen filter, is an implementation detail and is not the wire value (P-RPT-02). An empty array means one thing only: a manager with no assignment, whose response covers nothing (P-RPT-08). Consistent with EP-RPT-03, which carries all_halls plus the full screens array.",
        "takings_paise": "integer, minor units, never a float and never a formatted string",
        "seats_sold": "integer",
        "capacity": "integer, the sum of seat_count_at_creation over the period's showtimes",
        "occupancy_pct": "number to one decimal place, or null when capacity is 0",
        "shows": "integer",
        "films": "array of {movie_id, title, shows, seats_sold, capacity, occupancy_pct, takings_paise}, at most 100, ordered by takings_paise DESC, then title ASC, then movie_id ASC. All three keys always: a film has no unique title, so the first two do not give a total order, and a non-total order under a 100-row cap makes which film falls off the end nondeterministic (P-RPT-05). Every client-side re-sort of this table falls back to the same two trailing keys.",
        "films_truncated": "boolean, true when the period held more than 100 distinct films and the films array was therefore capped. When true the per-film sums are STRICTLY LESS THAN the headline figures and P-RPT-07's parts-equal-the-whole identity does not hold; the headline figures remain complete, because they are computed over every showtime in the period and are never summed from films. SCR-RPT-01 renders a line saying the table is short."
      }
    },
    "401": {"description": "No token or an expired token"},
    "403": {"description": "The caller's role is not manager or admin, or screen_id is outside a manager's scope"},
    "404": {"description": "An admin passed a screen_id that does not exist"},
    "422": {"description": "period, date or screen_id failed validation"},
    "429": {"description": "The per-user rate limit is exhausted"},
    "500": {"description": "The aggregate failed. No partial figures are returned."},
    "503": {"description": "Redis is unreachable, so the rate limiter fails closed"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "per user, REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE, starting value 60. No per-IP bucket: every caller is authenticated and a shared office address would put twelve managers in one bucket. Fails closed with DEPENDENCY_UNAVAILABLE when Redis is unreachable.",
  "authorisation_rule": "The router resolves the caller's screen ids once, as a dependency: admin means no screen filter, manager means the set from manager_screen_assignment, possibly empty. The handler never reads a screen id from the request and checks it itself, and an empty set short-circuits to the empty-scope response rather than building an IN () predicate.",
  "satisfies": ["P-RPT-01", "P-RPT-02", "P-RPT-03", "P-RPT-04", "P-RPT-05", "P-RPT-07", "P-RPT-08", "P-RPT-12"],
  "brd": ["R-RPT-01", "R-RPT-02", "R-RPT-03", "R-RPT-04"]
}
```

---

The per-show listing. It is a detail view of the same period the dashboard endpoint summarised, kept
separate because a month across six halls is on the order of a thousand rows and the response would
otherwise be unbounded on a host with roughly 1 GB of memory in total. The interface renders these
rows; it never sums them to produce a headline figure.

```endpoint
{
  "id": "EP-RPT-02",
  "method": "GET",
  "path": "/api/reports/showtimes",
  "summary": "List every showtime in the period and in scope, with its own figures",
  "auth": "role",
  "roles": ["manager", "admin"],
  "request": {
    "path_params": {},
    "query": {
      "period": "string, one of day|week|month, required",
      "date": "string, ISO-8601 date in Asia/Kolkata, optional",
      "screen_id": "integer, positive, optional, narrows within the caller's resolved scope",
      "limit": "integer, 1..200, optional, default 50",
      "offset": "integer, >= 0, optional, default 0"
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "One page of showtime rows, ordered by starts_at ascending",
      "body": {
        "period_start_utc": "string, ISO-8601 instant, inclusive",
        "period_end_utc": "string, ISO-8601 instant, exclusive",
        "total": "integer, the number of showtimes in the period and in scope",
        "limit": "integer, the page size applied",
        "offset": "integer, the offset applied",
        "rows": "array of {showtime_id, starts_at, screen_id, screen_name, movie_id, title, seats_sold, capacity, occupancy_pct, takings_paise, has_started}. starts_at is ISO-8601 WITH THE CINEMA'S OFFSET, e.g. 2026-08-14T19:30:00+05:30, exactly as every customer-facing endpoint serialises an instant (P-BRW-06). It is NOT bare UTC and there is no _utc suffix: SCR-RPT-01 renders 14 Aug 2026, 7:30 pm from this field, and a client converting UTC to local would be a second implementation of FR-ADR-018 in a language with a different zone database — wrong on a device whose own clock is set to another country, and wrong again the moment EP-ADM-29 changes the cinema's zone. The client formats the string it is given and performs no zone arithmetic.",
        "timezone": "string, the cinema's IANA zone, Asia/Kolkata. Present so a reader of the raw response can tell which zone the offset above belongs to without inferring it from the offset."
      }
    },
    "401": {"description": "No token or an expired token"},
    "403": {"description": "Wrong role, or screen_id outside a manager's scope"},
    "404": {"description": "An admin passed a screen_id that does not exist"},
    "422": {"description": "period, date, screen_id, limit or offset failed validation"},
    "429": {"description": "The per-user rate limit is exhausted"},
    "500": {"description": "The query failed"},
    "503": {"description": "Redis is unreachable, so the rate limiter fails closed"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "per user, REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE, shared with EP-RPT-01. Fails closed with DEPENDENCY_UNAVAILABLE.",
  "authorisation_rule": "Identical to EP-RPT-01: the router dependency resolves the screen ids and the handler filters on the resolved set only. An empty set returns an empty page with total 0, never an unfiltered query.",
  "satisfies": ["P-RPT-01", "P-RPT-02", "P-RPT-04", "P-RPT-06", "P-RPT-08"],
  "brd": ["R-RPT-01", "R-RPT-02", "R-RPT-03"]
}
```

---

The scope endpoint. The interface needs to know which halls the caller may narrow to before it can
render the hall filter and the scope line, and it must not guess. This endpoint returns exactly what
the router dependency resolved, so the control the reader sees and the filter the server applies come
from one source.

```endpoint
{
  "id": "EP-RPT-03",
  "method": "GET",
  "path": "/api/reports/scope",
  "summary": "Return the halls this caller may read, as resolved by the router dependency",
  "auth": "role",
  "roles": ["manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "The caller's resolved reporting scope",
      "body": {
        "role": "string, manager or admin",
        "scope_empty": "boolean, true when a manager has no assignments",
        "all_halls": "boolean, true for an admin, meaning no screen filter is applied",
        "screens": "array of {screen_id, screen_name, is_active}, the halls the caller may read, empty for an unassigned manager. Halls that are OUT OF SERVICE are included, with is_active false: a withdrawn hall keeps every booking it ever had and excluding it would make its past takings unreadable (P-RPT-02, P-ADM-16). SCR-RPT-01 marks such a hall as out of service where it offers it, so an empty future period reads as expected rather than as a broken filter.",
        "timezone": "string, the cinema's IANA zone, Asia/Kolkata",
        "today": "string, ISO-8601 date, today in Asia/Kolkata from the injected clock"
      }
    },
    "401": {"description": "No token or an expired token"},
    "403": {"description": "The caller's role is not manager or admin"},
    "429": {"description": "The per-user rate limit is exhausted"},
    "500": {"description": "The scope resolution failed. This endpoint runs a query — it reads manager_screen_assignment joined to screen for a manager, and every screen for an admin — so it can fail like any other, and the universal internal-error floor reaches it."},
    "503": {"description": "Redis is unreachable, so the rate limiter fails closed"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "per user, REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE, shared with EP-RPT-01.",
  "authorisation_rule": "This endpoint returns the output of the same router dependency the other endpoints filter on. It never enumerates halls the caller may not read, so it cannot be used to discover which screen ids exist.",
  "satisfies": ["P-RPT-02", "P-RPT-08"],
  "brd": ["R-RPT-03"]
}
```

---

The change log. This is where an administrator answers the client's own question — who changed a price
— by reading the append-only audit rows written in the same transaction as each change. It is
administrator-only, which is stricter than the ruling requires, and it produces no file.

```endpoint
{
  "id": "EP-RPT-04",
  "method": "GET",
  "path": "/api/reports/audit",
  "summary": "List audit rows, newest first, filtered and cursor-paginated",
  "auth": "role",
  "roles": ["admin"],
  "request": {
    "path_params": {},
    "query": {
      "from": "string, ISO-8601 date in Asia/Kolkata, optional, defaults to 30 days before to",
      "to": "string, ISO-8601 date in Asia/Kolkata, optional, defaults to today from the injected clock",
      "action": "string, 1..64, exact match, optional",
      "entity_type": "string, 1..64, exact match, optional",
      "entity_id": "integer, positive, optional, requires entity_type",
      "actor_user_id": "integer, positive, optional",
      "limit": "integer, 1..200, optional, default 50",
      "cursor": "integer, positive, optional, an audit row id; returns rows with a LOWER id. It is a bound and not a lookup, so a well-formed id naming no audit_log row is NOT an error — it returns 200 with whatever rows fall below it, exactly as a well-formed non-member action or actor_user_id does on this endpoint. Only a malformed or non-positive value is 422 (P-RPT-11 rows 6 and 6a)."
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {
      "description": "One page of audit rows, ordered by id descending",
      "body": {
        "window_start_utc": "string, ISO-8601 instant, inclusive",
        "window_end_utc": "string, ISO-8601 instant, exclusive",
        "rows": "array of {id, occurred_at, actor_user_id, actor_email, actor_role, action, entity_type, entity_id, before, after, request_id}. occurred_at is ISO-8601 WITH THE CINEMA'S OFFSET, e.g. 2026-08-12T15:40:00+05:30, as every customer-facing endpoint already serialises an instant (P-BRW-06). It is NOT bare UTC and there is no _utc suffix: SCR-RPT-02 renders 12 Aug 2026, 3:40 pm from this field, and the client performs no zone arithmetic — a second implementation of FR-ADR-018 on the client is wrong on a device set to another country and wrong again when EP-ADM-29 changes the zone.",
        "timezone": "string, the cinema's IANA zone, Asia/Kolkata. Present for the same reason as on EP-RPT-02: a reader of the raw response can name the zone without inferring it from the offset.",
        "next_cursor": "integer or null, the id to pass as cursor for older rows",
        "available_actions": "array of string, the distinct action values present inside the DATE window [window_start_utc, window_end_utc), ordered ascending. Computed from from/to ALONE — the action and actor_user_id filters do not narrow it, and neither does the page. Under the other reading the select collapses to the option already chosen and the reader cannot switch filters without clearing one (P-RPT-11).",
        "available_actors": "array of {actor_user_id: integer, actor_email: string}, the distinct acting users present inside the same DATE window, ordered by actor_email ascending. Same rule as available_actions: from/to alone, never narrowed by action, actor_user_id or the page. Carries no role, because actor_role belongs to a row and not to a person"
      }
    },
    "401": {"description": "No token or an expired token"},
    "403": {"description": "The caller is not an admin. A manager receives this."},
    "422": {"description": "A date, an id, limit or cursor failed validation, or entity_id was sent without entity_type"},
    "429": {"description": "The per-user rate limit is exhausted"},
    "500": {"description": "The query failed"},
    "503": {"description": "Redis is unreachable, so the rate limiter fails closed"}
  },
  "errors": ["AUTH_REQUIRED", "FORBIDDEN", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change. Reading the audit log is not itself audited.",
  "rate_limit": "per user, REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE, shared with EP-RPT-01.",
  "authorisation_rule": "The router admits the admin role alone. A manager is refused before the handler runs, with no screen-scoped variant of this endpoint existing anywhere. available_actors is derived from the rows this window already returns and is not an account listing: it never names a staff account that wrote nothing inside the window, so this endpoint cannot be used to enumerate who holds an administrator account.",
  "satisfies": ["P-RPT-01", "P-RPT-10", "P-RPT-11"],
  "brd": ["R-ADM-06", "R-RPT-05"]
}
```

---

### New error codes this lane needs

Three, none of which exists in `FR-ADR-052`'s registry. Each is a general HTTP condition this epic
cannot express with a listed code, and none is a business failure that would deserve a bespoke name.

```newerrorcode
{"code":"FORBIDDEN","http":403,"when":"The caller is authenticated but their role or their resolved screen scope does not permit the request. Covers: a customer or guest calling any reports endpoint; a manager calling the change log; a manager passing a screen_id they are not assigned to, whether or not that hall exists; a manager reaching any administration write path.","raised_by":["EP-RPT-01","EP-RPT-02","EP-RPT-03","EP-RPT-04"],"why_needed":"The registry has AUTH_REQUIRED for 401 and HOLD_NOT_OWNED for a 403 specific to seat locks. There is no general role-refusal code, and every role-scoped surface in the product needs one. Reusing HOLD_NOT_OWNED here would be wrong in substance and would make the interface branch on a lock concept for a reporting refusal."}
```

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"An administrator names a resource that does not exist — here, a screen_id passed as a narrowing filter. A manager never receives this: an out-of-scope screen_id returns FORBIDDEN whether or not the hall exists, so the response is not an oracle for which screen ids exist.","raised_by":["EP-RPT-01","EP-RPT-02"],"why_needed":"The registry has no not-found code. Returning FORBIDDEN to an administrator for a typo would be misleading, and returning 500 would report a client error as a server fault and pollute the error rate the operator watches."}
```

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"A request parameter fails type, range or format validation: an unknown period, a malformed or impossible date, an inverted date range, a limit outside 1..200, a negative offset, a stale cursor, an entity_id without an entity_type.","raised_by":["EP-RPT-01","EP-RPT-02","EP-RPT-04"],"why_needed":"The registry's two 422 codes, SEAT_LIMIT_EXCEEDED and IDEMPOTENCY_KEY_REUSED, are both specific business rules. Without a general validation code, either every parameter failure invents its own code or the framework's default 422 escapes the error envelope in FR-ADR-052, which requires one envelope from every endpoint. The details object carries the offending field name."}
```

---

## Lane notes

### Article X candidates raised by this lane

**`PROPOSED-RPTSCOPE-01` — does a manager's current hall assignment give them that hall's whole history?**
`FR-ADR-011` models the assignment as one row per `(manager, screen)` with **no validity period**. So a
manager assigned to Hall 3 today reads Hall 3's takings for every period since the system started,
including periods before they were employed; and a manager removed from Hall 3 loses last month's
figures they were reading yesterday. This lane specifies the behaviour that follows from the ADR as
written — current assignment, all history — and **does not invent a validity window**, because adding
a start and end date to `manager_screen_assignment` would change an `APPROVED` ADR's table shape.
**It is raised rather than closed because it is a question about who may see money**, which is the
client's to answer. *(Class: reserved — access to financial data.)*

**`PROPOSED-RPTIMMUT-01` — can an administrator edit a showtime's film or start time after it has sold
tickets, and if so, `R-RPT-04` is not true.** `R-RPT-04` requires reported figures not to move.
Per-film aggregation joins `showtime.movie_id` live, and the period filter reads `showtime.starts_at`
live. `FR-ADR-039` snapshots the *price* onto `booking_seat` and `FR-ADR-022` freezes the *seat
layout* — **neither protects the film or the start instant.** If an administrator can correct either
after bookings exist, then last month's per-film figures change and a show can move between periods,
which is exactly the failure `FR-ADR-022` and `FR-ADR-039` were written to prevent in their own
dimensions. Two remedies exist and **both belong to other lanes**: refuse the edit once bookings
exist (an administration write path), or snapshot `movie_id` onto the booking (a data-model change).
This lane can specify neither, and **it will not silently accept a figure that moves.** Raised for the
merge pass to route. *(Class: cross-lane, and it contradicts a `RULED` BRD row.)*

### Assumptions I had to flag

| Flag | Status | Where it bites in this lane |
|---|---|---|
| **The manager role exists at all** | `PROVISIONAL` (`SRC-003 C-1`, `FR-ADR-009`) | The entire scoped surface. If the client reverses to three roles, `P-RPT-02`'s screen filter, `P-RPT-08`'s empty state, `EP-RPT-03`, and the manager half of every copy string are deleted, and the dashboard becomes an administrator screen with a hall filter. Flagged at the top of this section and on every P-row it touches. |
| **One cinema with six screens** | `PROVISIONAL` (`SRC-003 C-2`, `FR-ADR-010`) | Scoping attaches to the **screen**, not the cinema, throughout. No query in this lane filters by `cinema_id`. If a second venue appears, nothing in this epic changes — which is the point of scoping at the narrower level. |
| **"Two managers per hall"** | **observation, not a constraint** (`FR-ADR-011`) | Nothing in this lane assumes the number two, counts managers, or fails when a hall has one manager or none. There is no schema rule enforcing it and this lane does not introduce one. |
| **Hall sizes 90/120/150/180/200/220** | `ASSUMED` (`SRC-003 OPEN-SCALE-02`) | Every occupancy percentage in every worked example divides by an assumed denominator. `P-RPT-04` says so at the point of use. The **formula** is specified; the example capacities are not. |
| **Seat category names and uplifts** | `ASSUMED` (`SRC-003 OPEN-SEAT-01`) | `P-RPT-03`'s worked example uses a 3333 basis-point Premium uplift as an **example input, not a configured value**. Takings do not depend on category at all — they sum snapshotted per-seat prices — so no figure in this lane is sensitive to the category set. |
| **Sales close 15 minutes *after* the advertised start** | `PROVISIONAL` (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`) | `P-RPT-03` names the consequence: a finished day's takings can still rise for up to fifteen minutes into the next day. Under the alternative reading — fifteen minutes *before* — the effect vanishes entirely. |
| **Takings attributed to the show's date, not the purchase date** | `RULED`, **batched for the client to reverse** (`R-RPT-04`, `FR-ADR-043`) | `P-RPT-03` states it in the row rather than hiding it, gives the accountant's alternative, and names the two consequences: a future period already shows money, and advance sales are visible before the show happens. |
| **`EP-RPT-02` and `EP-RPT-04` returned bare UTC** | **defect corrected** (`P-RPT-01`, `EP-RPT-02`, `EP-RPT-04`) | Both reporting screens. `SCR-RPT-01` renders `14 Aug 2026, 7:30 pm` and `SCR-RPT-02` renders `12 Aug 2026, 3:40 pm`, and **neither response carried an offset or a zone** — so the only way to render either was a client-side conversion, which five rows elsewhere name as the wrong implementation and which is wrong on a device set to another country and wrong again when `EP-ADM-29` changes the zone. `starts_at_utc` → `starts_at` and `occurred_at_utc` → `occurred_at`, both with the cinema's offset, both with a `timezone` field beside them. **The `_utc` suffix is now load-bearing**: a field carrying it is a boundary and is never rendered; a field without it is rendered and carries the offset. `period_*_utc` and `window_*_utc` keep the suffix and stay bare UTC, and a table in `P-RPT-01` says why so they do not read as missed. **Assigned two waves ago, announced, and lost when the turn died.** |
| **The per-show table is not sortable** | **defect corrected**, `S1.2.1` case 2 (`SCR-RPT-01`) | The accessibility clause claimed sortable headers "for both tables" — thirteen cells — and published three sort-state names, while the fields table gave the per-show row only "ordered by start time ascending" and **`EP-RPT-02` accepts no sort parameter**. A client-side sort would reorder **the current page only**, so `sorted highest first` would be a claim about fifty rows dressed as a claim about the period, and the month's highest-takings show would sit unfound on page four. **The requirement was removed rather than the parameter invented** — server-side sorting on a paginated endpoint is a real feature with a real cost and no source asks for it. Six sortable cells, seven plain ones, the three strings scoped to the per-film table. |
| **The per-film order was not total** | **defect corrected** (`P-RPT-05`, `EP-RPT-01`) | The per-film table and its 100-row cap. `takings_paise DESC, title ASC` left genuine ties, because this row's own preconditions say four lines earlier that **a film has no unique title** and a re-release is a legitimate second row — so which film fell off the end of a capped list was decided by whatever order the database returned. `movie_id ASC` is now the third key, and every client-side re-sort falls back to the same two trailing keys. The document fixes this three times elsewhere in the same words; **a cap over a non-total order is its worst case, because the row that disappears is the one nobody can see is missing.** **Assigned two waves ago and lost when the turn died.** |
| **`EP-RPT-04`'s `cursor` had no rule for a well-formed unknown id** | **defect corrected** (`P-RPT-11`, `EP-RPT-04`) | Change-log paging. The row said only "not a valid row id → 422" and left the reachable case silent between 422, an empty page and the newest page. **A cursor is a bound, not a lookup** — `id < cursor` is well defined for any integer — so a well-formed id naming no row returns 200 with whatever falls below it, exactly as a well-formed non-member `action` or `actor_user_id` already does on this same endpoint. 422 is now scoped to malformed or non-positive values alone. |
| **`SCR-RPT-01`'s opening period is `Day`** | **`[JUDGMENT CALL]`** (`SCR-RPT-01`, `EP-RPT-01`) | The dashboard's first request, `GET /api/reports/dashboard?period=day` with `date` omitted. `period` is required and deliberately undefaulted, and the screen said only "exactly one is selected at all times" — so **Day and Month would have given two implementers entirely different headline figures on the first screen a manager ever sees**, each looking right to whoever built it. `Day` because today's takings can be checked against the building the reader is standing in, and because the narrowest period is the cheapest aggregate on a ~1 GB host. `date` is omitted rather than computed client-side, because the server owns "today" and a client computing it would be a second implementation of the one thing this epic says will be got wrong. Reversible: one default. |
| **`SCR-RPT-01` published no column header for either table** | **defect corrected**, the `S5` class | Both tables. The accessibility clause required `<th scope="col">` buttons carrying `aria-sort` — thirteen header cells — and the copy table published **none** of them, while the sibling `SCR-RPT-02` published all six of its own. **The per-show table's Start, Hall and Film columns are covered by nothing else on the screen**, so no other string named them. Six per-film headers, seven per-show headers, and three sort-state accessible-name forms added. |
| **Count-interpolated strings gained their singular** | **the class**, `S7.21` extended by E8 | `SCR-RPT-02`'s live region: `1 change.` at exactly one, `0 changes.` and `12 changes.` otherwise, with zero taking the plural. The per-show pagination position line, added last wave and therefore this lane's own, gained a one-row form rather than rendering `Shows 1 to 1 of 1`. **A string published with only the plural is how `1 changes` ships** — the same failure `S7.20` rule 4 spends a paragraph on for durations. |
| **The parts-equal-the-whole invariant is conditioned on `films_truncated`** | **defect corrected** (`P-RPT-05`, `P-RPT-07`, `EP-RPT-01`, `SCR-RPT-01`) | `P-RPT-07` asserted the per-film sums equal the headline **in every response** and called them test assertions, while `P-RPT-05` caps the list at 100 films. **Both cannot hold above 100.** The identity now holds when `films_truncated` is `false`, and the truncated case asserts the inequality plus `len(films) == 100` instead of being skipped. The headline stays complete because it is computed over the period and never summed from the list. `SCR-RPT-01` gained a state and a published line so a reader is told the table is short. |
| **Out-of-service halls stay in reporting scope** | `RULED` by `P-ADM-16`, applied here (`P-RPT-02`, `EP-RPT-01`, `EP-RPT-03`) | The hall filter and every figure. Excluding a withdrawn hall would make its past takings unreadable and would shrink last month's figures the day it was withdrawn, which `R-RPT-04` forbids. It is **marked** as out of service where it is offered — a label, not a filter — so an empty future period reads as expected rather than as a broken control. `EP-RPT-03`'s `screens` array gained `is_active`. |
| **`occurred_at` renders `12 Aug 2026, 3:40 pm`** | **defect corrected**, `S7.19` rules 2 and 3 | The change log's `When` column. `15:40` is a 24-hour clock on a surface an admin reads **in the interface**, which rule 3 forbids; the zone suffix went too, on rule 2 — the panel's zone note carries it once. `S7.19` named this string as the last of four still standing and it is now closed. The `P-RPT-11` example table was made conformant in the same pass so one row does not contradict the other. |
| **`SCR-RPT-01` and `SCR-RPT-02` — the class** | **defect corrected** | Eighteen strings added: the period stepper's six period-aware labels, the hall filter's label and both first options and the out-of-service suffix, the per-show pagination's two controls and position line, the truncation line, the action select's first option, its empty-set help line, its dropped-filter announcement, and the Apply control. **The Apply control sat in `SCR-RPT-02`'s focus order for several revisions with no words and no row in the fields table.** Direction on the pager is named by **time**, not page number, because the table is ordered by start time. |
| **The 429 wait is 1 second, not 30** | **defect corrected**, `S7.20` · `P-RPT-12` | `P-RPT-03` ex. 3, `P-RPT-12` ex. 3 and `SCR-RPT-01`'s copy table all published `Try again in 30 seconds.` The bucket is 60 per 60 s, so `ceil(60/60) = 1` and `S7.20` names this bucket as one where the **singular** ships. **Thirty was neither the capacity, the window, nor the refill interval.** Fourth instance of one class — a bucket's capacity or window written into copy that wanted its refill interval — so the arithmetic is now shown once in `P-RPT-12` and the other two point at it. |
| **`screen_ids` carries the halls the response covers; an admin gets every screen** | **defect corrected** (`P-RPT-02`, `EP-RPT-01`) | An admin previously emitted `[]` for "no filter", which was **byte-identical to an unassigned manager** while meaning the opposite, and would have rendered `SCR-RPT-01`'s `Halls shown:` line empty for the one caller who sees everything. The resolver's internal `None` no longer reaches the wire. `[]` now means one thing only. `EP-RPT-03` already carried `all_halls` and was left alone. |
| **The change log's option sets are computed over the date window alone** | **`[JUDGMENT CALL]`** (`P-RPT-11`, `EP-RPT-04`, `SCR-RPT-02`) | Both selects on `SCR-RPT-02`. **Decided because the other reading collapses each select to the option already chosen**, so a reader cannot switch filters without clearing one, and `SCR-RPT-02`'s drop-and-announce rule then cascades between the two selects. The old one-row worked example could not distinguish the readings; it is replaced with a three-row, two-action window where `rows` has one entry and both option sets have two. Reversible: one clause in the query. |
| **The occupancy denominator is the size of the showtime's materialised seat set** | **`[JUDGMENT CALL]`** — recorded as a **deferral**, not a decision of this lane (`P-ADM-14`, `FR-ADR-022`) | `P-RPT-04`'s denominator, and with it every occupancy figure in this epic. **Decided so that the numerator and the denominator are counted over one set**, which is what makes occupancy unable to exceed 100 %; the alternative — a denominator computed live from the screen's current seats — lets a seat added after the showtime existed be sold and counted while the denominator does not move. **The rule is `P-ADM-14`'s and is not restated here**; this lane names the column and points. Reversible in one place: if `P-ADM-14` changes what a seat set is, this row's denominator follows it with no change to any formula above. |

### Where I would have had to guess and did not

**Whether the dashboard should compare a period against the previous one.** No frozen source asks for
a change figure, a trend arrow or a percentage against last week. `SRC-001 §2.4` asks for visibility
into occupancy, revenue and popular showtimes; `§5.5.2` asks for three cuts. A comparison is a
different product decision and it would make every figure two figures. **Not built, not specified, not
mentioned in any copy string.**

**What "popular" is measured by.** `SRC-001 §2.4` asks for visibility into popular showtimes and never
says whether popular means seats sold, occupancy or takings — three different orderings of the same
table. Rather than pick a business definition, `P-RPT-05` makes every column sortable and defaults to
takings descending, logged as a reversible build-session judgment call. No definition of popular is
imposed.

**Whether a manager may see who bought a ticket.** Nothing grants it. `SRC-003 OPEN-OPS-03` makes
managers read-only and says nothing about customer data; `SRC-001 §7.6`'s "who booked this seat and
when" is a capability of the business, not of the manager role. **No endpoint in this lane returns a
customer name, an email address, a booking reference or a per-booking row.** Stated as a hard property
of the response shape in `P-RPT-10` rather than left as an omission.

**Whether a withdrawn showtime should be excluded from the figures.** `OPEN-SHOWCANCEL-01` is open and
`R-ADM-08` records that **no withdraw-showtime capability exists in v1**. So there is no state to
exclude and this lane writes no filter for one. It does not invent a `withdrawn` predicate against a
column nothing sets.

**What an administrator may do about a figure they think is wrong.** Nothing in this lane offers a
correction, an adjustment, a manual entry or a note. Every figure is derived from booking rows and the
only way to change one is to change a booking, which no endpoint in this version permits.

**How far back the anchor date may go.** Nothing is deleted (`SRC-003 OPEN-OPS-02`), so no retention
window exists to bound it, and inventing one would create a silent data cliff. `P-RPT-01` places no
bound and says why.

**The copy for a manager whose request failed because their account was just unassigned mid-session.**
The response is `P-RPT-08`'s empty-scope state, which already has its sentence. No second, distinct
"you have been removed" message is written, because nothing tells the server that an assignment was
removed rather than never granted, and writing a sentence that claims to know would be inventing
evidence.

### Contradictions and overlaps found, with both sides named

**1. `P-RPT-06`'s pagination against "partial is never rendered".** The brief and `R-RPT-04` require
that a partial period is never rendered. A paginated per-show list is, literally, a partial view. The
resolution written into `P-RPT-06` and `P-RPT-07` is that **the figures are always complete and the
listing is a listing** — the interface never sums the list to produce a headline number, and the
totals come from `EP-RPT-01`, which is computed over every showtime in the period. Named here rather
than left for a reviewer to notice.

**1a. `SCR-RPT-02`'s administrator filter had no data source, and it is a silence rather than a
conflict.** The action filter was specified end to end — `available_actions`, derived from the queried
window precisely so the options and the data cannot disagree — and **the administrator filter beside
it had no equivalent**. `EP-RPT-04` accepted `actor_user_id`, the screen rendered a select for it, and
nothing anywhere said where its options came from. **No endpoint in this product lists staff accounts
and none is added**: `available_actors` returns the distinct acting users inside the same window, by
the same mechanism and for the same reason. Closed in `P-RPT-11`, `EP-RPT-04` and `SCR-RPT-02`
together, so the rule, the wire shape and the control all say one thing. **The kind of defect that
resolves perfectly against every mechanical check** — every id existed, every citation resolved — and
is only visible to a reader who asks where a control's options come from.

**2. `COMPONENTS.md §10` does not cover the capacity-zero case.** `§10` gives two empty states — a
manager with no screens assigned, and a period with no bookings, the latter rendering `₹0.00` and
`0%`. It does not name **a period with no showtimes at all**, where the occupancy denominator is zero
and the percentage is undefined. `P-RPT-08` adds that third state and renders `—`, not `0%`. **This
extends `§10`; it does not contradict it**, and both existing states are preserved exactly as written.

**3. `P-RPT-12` extends `FR-ADR-058`'s rate-limit table by one row.** `FR-ADR-058` lists the limited
endpoints and their buckets; reporting endpoints are not among them, because they did not exist when
it was written. Adding a per-user bucket is a stricter control (Art III.10, needs no signature) and it
follows `FR-ADR-058`'s own convention of a starting value to be tuned once measured. **The row is
`REPORTS_RATE_LIMIT_PER_USER_PER_MINUTE`, starting value 60, per user only**, and it is carried in the
cross-cutting rate-limit table and configuration inventory, which are the single source for both.
**This lane holds no second copy of either table** — it names its one row and points at the floor.

**4. `R-ADM-06` is cited by this lane and is not one of its assigned rows.** `FR-ADR-019` places the
audit **reading** screen in Phase 8, which is this lane, while the audit **writing** rules belong with
the administration write paths. `P-RPT-11` specifies only the reading surface and says so in its first
paragraph. If another lane also specifies a change-log reader, that is a genuine duplicate and the
merge pass should keep one.

**5. Route namespace.** This lane claims the frontend routes `/dashboard` and `/dashboard/audit`, and
the API namespace `/api/reports/`. Neither was reserved by any ADR. If an administration lane has
claimed `/admin/…` for its own surfaces there is no collision; if it has also claimed `/dashboard`,
this is the collision to resolve.

**6. `SRC-001 §3.4` and `§2.3` are withdrawn** (`SRC-001 §E E-6`, `E-7`), and **nothing in this
dashboard reports on an import, a sync run, a created/updated/skipped count, or an external data
source.** There is no such thing to report on. Recorded because both clauses sit in the reporting
neighbourhood of the requirement document and a reader skimming `§2`–`§3` would find them.

### Not specified, and offered to the client rather than assumed

`SRC-003 OPEN-SCOPE-01` ends *"and other analytics things add more stuff that managers can do"*.
`FR-ADR-009` reads that as **read-only analytics only** and directs concrete additions into the PRD as
**candidates for the client to approve, never as ruled scope**. Three are listed below. **None has a
`P-`, `SCR-` or `EP-` id, none is built, and none may be built without a ruling.**

1. A comparison across the manager's **own** halls in one view — same period, one row per assigned
   hall. Read-only, uses no new data, and is the smallest possible addition.
2. A seats-remaining column on shows that are still selling, alongside the existing occupancy column.
   Read-only, derived from figures already computed.
3. A breakdown of takings and occupancy by day of week and by time of day, inside the chosen period.
   Read-only, and it is the shape of the question "which slots sell".

Anything that writes is excluded by `SRC-003 OPEN-OPS-03` and would be a defect
(`FR-ADR-009`), so no proposal above writes anything.
