# Dashboard periods are calendar boundaries in Asia/Kolkata, and revenue is money actually captured

```
ADR id ............ FR-ADR-043
Pack .............. PACK-MONEY
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-REPORT-01; SRC-003 OPEN-SCOPE-01; SRC-003 OPEN-LOCALE-01; SRC-001 §5.5.2; SRC-001 §2.4; SRC-001 §3.5
Constitution ...... frontrow-constitution@0.1.0
```

> **Part of this is reserved-but-reversible, decided and batched for the client to reverse**
> (Art III.9): what counts as revenue is a money definition. It is reversible — the figure is
> recomputed from stored rows on every request, so changing the definition changes the report and
> rewrites no data.

## Context

`SRC-003 OPEN-SCOPE-01` says a manager sees "earnings movies for the day, month, week" for their
halls. `OPEN-REPORT-01` confirms a dashboard for managers and admins. `SRC-001 §5.5.2` asks for
occupancy and revenue per show, per day and per movie, and `§3.5` says management should see occupancy
without asking anyone for a report.

Three things are undetermined and each changes the number on the screen.

**Where a period starts and ends.** Midnight in which zone, weeks starting on which day, a calendar
month or a rolling thirty days.

**Which day a late-night show belongs to.** A show at 23:45 that ends at 02:10 is one business
evening and two calendar dates.

**What counts as revenue.** Money captured, or bookings confirmed, or seats held. And what the
occupancy denominator is.

## Decision

**All period boundaries are calendar boundaries in the cinema's zone, Asia/Kolkata**, taken from the
injected clock (`FR-ADR-018`). Never UTC, and never the container's local time.

- **Day** — midnight to midnight, Asia/Kolkata.
- **Week** — **Monday to Sunday**, ISO-8601. Monday because it is the ISO standard and because the
  alternative, Sunday, is a regional convention that would have to be chosen without a ruling. This is
  a display convention and the client may reverse it.
- **Month** — the calendar month, not a rolling thirty days. "Month" in the client's answer sits
  alongside "day" and "week", which are both calendar periods.

**A showtime belongs to the calendar date of its `starts_at`, in Asia/Kolkata.** A 23:45 show belongs
to the date it starts, not the date it ends. That matches how a cinema publishes its listings and it
matches what the customer's date filter selected.

**Revenue is the sum of `booking_seat.price_paise` for confirmed bookings whose payment reached
`captured`.**

- Money **actually taken**, not money promised. A booking whose payment failed contributes nothing.
- **Held-but-unpaid seats contribute nothing.** A hold is not revenue and showing it as such would
  make the figure fluctuate as customers browse.
- **Recognised at payment capture**, attributed to the **showtime's date**, not the booking's date. A
  ticket bought on Monday for Friday's show is Friday's revenue, because the manager is reading
  performance per show. `SRC-001 §5.5.2` asks for revenue per show, which settles the attribution.
- Summed from the **snapshotted** `price_paise` (`FR-ADR-039`), never recomputed from current prices.

**Occupancy is `seats sold ÷ seat_count_at_creation`** for the showtime (`FR-ADR-022`), expressed as a
percentage. Using the showtime's recorded seat count rather than the screen's current one means
retiring a seat next month does not change last month's reported occupancy.

**Per-movie performance** aggregates the above across every showtime of that movie inside the period
and inside the caller's screen scope.

**Manager scope is applied in the query, from the router dependency** (`FR-ADR-011`), never from a
screen id in the request. Admins run the same queries with no screen filter.

**Figures are computed live from the source rows on every request. There are no rollup tables.** At
this scale — six halls, roughly a month of data at a time — the aggregation is small, and a rollup
would need something to maintain it. There is no scheduler (`FR-ADR-005`), so a rollup would have to
be updated on the write path, which puts reporting work inside the booking transaction.

## Alternatives rejected

**Boundaries in UTC.** Rejected. Midnight UTC is 05:30 in Kolkata, so "today's earnings" would include
the previous evening's late shows and exclude the current one until half past five in the morning.

**Attribute a late show to the date it ends.** Rejected. It splits one evening's trading across two
dates and disagrees with the listing the customer bought from.

**Recognise revenue at booking date rather than showtime date.** Rejected on `SRC-001 §5.5.2`, which
asks for revenue per show. It is the other defensible answer — it is what an accountant would want —
and it is the specific part offered for the client to reverse.

**Count confirmed bookings regardless of payment state.** Rejected. Under `FR-ADR-029` a booking
cannot commit without a capture, so the two nearly coincide today — but tying the report to the
payment state means the definition survives if that ever changes.

**Compute occupancy from the screen's current seat count.** Rejected above: it rewrites history.

**Maintain rollup tables for speed.** Rejected above, and recorded as the thing to reach for if the
dashboard becomes slow. It would need the write path or a schedule, and there is no schedule.

## Source

`SRC-003 OPEN-REPORT-01` (a dashboard for managers and admins) · `OPEN-SCOPE-01` (day, week, month;
earnings) · `OPEN-LOCALE-01` (Asia/Kolkata) · `SRC-001 §5.5.2` (occupancy and revenue per show, per
day, per movie) · `§2.4` (visibility into occupancy, revenue and popular showtimes) ·
`§3.5` (without asking anyone for a report).

Boundaries, attribution and the revenue definition are the build session's under Art III.9, with the
revenue definition batched for client reversal.

## Consequences

`SUM()` over a `bigint` column returns `numeric`, which arrives in Python as `Decimal` and mixes
badly with `int`. `GOTCHAS.md` records it and this is the query where it bites. Cast back to
`BigInteger` in the query.

Every dashboard figure is testable against a fixed injected clock and a seeded dataset. A test that
reads the wall clock here would go red on the first of the month with no code change.

The seed script generates about a month of bookings (`FR-ADR-067`), which is what gives the day, week
and month views real shapes to test against. That is why the client asked for a month.

Live computation means the dashboard's cost grows with the data, and nothing is deleted
(`FR-ADR-012`). At six halls it will not matter for a long time. The query needs an index on
`showtime.starts_at` and on `booking.showtime_id`, and the runbook should carry the response time as a
figure to watch. *(reasoned, not observed.)*

**No CSV or spreadsheet export exists** (`OPEN-REPORT-02`). On screen only, which also keeps
customer-level booking data off any download path.
