# 03 — The concurrency model

> **compressed per SRC-004 R-1. The single most important document in this folder.** If you are
> writing `domain/locking.py`, `domain/booking.py`, a migration that touches `booking_seat`, or
> `scripts/stress_seats.py`, read all of it.
>
> Sources: `FR-ADR-024`..`FR-ADR-035`, `P-HLD-01`..`P-HLD-14`, `P-PAY-09`..`P-PAY-11`, `P-XCT-01`,
> `P-XCT-08`, `P-XCT-09`, `P-XCT-17`. Those win on any disagreement.

## The guarantee, in one paragraph

**A seat is never sold twice, and that is enforced twice, in two systems.** Redis answers *"may this
customer start paying for this seat?"* — a hold, atomic, tokened, expiring on its own. PostgreSQL
answers *"does this seat belong to this booking?"* — a **total** `UNIQUE (showtime_id, seat_id)` on
`booking_seat`. **Redis being wrong degrades the product. Only PostgreSQL being wrong can oversell, and
PostgreSQL's half is the one that may not be waived** (`FR-ADR-024`, `SRC-002 §8.1.5`).

## Why the database guard is the one that cannot be waived

Each of these makes Redis hand out two holds on one seat, and none of them is a bug in our code:

1. The Redis node restarts and comes back empty — a customer who was paying keeps paying while a
   second customer acquires the same seat.
   - [AWS-03-01] A single ElastiCache node with no replica and no persistence loses every key on restart, which is the case this item describes. *(reasoned, not observed)*
2. A key expires at 180 s while the first customer's confirm is between step 2 (re-validate) and step
   7 (insert) of the transaction below — the re-validation passed, then the lock vanished.
3. Memory pressure evicts a key under an eviction policy someone set by mistake.
4. A bug in a release path deletes a key it did not own.

In every case the second customer's confirm reaches step 7 and the unique constraint refuses one of
the two inserts. **Without the constraint, each of those four is a seat sold twice.** That is why the
constraint is created in the Phase 2 migration, before any booking code exists, and why it has no
partial predicate (`FR-ADR-024`). **`SELECT ... FOR UPDATE` is not the guard**: it cannot lock a
`booking_seat` row that does not exist yet (`GOTCHAS.md`).

## Redis keys

| Key | Type | Value | TTL | Written by | Read by |
|---|---|---|---|---|---|
| `lock:seat:{showtime_id}:{seat_id}` | string | the hold token | `SEAT_HOLD_TTL_SECONDS` × 1000 ms, set **in the same `SET`** | hold | hold (nil disambiguation), confirm step 2, seat map |
| `hold:{hold_token}` `[JUDGMENT CALL]` name | hash | `user_id`, `showtime_id`, `expires_at`, seat list with per-seat `price_paise` | the hold's remaining TTL | hold (append only) | confirm (prices), `EP-HLD-02` |
| `holds:user:{user_id}:showtime:{showtime_id}` | set | hold token(s) | same | hold | the 10-seat cap, token reuse (`P-HLD-01` step 4) |
| `instance:{instance_id}:holds` | set | lock keys granted by this api process | same | hold | SIGTERM release (`FR-ADR-033`) |
| `cache:seatmap:{showtime_id}` | string | rendered seat map | `SEATMAP_CACHE_TTL_SECONDS` (10) | seat-map read | seat-map read; `DEL` after hold/release/commit |
| `cache:seatmap:{showtime_id}:rebuild` | string | rebuilder id | `CACHE_REBUILD_LOCK_TTL_MS` (2000) | seat-map read | stampede guard |
| `cache:listing:generation` | string | integer | none | admin writes | listing cache keys |
| rate-limit buckets | hash | tokens, last refill | refill horizon | limiter Lua | limiter Lua |

**`[JUDGMENT CALL]` the hold record's key name `hold:{hold_token}`.** `P-HLD-11` says "stored under the
hold token" and names no key. Reversible by renaming one constant.

**The hold token** is 32 bytes from `secrets.token_urlsafe(32)` → exactly 43 URL-safe characters,
matching the bound `EP-HLD-*` and `EP-PAY-01` validate. It appears in a URL path (`/api/holds/{hold_token}`),
so **the access log records the route template, never the raw path.**

## The two Lua scripts

**Release (compare-and-delete), verbatim from `FR-ADR-025`:**

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then return redis.call("DEL", KEYS[1]) else return 0 end
```

**Never** `GET` then `DEL` from Python: A's lock expires, B acquires the seat, A's late release
deletes B's lock while B pays. A test asserts a wrong token deletes nothing.

**Rate-limit token bucket** — read, refill and decrement in one script (`FR-ADR-058`). Not shown here;
its shape is in `P-XCT-07`.

**Acquisition is not a script.** It is `SET key token NX PX ttl` per seat, one command each. **Never
`SETNX` then `EXPIRE`** — a crash between them is a seat locked forever with no error anywhere.

## Hold — the order of operations (`P-HLD-01`)

```
validate body (1..10 distinct seat ids, all in this showtime's seat set)        no Redis touched yet
check cap: |seats in holds:user:{u}:showtime:{s}| + |new| <= MAX_SEATS_PER_BOOKING
check sales cut-off against the injected clock (P-HLD-06, PROVISIONAL +15 min)
resolve token: existing live hold for (u, s) → reuse its token and expires_at; else mint both once
sort seat ids ascending                                                         deterministic order
for each seat:  SET lock:seat:{s}:{seat} <token> NX PX <ttl_ms>
    OK  → won
    nil → GET the key: equals my token → already mine (no-op, TTL NOT extended); else → lost
any lost  → compare-and-delete every seat THIS request won; 409 SEAT_UNAVAILABLE naming the lost seats
all won   → read booking_seat for these seats; any row → treat as lost (a sold seat leaves no key)
price ONLY the seats this request added; append them with prices to hold:{token}
SADD holds:user:{u}:showtime:{s} token ;  SADD instance:{id}:holds <keys>  (same TTL)
DEL cache:seatmap:{s}
return the whole hold: token, expires_at (UTC), every seat with price_paise, total_paise
```

- **Ascending order** turns two overlapping requests into one clean loser instead of a stall.
- **Partial-win release is best-effort and safe**: if the process dies before releasing, those seats
  free themselves at TTL. No cleanup job (`FR-ADR-026`).
- **The TTL is never extended** — not by re-selecting, not by polling (`FR-ADR-027`).
- **Redis unreachable at any step → `503 DEPENDENCY_UNAVAILABLE`.** No PostgreSQL substitute
  (`SRC-002 §7.9`).
- **The price is fixed at hold time** and stored in the hold record; confirm never recomputes it
  (`FR-ADR-035`, `FR-ADR-039`).

## Confirm — one PostgreSQL transaction (`P-PAY-10`, `FR-ADR-029`)

`READ COMMITTED`. The constraint holds at every isolation level; `SERIALIZABLE` would add retries for
an anomaly the constraint already prevents.

| # | Inside the transaction | If it fails |
|---|---|---|
| 1 | `INSERT idempotency_record (user_id, key, fingerprint, 'in_progress')` | unique violation → roll back → duplicate path (`P-PAY-09`): same fingerprint + completed → replay stored response; same + in progress → `409 IDEMPOTENCY_IN_FLIGHT`; different fingerprint → `422 IDEMPOTENCY_KEY_REUSED` |
| 2 | **Re-validate the hold in Redis**: `hold:{token}` exists, belongs to this user, every `lock:seat` key still holds this token | `409 HOLD_EXPIRED` / `403 HOLD_NOT_OWNED`; Redis down → `503` |
| 3 | `SELECT ... FOR UPDATE` the showtime row | serialises against an admin edit |
| 4 | read the showtime; **cut-off is not re-checked** (`FR-ADR-042`) | — |
| 5 | sum the stored per-seat prices; nothing recomputed | — |
| 6 | `payment` row `pending → authorized → captured` via `SimulatedProvider` (`PAYMENT_SIMULATED_DELAY_MS`) | `402 PAYMENT_FAILED`, everything rolls back, nothing charged |
| 7 | `INSERT booking` (reference: up to 5 draws, `P-TKT-01`) + `INSERT booking_seat` × n | **unique violation on `(showtime_id, seat_id)` → the guard working** → roll back → `409 SEAT_UNAVAILABLE` naming the seats. Not retried. Logged as an expected outcome with a counter, not an exception |
| 8 | audit row — **no-op**: a customer booking is not privileged (`FR-ADR-019`) | — |
| 9 | `INSERT receipt_dispatch (booking_id, dispatch_seq=1, 'pending')` | — |
| 10 | `INSERT outbox_message (topic='receipt.send', payload={booking_id, dispatch_seq, request_id, message_version})` | — |
| 11 | `UPDATE idempotency_record SET status='completed', booking_id, response_body` | — |
| 12 | **COMMIT** | any exception before here rolls back all of 1–11, including the payment row |

After commit, outside the transaction, in this order (`P-PAY-10` steps 13–15):

1. Compare-and-delete every seat lock; delete `hold:{token}`; remove the token from
   `holds:user:{u}:showtime:{s}` and the keys from `instance:{id}:holds`.
2. `DEL cache:seatmap:{s}`.
3. Fast-path relay: send the outbox message under `QUEUE_SEND_TIMEOUT_MS`; mark the outbox row `sent`
   on success. Success, failure or timeout — the `201` goes out after this returns.

**Why release after commit.** Before commit, a seat would be free and unbooked for a moment. Inside the
transaction does nothing — Redis does not roll back. If the release fails, keys expire within 180 s
and the database already refuses anyone else.

**Why the confirm still needs Redis when the constraint would catch a double sale anyway.** Without
step 2 a customer could confirm seats that another customer is holding and paying for, and the loser
would find out at payment. Correct, and unkind. So confirm with Redis down is `503`, not "constraint
only" (`FR-ADR-028`).

**The crash window.** Captured at step 6, process dies before commit: the transaction rolls back, the
payment row with it. The retry with the same `Idempotency-Key` runs from step 1 again. **No money is
captured without a booking and none twice** — trivially here, because the provider is simulated and
its capture lives inside the same transaction.

## Failure of each system, side by side

| Situation | Hold | Confirm | Seat map | Can a seat be sold twice? |
|---|---|---|---|---|
| Both healthy | works | works | cached ≤ 10 s stale | no |
| Redis down | `503` | `503` | served from PostgreSQL; held seats show as available | **no** — nothing can be held or confirmed |
| Redis lost a key (restart, expiry race, eviction) | a second customer can hold the seat | first to reach step 7 wins; the other gets `409 SEAT_UNAVAILABLE` | briefly wrong | **no** — the constraint |
| PostgreSQL down | `503` at the `booking_seat` read | `503` | `503` unless cached | no — nothing commits |
| Constraint missing (the red-proof drill only) | works | **two commits succeed** | wrong | **yes** — this is what the drill shows |

## SIGTERM (`FR-ADR-033`, `P-XCT-17`)

Expiry is the guarantee; release on shutdown only shortens the window. The load balancer's
deregistration delay runs before SIGTERM (`04`, AWS-04-12). On SIGTERM the api stops accepting, drains for at most
`SHUTDOWN_DRAIN_TIMEOUT_SECONDS`, reads `instance:{id}:holds`, runs compare-and-delete on each key, and
exits. A hold whose booking committed was already released at commit, so **only holds that never became
bookings are dropped**, and the token comparison means an expired-and-re-acquired seat is not freed.

The ordering that breaks silently is Zone C: the ECS stop timeout must exceed the drain timeout plus
release time (strict safe bound: deregistration delay + drain), or SIGKILL lands mid-drain and the
release never runs. Correctness survives
(keys expire); the outage window does not shrink. Stated in `04`.

## The concurrency proof (`SRC-002 §9.1`, `FR-ADR-034`, `P-HLD-13`) — never waivable

`scripts/stress_seats.py`:

- signs in 50 distinct seeded customers first (untimed warm-up), so the per-user rate limit is not
  what decides the race;
- **Stage A**: fires 50 hold requests for one seat from separate connections, released together;
  asserts its own spread is under `STRESS_CONCURRENCY_SPREAD_MS` (100) so a serialised client cannot
  pass as concurrent (`GOTCHAS.md`); asserts **exactly one `201` and forty-nine `409 SEAT_UNAVAILABLE`**;
  the winner confirms; then asserts **exactly one** `booking_seat` row for that pair, **counted in
  PostgreSQL**, not from status codes (`P-HLD-13`);
- takes a base URL, so the same script runs against local Docker and the deployed environment.

**Stage A never reaches the constraint** — every loser is refused by Redis at `SET … NX`, so dropping
the constraint leaves Stage A green. **That is why the red proof is a different run** (`P-XCT-01`
Stage B), local only:

1. Drop `uq_booking_seat__showtime_id_seat_id` (owner role, local database).
2. Customer A holds the seat. **Inject an eviction by hand**: `DEL lock:seat:{s}:{seat}` with direct
   Redis access. Customer B holds the same seat. **Two live holders.** Both confirm; both reach step 7.
3. Observe **two** committed `booking_seat` rows for one pair. One row here means the drill did not
   reach the constraint and the proof is void — a stop-the-line finding.
4. Restore the constraint (re-run the migration that creates it); repeat; observe one row and one
   `409 SEAT_UNAVAILABLE`.
5. **Verify the restore by catalogue**, not only by the green run:
   `SELECT conname FROM pg_constraint WHERE conname='uq_booking_seat__showtime_id_seat_id'` → one row.

No application test seam is needed: the eviction is injected from outside, which is also the most
honest model of the failure the constraint exists for. `GOAL_08` already watched the constraint refuse
a duplicate on PostgreSQL 16 at the schema level; the end-to-end drill needs the application and runs
in Phase 4.
