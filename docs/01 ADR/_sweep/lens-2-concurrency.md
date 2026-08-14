# Lens 2 — Concurrency · raw sweep return

```
Run ........ 2026-08-14, GOAL_02
Method ..... independent sub-agent, read SRC-001 + SRC-002 + SRC-003 in full including both §E,
             plus CONSTITUTION.md Art IV
Status ..... RAW. Not deduped, not merged, not adjudicated.
Format ..... <decision statement> | SOURCE: <clause id or NONE> | <RULED|PROVISIONAL|OPEN|ASSUMED>
```

Redis lock is per `(showtime_id, seat_id)` with atomic acquire, an owner token, and self-expiry | SOURCE: SRC-002 §8.1.1/§8.1.2/§8.1.3/§8.1.4 | RULED
Hold TTL is 3 minutes read from configuration, not a constant | SOURCE: SRC-002 §E E-1 (SRC-003 OPEN-HOLD-01) | RULED
Booking confirmation takes a database-level guard: unique constraint on `(showtime_id, seat_id)` plus `SELECT ... FOR UPDATE` or optimistic locking | SOURCE: SRC-002 §8.1.5 / CONSTITUTION Art IV.2 | RULED
The database guard may never be waived; Redis being wrong must never oversell | SOURCE: CONSTITUTION Art IV.3 | RULED
If Redis is unreachable the seat-hold path returns an error and never falls back to the database for locks | SOURCE: SRC-002 §7.9 / Art IV.6 | RULED
Booking confirmation accepts an `Idempotency-Key` header and a repeated key returns the original result rather than a second booking | SOURCE: SRC-002 §8.3.1 / SRC-001 §5.3.2 | RULED
On SIGTERM the instance stops accepting requests, drains in-flight ones, releases its own Redis locks, then exits | SOURCE: SRC-002 §7.5 | RULED
Killing a container mid-request must not corrupt data, lose money, or leave a customer with a seat they did not get | SOURCE: SRC-001 §7.5 / SRC-002 §7.3 / Art IV.8 | RULED
`scripts/stress_seats.py` fires 50 simultaneous requests for one seat and asserts exactly one winner, runnable against local Docker and the deployed environment by base-URL swap | SOURCE: SRC-002 §9.1 / Art IV.4 | RULED
The red-proof drill drops the unique constraint, observes more than one winner, restores it, and verifies the restore | SOURCE: CONSTITUTION Art IV.5 | RULED
The lock is per individual seat, not per pair or per group, because no seat is sold as a pair | SOURCE: SRC-003 OPEN-SEAT-03 | RULED
A hold request may cover at most 10 seats, enforced server-side | SOURCE: SRC-003 OPEN-BOOK-01 | RULED
Only authenticated customers may acquire a hold; guests may read the seat map but never lock | SOURCE: SRC-003 OPEN-ROLE-01 / OPEN-BOOK-02 | RULED
Seat-map cache is per showtime with a short TTL and is invalidated on any booking or lock change, cache-aside | SOURCE: SRC-002 §8.2.1 | RULED
Cache stampede points are documented in code with the prevention used | SOURCE: SRC-002 §8.2.3 | RULED
Seat map is polled every 3 seconds rather than pushed, so the client's view is up to 3 seconds stale | SOURCE: SRC-002 §8.6.1 / SRC-001 §3.3 | RULED
A confirmed booking pushes a message to SQS and the worker sends the receipt email | SOURCE: SRC-002 §8.5.1 as corrected by SRC-002 §E E-5 | RULED
Worker retries are handled and a dead letter queue path is configured with failures made visible | SOURCE: SRC-002 §8.5.2 / SRC-003 OPEN-QUEUE-01 | RULED
Token-bucket rate limiting in Redis on seat selection and booking, per user and per IP, returning 429 with `Retry-After` | SOURCE: SRC-002 §8.4.1/§8.4.2 | RULED
Anyone already holding seats may finish checking out after the 15-minute sales cut-off | SOURCE: SRC-003 OPEN-BOOK-03 | PROVISIONAL
Whether the seat-hold write path is a single multi-seat atomic all-or-nothing acquire or a per-seat sequence with partial-success rollback | SOURCE: NONE | OPEN
Whether a partial multi-seat acquire releases the seats it did win, and whether that release is best-effort or guaranteed | SOURCE: NONE | OPEN
Whether the atomic acquire is a Lua script, a `SET NX PX` per key, or `MULTI/EXEC`, and where that choice is enforced | SOURCE: NONE | OPEN
Whether one lock token covers a whole selection (a hold id) or each seat key carries its own token | SOURCE: NONE | OPEN
Where the lock token is stored client-side and how it survives a page refresh so the customer keeps their own hold | SOURCE: NONE | OPEN
Whether a customer may extend or re-acquire an expiring hold, and whether the TTL refreshes on any activity | SOURCE: NONE | OPEN
Whether the same customer re-selecting a seat they already hold is a no-op, an error, or a TTL refresh | SOURCE: NONE | OPEN
Whether one customer may hold seats across two showtimes or two devices simultaneously, and any cap on concurrent holds per user | SOURCE: NONE | OPEN
Transaction isolation level for the booking confirmation transaction (READ COMMITTED vs REPEATABLE READ vs SERIALIZABLE) | SOURCE: NONE | OPEN
Whether the booking transaction takes `SELECT ... FOR UPDATE` or optimistic locking, given SRC-002 §8.1.5 offers both | SOURCE: SRC-002 §8.1.5 | OPEN
What rows the `FOR UPDATE` locks and in what deterministic order, to avoid deadlock between two multi-seat bookings that overlap | SOURCE: NONE | OPEN
Whether a unique-constraint violation on confirm is retried, mapped to a user-facing 409, or both, and how many times | SOURCE: NONE | OPEN
Whether the unique constraint is partial (excluding cancelled bookings) or total, given the schema retains a booking status and `cancelled_at` | SOURCE: SRC-003 OPEN-CANCEL-01/-02 | OPEN
Whether seat occupancy lives on a `booking_seat` row or a denormalised column, which determines what the unique index can even be declared on | SOURCE: NONE | OPEN
The exact boundary of the confirm transaction: whether payment capture, booking insert, audit row and SQS enqueue are inside or outside it | SOURCE: NONE | OPEN
Whether the SQS enqueue uses a transactional outbox or a post-commit send, and what happens if the send fails after commit | SOURCE: NONE | OPEN
Whether the Redis lock is released, left to expire, or converted to a permanent marker after a successful booking | SOURCE: NONE | OPEN
Which side wins when a hold expires in Redis in the same instant the confirm transaction is running: whether confirm re-validates lock ownership before insert | SOURCE: NONE | OPEN
Whether the confirm path requires a live valid lock at all, or relies solely on the database constraint if the hold has lapsed | SOURCE: NONE | OPEN
Whether payment capture happens before or after the seat row is durably written, and what unwinds if the other half fails | SOURCE: SRC-003 OPEN-PAY-02 | OPEN
What the simulated provider's `pending → authorized → captured` transitions do under a concurrent duplicate confirm for the same booking attempt | SOURCE: SRC-003 OPEN-PAY-02 | OPEN
Idempotency key scope, storage medium (Redis vs Postgres), TTL, and whether it is namespaced per user | SOURCE: NONE | OPEN
What the endpoint returns when the same idempotency key arrives while the first request is still in flight (409, block, or replay) | SOURCE: NONE | OPEN
What happens when the same idempotency key is presented with a different request body | SOURCE: NONE | OPEN
Whether the idempotency record is written in the same transaction as the booking, which decides whether a crash mid-commit can duplicate | SOURCE: NONE | OPEN
How the worker suppresses a duplicate receipt email under SQS at-least-once delivery (dedupe key, sent-at marker, or standard-queue visibility only) | SOURCE: SRC-002 §8.5.2 | OPEN
Whether the SQS queue is standard or FIFO, and the visibility timeout relative to SES call latency | SOURCE: NONE | OPEN
Maximum receive count before a message goes to the dead letter queue, and who or what drains it | SOURCE: SRC-002 §8.5.2 | OPEN
What the customer sees, and what state the booking is in, when SES fails after payment is captured | SOURCE: SRC-003 OPEN-EMAILFAIL-01 | OPEN
Whether the worker also honours SIGTERM by finishing or returning its in-flight message, and its drain deadline | SOURCE: SRC-002 §7.5 | OPEN
How an instance tracks "locks held by that instance" for SIGTERM release, given containers are stateless and hold state lives in Redis | SOURCE: SRC-002 §7.5 vs §7.3 | OPEN
Whether SIGTERM release drops customer holds that are still legitimately live, and whether that is the intended behaviour | SOURCE: NONE | OPEN
The graceful shutdown grace period and its relationship to the 3-minute hold TTL and the ALB deregistration delay | SOURCE: NONE | OPEN
Whether a hold acquired on one API instance can be released or confirmed by another instance behind the ALB | SOURCE: NONE | OPEN
Whether Redis unavailability also fails the browse and seat-map read path, or only the hold and booking write path | SOURCE: SRC-002 §7.9 | OPEN
Whether `/health/ready` returning 503 on Redis loss pulls every instance out of the ALB and thereby takes down read traffic too | SOURCE: SRC-002 §7.4 vs §7.9 | OPEN
Redis client behaviour on partial failure: connect timeout, command timeout, retry count, and whether a retry can double-acquire | SOURCE: NONE | OPEN
Whether Redis persistence or failover is assumed, and what a single-node ElastiCache restart does to every live hold | SOURCE: SRC-002 §5.2.3 | OPEN
What an admin editing or withdrawing a showtime does to live holds and in-flight checkouts on that showtime | SOURCE: SRC-003 OPEN-SHOWCANCEL-01 | OPEN
Whether an admin may change a showtime's base price while a customer holds seats, and which price the confirm uses | SOURCE: SRC-003 OPEN-PRICE-01 | OPEN
Whether an admin may change a seat-category uplift percentage mid-checkout, given it applies uniformly across all halls and shows | SOURCE: SRC-003 OPEN-PRICE-01 | OPEN
Whether the price is captured at hold time or recomputed at confirm time, and where that snapshot is stored | SOURCE: NONE | OPEN
Whether a screen's seat layout may be edited while showtimes exist, and what happens to held or booked seats that disappear | SOURCE: SRC-001 §9.3 | OPEN
Concurrency control for two admins editing the same movie or showtime (last-write-wins, version column, or row lock) | SOURCE: NONE | OPEN
Whether the audit row written in the same transaction as an admin change makes admin writes serialise, and what conflict that creates under concurrent edits | SOURCE: SRC-003 OPEN-OPS-03 / CLAUDE.md invariants | OPEN
Whether the seat-map cache invalidation is transactional with the booking commit or a best-effort post-commit delete that can leave a stale map | SOURCE: SRC-002 §8.2.1 | OPEN
Whether concurrent invalidations can resurrect a stale seat map (read-then-write race in cache-aside) | SOURCE: SRC-002 §8.2.1 | OPEN
Whether the `seat lock counts` metric is read from Redis on every scrape and whether that scan is safe at 220 seats × six halls | SOURCE: SRC-002 §7.7 | OPEN
Whether rate limiting can reject a legitimate retry of a booking confirm carrying an already-seen idempotency key | SOURCE: SRC-002 §8.4.1 vs §8.3.1 | OPEN
Whether the rate limiter's token bucket is itself atomic in Redis and what it does when Redis is down | SOURCE: SRC-002 §8.4.1 vs §7.9 | OPEN
Whether the stress script's 50 requests authenticate as 50 distinct users, and whether the rate limiter would mask the concurrency result | SOURCE: SRC-002 §9.1 / SRC-003 OPEN-SCALE-03 | OPEN
Whether the red-proof drill runs only locally or also against the deployed environment, and who authorises dropping a constraint there | SOURCE: CONSTITUTION Art IV.5 | OPEN
Whether the stress test asserts one winner at the HTTP layer, the database layer, or both, and how the losing 49 responses are shaped | SOURCE: SRC-002 §9.1 | OPEN
Time is injected rather than read from the wall clock in tests, which forces hold expiry to be a testable clock rather than a sleep | SOURCE: CLAUDE.md Definition of Done | RULED
Whether expiry is evaluated against Redis TTL alone or against a stored `held_until` timestamp the database can also see | SOURCE: SRC-002 §8.1.4 | OPEN
That no cleanup job exists means an abandoned hold leaves no database row to reconcile — whether a hold is persisted at all is undecided | SOURCE: SRC-002 §8.1.4 | OPEN
Load test at 50 concurrent bookers is an assumption the client declined to make, so no capacity decision may harden on it | SOURCE: SRC-003 OPEN-SCALE-03 | ASSUMED
Six halls of 90–220 seats is assumed, so seat-map payload size and lock-key cardinality are not constrained by a ruling | SOURCE: SRC-003 OPEN-SCALE-02 | ASSUMED
Nothing in the system runs on a schedule, so no scheduled reconciler may be introduced to clean stale locks or orphaned bookings | SOURCE: SRC-002 §E E-4 (SRC-003 OPEN-PROC-01) | RULED
The worker is the only other process touching booking data, which bounds every write-write race to API-versus-API | SOURCE: SRC-003 OPEN-PROC-01 | RULED
