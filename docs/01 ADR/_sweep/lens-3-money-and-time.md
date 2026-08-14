# Lens 3 — Money and time · raw sweep return

```
Run ........ 2026-08-14, GOAL_02
Method ..... independent sub-agent, read SRC-001 + SRC-002 + SRC-003 in full including both §E,
             plus CONSTITUTION.md Art V
Status ..... RAW. Not deduped, not merged, not adjudicated.
Format ..... <decision statement> | SOURCE: <clause id or NONE> | <status> | <RESERVED|TECHNICAL>
```

Currency is INR, market India, minor unit paise at ratio 100. | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED | RESERVED
All money is persisted as an integer number of paise, never a float, with Decimal only at the boundary and a formatted string only at render. | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED | RESERVED
The 100 minor-unit ratio is a one-way door held as a named configuration value and never changed by inference. | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED | RESERVED
Price is a base price per showtime plus a fixed percentage uplift per seat category, applied uniformly across every hall and every show. | SOURCE: SRC-003 OPEN-PRICE-01 | RULED | RESERVED
Base price is set per showtime rather than globally — this is a build-session reading of "the admin will set the ticket price" and is reversible. | SOURCE: SRC-003 OPEN-PRICE-01 | PROVISIONAL | RESERVED
Seat price = round(base_price x (1 + uplift_percent / 100)). | SOURCE: SRC-003 OPEN-PRICE-01 | RULED | RESERVED
The exact rounding mode where a percentage meets an integer number of paise (half-up, half-even, floor, ceiling) is not stated anywhere — only that a rule must be written. | SOURCE: NONE | OPEN | RESERVED
Whether rounding is applied per seat and then summed, or applied once to the booking total, is unstated. | SOURCE: NONE | OPEN | RESERVED
The storage type and precision of uplift_percent (integer percent, decimal, or basis points) is unstated. | SOURCE: NONE | OPEN | RESERVED
Whether a category uplift change reprices existing showtimes, and whether Standard is defined as 0% uplift, is unstated. | SOURCE: NONE | OPEN | RESERVED
Whether the paid amount is snapshotted onto the booking so a later base-price edit cannot rewrite what a past customer paid is unstated, though permanence of bookings is required. | SOURCE: SRC-001 §7.6 | OPEN | RESERVED
Three seat categories — Standard, Premium, Recliner — held in a table not an enum; the client said "you pick". | SOURCE: SRC-003 OPEN-SEAT-01 | ASSUMED | TECHNICAL
No separate tax line; the price shown is the price paid and the stored total is a single unsplittable figure. | SOURCE: SRC-003 OPEN-PRICE-03 | RULED | RESERVED
GST is deliberately absent and would have to be revisited before real money moves. | SOURCE: SRC-003 OPEN-PRICE-03 | RULED | RESERVED
No discount codes, no concession or student pricing, no booking fee, no convenience fee. | SOURCE: SRC-003 OPEN-PRICE-02 | RULED | RESERVED
No customer-initiated cancellation and no refund of any kind in v1; a confirmed booking is final. | SOURCE: SRC-003 OPEN-CANCEL-01 + OPEN-CANCEL-02, SRC-001 §E E-2 | RULED | RESERVED
The schema still carries booking status and a cancelled_at column, exposed by no v1 endpoint. | SOURCE: SRC-003 OPEN-CANCEL-01 | RULED | TECHNICAL
What happens to existing bookings and to the money when an admin withdraws a showtime is explicitly not closed. | SOURCE: SRC-003 OPEN-SHOWCANCEL-01 | OPEN | RESERVED
Payment is simulated only; no real provider is integrated at any point in this project's scope and the system never handles card data. | SOURCE: SRC-003 OPEN-PAY-01, SRC-001 §E E-10 | RULED | RESERVED
The payment state machine is pending -> authorized -> captured, plus failed, behind a real interface. | SOURCE: SRC-003 OPEN-PAY-02 | RULED | RESERVED
The simulated provider must be unreachable in a deployed environment without a deliberate visible flag, and checkout must state no real payment is taken. | SOURCE: SRC-003 OPEN-PAY-02 | RULED | RESERVED
Payment is collected before the booking is confirmed. | SOURCE: SRC-001 §5.3.1 | RULED | RESERVED
A customer is never charged twice for one booking attempt, including on refresh or double-click. | SOURCE: SRC-001 §5.3.2 | RULED | RESERVED
The booking confirmation endpoint takes an Idempotency-Key header and a repeat key returns the original result rather than a second booking or charge. | SOURCE: SRC-002 §8.3.1 | RULED | TECHNICAL
Idempotency key scope, storage medium, retention window and behaviour on key reuse with a different request body are unstated. | SOURCE: NONE | OPEN | TECHNICAL
How a simulated payment produces a `failed` outcome (injection flag, failure rate, or explicit test control) is unstated. | SOURCE: NONE | OPEN | TECHNICAL
The artificial delay of the simulated provider and whether it can outlive the 3-minute hold is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Whether payment capture and booking-row insertion occur in one atomic step, and what recovery runs if a container dies between them, is unstated beyond "no customer loses money". | SOURCE: SRC-001 §7.5 | OPEN | TECHNICAL
Maximum 10 seats per booking, enforced server-side and not only in the interface. | SOURCE: SRC-003 OPEN-BOOK-01 | RULED | TECHNICAL
The running total updates as seats are selected. | SOURCE: SRC-001 §5.2.4 | RULED | TECHNICAL
Currency rendering (symbol, Indian digit grouping, whether rupees-with-decimals or whole rupees is shown) is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Timezone is Asia/Kolkata. | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED | RESERVED
Whether a showtime's start is stored UTC, local, or both, and the column type used (timestamptz vs timestamp), is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Whether a showtime's end is stored or derived from movie runtime is unstated. | SOURCE: SRC-001 §5.1.1 | OPEN | TECHNICAL
India observes no DST and sits at a fixed +05:30, so no offset-transition handling is required. | SOURCE: NONE | ASSUMED | TECHNICAL
Sales close 15 minutes AFTER the advertised start time; the alternative reading is 15 minutes before and one client message reverses it. | SOURCE: SRC-003 OPEN-BOOK-03 | PROVISIONAL | RESERVED
Anyone already holding seats when the cut-off passes may finish checking out. | SOURCE: SRC-003 OPEN-BOOK-03 | RULED | RESERVED
Whether the cut-off is evaluated at hold acquisition, at booking confirmation, or both, is unstated. | SOURCE: NONE | OPEN | TECHNICAL
The seat hold is 3 minutes, read from a configuration value rather than a constant, superseding the 7 minutes in SRC-002 §8.1.1. | SOURCE: SRC-003 OPEN-HOLD-01, SRC-002 §E E-1 | RULED | TECHNICAL
Hold expiry is a Redis TTL that releases the seat with no cleanup job. | SOURCE: SRC-002 §8.1.4 | RULED | TECHNICAL
The lock is per seat, not per basket, because every seat is sold individually. | SOURCE: SRC-003 OPEN-SEAT-03, SRC-002 §8.1.1 | RULED | TECHNICAL
Whether the 3-minute clock restarts, extends, or runs per-seat when a customer adds or removes a seat mid-selection is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Whether the user-visible countdown is driven by a server-issued absolute expiry timestamp or a client-side timer is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Whether Redis TTL or a database timestamp is authoritative for expiry, and how clock skew between API instances is handled, is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Domain code must take an injected clock and a test that reads the wall clock is a defect — asserted only in derived guidance, not in any frozen source. | SOURCE: NONE | ASSUMED | TECHNICAL
Booking records are kept forever; nothing is ever deleted, no pruning job, no retention window, no cascade destroying a booking. | SOURCE: SRC-003 OPEN-OPS-02 | RULED | RESERVED
Nothing in this system runs on a schedule, which also rules out any timed expiry, pruning or reconciliation job. | SOURCE: SRC-003 OPEN-PROC-01, SRC-002 §E E-4 | RULED | TECHNICAL
Manager and admin dashboards report earnings, occupancy and per-movie performance over day, week and month. | SOURCE: SRC-003 OPEN-SCOPE-01 + OPEN-REPORT-01 | RULED | TECHNICAL
The calendar boundaries of those periods — midnight Asia/Kolkata vs UTC, week starting Monday or Sunday, calendar month vs rolling 30 days — are unstated. | SOURCE: NONE | OPEN | TECHNICAL
Which business day a late-night show crossing midnight belongs to for reporting is unstated. | SOURCE: NONE | OPEN | TECHNICAL
Whether dashboard revenue is recognised at payment capture or at showtime, and whether held-but-unpaid seats count, is unstated. | SOURCE: NONE | OPEN | RESERVED
The date boundary defining "today's showtimes" for the customer browse and filter path is unstated. | SOURCE: SRC-001 §5.1.3 | OPEN | TECHNICAL
A movie carries an admin-set display window with a start and an end; its timezone, inclusivity of endpoints, and effect on already-scheduled showtimes are unstated. | SOURCE: SRC-003 OPEN-ROLE-01 | OPEN | TECHNICAL
No CSV or spreadsheet export of revenue data; on screen only. | SOURCE: SRC-003 OPEN-REPORT-02 | RULED | TECHNICAL
Every admin price change writes an audit row in the same transaction as the change; whether that row captures the prior and new price is unstated. | SOURCE: SRC-003 OPEN-OPS-03 | RULED | TECHNICAL
Seed data spans about one month of showtimes and bookings so dashboard periods have real shapes. | SOURCE: SRC-003 OPEN-SEED-01 | RULED | TECHNICAL
Minimum turnaround gap between consecutive showtimes on one screen, and how far ahead showtimes may be created, are unstated. | SOURCE: NONE | OPEN | TECHNICAL
