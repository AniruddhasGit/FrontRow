# Lens 1 — Data shape · raw sweep return

```
Run ........ 2026-08-14, GOAL_02
Method ..... independent sub-agent, read SRC-001 + SRC-002 + SRC-003 in full including both §E
Status ..... RAW. Not deduped, not merged, not adjudicated. Evidence of the sweep, not a decision.
Format ..... <decision statement> | SOURCE: <clause id or NONE> | <RULED|PROVISIONAL|OPEN|ASSUMED>
```

> Kept unedited. Where the merge pass disagreed with a line here, the merge pass is recorded in
> `lens-merge.md` and the line below is left standing — an amended sweep is not evidence of a sweep.

Movie entity carries poster, synopsis, runtime, certification, language and genre attributes | SOURCE: SRC-001 §5.1.1 | RULED
Movie has an admin-set display window with a start and an end | SOURCE: SRC-003 OPEN-ROLE-01 | RULED
No external-id column, no import/pending state and no upsert key on movie | SOURCE: SRC-002 §E E-2 | RULED
Default movie listing order is newest first, with customer-chosen filter overriding | SOURCE: SRC-003 OPEN-TMDB-01 | RULED
No "upcoming release" flag, status or separate listing surface | SOURCE: SRC-001 §E E-5 | RULED
Poster is stored in S3 and the row holds our own URL, never a hotlink | SOURCE: SRC-002 §10.6.3 (survives via §E E-2) | RULED
A `cinema` entity exists in the schema even though exactly one row exists at launch | SOURCE: SRC-003 C-2 | PROVISIONAL
Six screens belong to the one cinema | SOURCE: SRC-003 OPEN-SCOPE-01 | RULED
Manager scoping attaches to screen, not to cinema | SOURCE: SRC-003 C-2 | PROVISIONAL
Role set is exactly guest, customer, manager, admin, with no staff/door role and no admin tiers | SOURCE: SRC-003 C-1 / SRC-001 §E E-1 | PROVISIONAL
Screen seat counts are 90/120/150/180/200/220 | SOURCE: SRC-003 OPEN-SCALE-02 | ASSUMED
Seat categories are a lookup table with three seeded rows, not a database enum | SOURCE: SRC-003 OPEN-SEAT-01 | ASSUMED
No accessible-seat marking attribute on seat | SOURCE: SRC-003 OPEN-SEAT-02 | RULED
No paired/couple-seat linkage between seat rows | SOURCE: SRC-003 OPEN-SEAT-03 | RULED
No gap/adjacency rule modelled on seat selection | SOURCE: SRC-003 OPEN-SEAT-04 | RULED
Every seat is an individually lockable and individually sellable unit | SOURCE: SRC-003 OPEN-SEAT-03 | RULED
Unique constraint on `(showtime_id, seat_id)` is the non-waivable oversell guard | SOURCE: SRC-002 §8.1.5 | RULED
Seat holds live only in Redis with a config-driven 3-minute TTL and have no Postgres table | SOURCE: SRC-002 §E E-1, §8.1.1, §7.9 | RULED
Maximum 10 seats per booking, enforced server-side | SOURCE: SRC-003 OPEN-BOOK-01 | RULED
A booking always carries a non-null FK to a user row; no anonymous order exists | SOURCE: SRC-003 OPEN-BOOK-02 | RULED
One booking references exactly one showtime and one or more seats | SOURCE: SRC-001 §9.2 | RULED
Booking carries a unique human-typable reference avoiding 0/O and 1/I/l | SOURCE: SRC-003 OPEN-TICKET-01 | RULED
No QR-code artifact, column or generation step anywhere | SOURCE: SRC-002 §E E-5 | RULED
No used-ticket, checked-in or validated state on booking | SOURCE: SRC-003 OPEN-TICKET-02 / SRC-001 §E E-3 | RULED
Booking retains a status column and a `cancelled_at` column that no v1 endpoint exposes | SOURCE: SRC-003 OPEN-CANCEL-01/-02 | RULED
No refund entity, no cancellation record and no customer-initiated cancellation path | SOURCE: SRC-001 §E E-2 | RULED
Payment states are exactly pending, authorized, captured, failed | SOURCE: SRC-003 OPEN-PAY-02 | RULED
No card-shaped column, fixture or seed value exists in the schema | SOURCE: SRC-003 OPEN-PAY-01 / SRC-001 §E E-10 | RULED
All money is an integer count of paise with a fixed minor-unit ratio of 100 and currency INR | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED
Showtime carries a base price in paise set per showtime rather than a single global price | SOURCE: SRC-003 OPEN-PRICE-01 | PROVISIONAL
Seat-category uplift is one global percentage per category, applied uniformly to every hall and show | SOURCE: SRC-003 OPEN-PRICE-01 | RULED
No discount, promo-code, concession or booking-fee entity | SOURCE: SRC-003 OPEN-PRICE-02 | RULED
No tax column and no split of the total into net and tax | SOURCE: SRC-003 OPEN-PRICE-03 | RULED
Booking confirmation is keyed by a stored `Idempotency-Key` so a replay returns the original booking | SOURCE: SRC-002 §8.3.1 | RULED
An audit row is written for every privileged admin write in the same transaction as the change, from Phase 2 | SOURCE: SRC-003 OPEN-OPS-03 | RULED
The schema must answer "who booked this seat and when" for any seat | SOURCE: SRC-001 §7.6 | RULED
Nothing is ever deleted; no retention window, no pruning job, no cascade that destroys a booking | SOURCE: SRC-003 OPEN-OPS-02 | RULED
Users authenticate by email and password hash held in our own table, with JWT sessions and no Cognito | SOURCE: SRC-002 §4.8 / SRC-001 §5.4.1 | RULED
Showtimes are only ever created by a human admin, never generated | SOURCE: SRC-001 §9.4 / §5.6.3 | RULED
Sales close 15 minutes after advertised start, so showtime needs a derivable cut-off instant | SOURCE: SRC-003 OPEN-BOOK-03 | PROVISIONAL
Seed data is structural only, with placeholder movie rows like `DEMO MOVIE 01` and roughly one month of showtimes and bookings | SOURCE: SRC-003 OPEN-SEED-01 | RULED
No CSV/spreadsheet export table or download artifact | SOURCE: SRC-003 OPEN-REPORT-02 | RULED
Dashboard reporting is over day, week and month for earnings, occupancy and per-movie performance | SOURCE: SRC-003 OPEN-REPORT-01 / OPEN-SCOPE-01 | RULED
Primary key type across all tables — bigserial versus UUID versus ULID | SOURCE: NONE | OPEN
Whether internal numeric ids are ever exposed in public URLs or an opaque public identifier is required | SOURCE: NONE | OPEN
Exact character set, length and collision-retry strategy for the booking reference | SOURCE: NONE | OPEN
Whether the booking reference is the primary key or a separate unique column alongside a surrogate key | SOURCE: NONE | OPEN
Seat identity decomposition — row label plus seat number versus a single label — and the uniqueness constraint over `(screen_id, …)` | SOURCE: NONE | OPEN
How the physical layout is represented: grid coordinates, aisles, gaps and non-seat cells | SOURCE: NONE | OPEN
What happens to seats and bookings when a screen's layout is edited after bookings exist (versioning or immutability of layout) | SOURCE: NONE | OPEN
Whether the price actually charged is snapshotted onto each booked-seat row or recomputed from live base price and uplift | SOURCE: NONE | OPEN
Whether seat-category uplift percentages and showtime base prices are versioned or mutated in place | SOURCE: NONE | OPEN
The rounding rule for `base_price × (1 + uplift/100)` and whether the rounded figure is stored | SOURCE: NONE | OPEN
Whether payment is a separate table or columns on booking, and its cardinality with booking | SOURCE: NONE | OPEN
Booking status enumeration values and their legal transitions | SOURCE: NONE | OPEN
Idempotency record shape: scope key, uniqueness, stored response body, and lifetime given nothing is deleted | SOURCE: NONE | OPEN
Audit log column shape — actor, action vocabulary, entity type and id, before/after payload — and whether rows are append-only enforced | SOURCE: NONE | OPEN
Whether reads (manager dashboard views) generate audit rows or only writes | SOURCE: NONE | OPEN
Foreign-key ON DELETE behaviour for every relationship given that nothing is ever deleted | SOURCE: NONE | OPEN
Whether any entity uses soft-delete (`deleted_at`, `is_active`) for movies, showtimes, screens or users | SOURCE: NONE | OPEN
Uniqueness rule for movie — title alone, title plus year, or no natural key | SOURCE: NONE | OPEN
Whether language, certification and genre are free text, PostgreSQL enums, or lookup tables, and whether genre is many-to-many | SOURCE: NONE | OPEN
Whether "format" from the customer filter is an attribute of screen, of showtime, or an entity, and its permitted values | SOURCE: SRC-001 §5.1.3 | OPEN
Whether a movie may carry more than one poster and whether poster URL is nullable | SOURCE: NONE | OPEN
Whether showtime stores an end time or derives it from movie runtime, and whether overlapping showtimes on one screen are constrained | SOURCE: NONE | OPEN
Timestamp storage type and whether all instants are `timestamptz` in UTC with Asia/Kolkata applied at render | SOURCE: NONE | OPEN
Whether the manager-to-screen assignment is a join table and whether the "2 managers per hall" figure is a database constraint or an observation | SOURCE: SRC-003 OPEN-SCOPE-01 | OPEN
Whether a user holds one role as a column or many roles via a table, and whether admin is modelled as a superset or a distinct row | SOURCE: NONE | OPEN
Email uniqueness, case-folding and normalisation rule on the user table | SOURCE: NONE | OPEN
Whether the user table carries an email-verification state, and whether an unverified user may book | SOURCE: NONE | OPEN
Password hash algorithm and whether the hash parameters are stored per row | SOURCE: NONE | OPEN
Whether account deletion or anonymisation is possible at all, given the never-delete ruling | SOURCE: NONE | OPEN
Whether a receipt-send attempt is recorded as a row (status, attempts, SES message id) or left untracked | SOURCE: SRC-003 OPEN-EMAILFAIL-01 | OPEN
What the schema records when SES fails after payment is captured | SOURCE: SRC-003 OPEN-EMAILFAIL-01 | OPEN
Whether the SQS enqueue after booking confirmation uses a transactional outbox table or a direct post-commit send | SOURCE: NONE | OPEN
What happens to booking and booked-seat rows when an admin withdraws a showtime that already has bookings | SOURCE: SRC-003 OPEN-SHOWCANCEL-01 | OPEN
Whether a poster's provenance must be recorded on the movie row to satisfy a possible attribution obligation | SOURCE: SRC-003 OPEN-ATTRIB-01 | OPEN
Index set required by the seat-map read path, dashboard aggregation and reference lookup | SOURCE: NONE | OPEN
Whether dashboard figures are computed live or persisted as rollup tables | SOURCE: NONE | OPEN
Occupancy denominator definition — seats configured at showtime creation versus current screen seat count | SOURCE: NONE | OPEN
Revenue definition for the dashboard — captured payments only versus all confirmed bookings | SOURCE: NONE | OPEN
Whether `created_at`/`updated_at` are present on every table and who writes them | SOURCE: NONE | OPEN
Whether the 10-seat cap is a database check constraint as well as an application rule | SOURCE: NONE | OPEN
Whether cinema carries address, contact or geography fields at all, given one row | SOURCE: NONE | OPEN
Whether a currency column exists per money value or currency is a single system-wide constant | SOURCE: NONE | OPEN
