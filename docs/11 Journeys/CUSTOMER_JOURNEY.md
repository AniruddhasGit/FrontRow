# Customer journey — the registered customer, first visit to receipt in hand

```
Lane .............. CUSTOMER (GOAL_06, one of five independent lanes)
Walked ............ 2026-08-22
Walked against .... docs/03 PRD/sections/ — the section files, not the 1.9 MB assembly
Sections read ..... S1_reading_rules · S3_personas_surfaces
                    E2_seat_hold (in full) · E3_checkout_payment (in full)
                    E5_account (P-ACC-01, -02, -03, -05, -06, -09 … -15; SCR-ACC-01, -04, -05)
                    E1_browse (P-BRW-01, P-BRW-07, P-BRW-11, P-BRW-12; SCR-BRW-01, -02, -03)
                    E4_receipt_entry (P-TKT-03, -04, -05, -07, -10, -11; SCR-TKT-01) —
                        read because walks 1 and 10 end there, not because this lane owns it
                    E8_crosscutting (P-XCT-07, P-XCT-11, SCR-XCT-04) — grepped, not read end to end
Also consulted .... CONSTITUTION.md Article X (the 19 open rows), to avoid re-filing a filed question
Defects filed ..... 12, in defects_customer.tsv, ids J-CUS-01 … J-CUS-12
```

> **Three readings this lane carries and does not re-decide.** Sales close **15 minutes after** the
> advertised start (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`) — `PROVISIONAL`, and walk 5 is written
> against it with the flag repeated at the step. Four roles (`SRC-003 C-1`) — `PROVISIONAL`. One
> cinema with six screens (`C-2`) — `PROVISIONAL`.
>
> **What the customer is told when their receipt definitively fails is `OPEN`**
> (`OPEN-EMAILFAIL-01`, `P-TKT-10`). Walk 10 walks the mechanism and writes no sentence for that
> screen. Where this document says the PRD is silent, it is silent — nothing below fills a gap in.

---

## Walk 1 — first visit to receipt in hand

A visitor with no account, no session and no stored state, from `/` to an emailed receipt. This is the
walk the win condition is written against, and it is the only walk here that crosses every seam the
product has.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-BRW-01` movie listing, `/` | guest, no session, no stored state | opens the site | browser → `GET /api/movies`; cache-aside read of `cache:listing:{generation}:{fingerprint}`, 60 s TTL, falling through to Postgres on a miss | `system` | the films that are both `published_at IS NOT NULL` and inside `display_from <= T < display_until`; nothing else exists for them | `P-BRW-01` `P-BRW-12` | — |
| 2 | `SCR-BRW-01` → `SCR-BRW-02` `/movies/{movie_id}` | a listing on screen | taps a movie card | listing → movie page; `GET /api/showtimes` returns `sales_close_at` and `sales_closed` per showtime | `page` | a date strip and a showtime grid; closed showtimes are **listed, marked `Closed`, and removed from the tab order** rather than hidden | `P-BRW-07` | — |
| 3 | `SCR-BRW-02` → `SCR-SEA-01` / `SCR-BRW-03` `/showtimes/{showtime_id}` | a chosen showtime id | taps an open showtime button | movie page → seat map; `GET /api/showtimes/{id}/seatmap`, assembled from `booking_seat` rows in Postgres **and** lock keys in Redis, with `sold` winning over any lock | `system` | a painted map of three wire states (`available` / `sold` / `held`), a `price_paise` on every seat, and a 3-second poll started from `poll_interval_seconds` in the payload itself | `P-BRW-11` `P-BRW-12` `P-SEA-05` `P-SEA-02` | — |
| 4 | `SCR-SEA-01` → `SCR-ACC-01` `/register` | guest, map painted | taps two `available` seats — the total builds client-side, **no request is sent and no lock is taken** — then presses `Sign in to hold these seats` | seat map → auth screen; `fr.pending_selection` is written to `sessionStorage` **before** the auth step opens | `page` | a stored `{showtime_id, seat_ids, stored_at}` and an auth screen with two tabs. The guest was stopped **at the hold, not at the map and not at payment** | `P-SEA-01` `P-SEA-03` `P-SEA-04` `P-HLD-05` `P-ACC-13` | — |
| 5 | `SCR-ACC-01`, register tab | an unauthenticated visitor with a stored selection | submits email + password | `POST /api/auth/register` → Postgres: unique index on `lower(email)` is the guard; bcrypt runs in a thread, off the event loop | `system` | an `fr_session` `HttpOnly` cookie carrying `sub`, `role`, `pv`, `iat`, `exp`, and role `customer`. **Registration signs them in** — no second form | `P-ACC-01` `P-ACC-03` `P-ACC-05` `P-ACC-14` | — |
| 6 | `SCR-ACC-01` → `SCR-SEA-01` | a live session and a stored selection | the interface returns them | auth screen → seat map; **the map is refetched before anything is restored**, then surviving seat ids are re-selected and gone ones are named | `page` | the same two seats selected, re-checked against a fresh map. **The hold is not taken automatically**, deliberately | `P-ACC-13` `P-SEA-03` | — |
| 7 | `SCR-SEA-01` | signed-in customer, selection restored | presses `Hold these seats` | `POST /api/showtimes/{id}/holds` → Redis: `SET lock:seat:{showtime_id}:{seat_id} <token> NX PX 180000`, one command, **in ascending `seat_id` order**, all-or-nothing; then a `booking_seat` read in Postgres to catch a sold seat; then `DEL cache:seatmap:{showtime_id}` | `system` | a 43-character hold token, an absolute `expires_at` in UTC, every seat under that token with its own snapshotted `price_paise`, and a `total_paise` equal to what confirm will charge | `P-HLD-01` `P-HLD-02` `P-HLD-04` `P-HLD-05` `P-HLD-06` `P-HLD-11` `P-SEA-06` `P-XCT-07` | — |
| 8 | `SCR-SEA-01` + `SCR-SEA-02` → `SCR-PAY-01` `/showtimes/{id}/checkout` | a live hold, countdown running from a server-issued instant | presses `Continue to payment` | seat map → checkout. **This is navigation and issues no request**; the seat map unmounts and its 3-second poll stops | `page` | the checkout panel, the same countdown component repeated unchanged, and the hold token + `Idempotency-Key` in `sessionStorage` | `P-HLD-09` `P-SEA-04` | `J-CUS-08` |
| 9 | `SCR-PAY-01` | a live hold, prices in hand | reads the unconditional simulated-payment notice slab and presses `Pay ₹1,661.46` | `POST /api/bookings` → Postgres: **insert the idempotency record first, before any other work**, unique on `(user_id, idempotency_key)`; then → Redis: re-validate every seat's key carries this hold's token; then `SELECT … FOR UPDATE` the showtime row | `system` | a transaction that owns the key, or a `409` before any money moves. **No card field exists anywhere on this screen** | `P-PAY-01` `P-PAY-06` `P-PAY-08` `P-PAY-09` `P-PAY-10` | — |
| 10 | `SCR-PAY-01`, in flight | the transaction past re-validation | waits `PAYMENT_SIMULATED_DELAY_MS` (assumed 1500, bounded at boot to under a tenth of the hold) | API → the **simulated** provider, in-process, `pending → authorized → captured`; then the `booking` and `booking_seat` inserts, where the **unique constraint on `(showtime_id, seat_id)` fires if it is going to** | `system` | a captured payment row and, if the constraint is satisfied, a booking whose `total_paise` is the sum of already-rounded per-seat prices — never a rounded total | `P-PAY-02` `P-PAY-03` `P-PAY-04` `P-PAY-05` `P-PAY-07` `P-PAY-11` | — |
| 11 | (no surface) | the transaction at step 12, COMMIT | none — the server acts | after commit and outside the transaction: Redis compare-and-delete on each lock, delete the hold record, remove the token from `holds:user:{user_id}:showtime:{showtime_id}`; `DEL cache:seatmap:{showtime_id}`; relay the `outbox_message` to SQS (ElasticMQ locally) and mark **that row** `sent` | `process` | a durable booking, freed locks, an invalidated map cache, and a receipt job on the queue. `receipt_dispatch` stays `pending` — the outbox row's `sent` and the dispatch row's `sent` are two different facts | `P-PAY-10` `P-TKT-04` `P-BRW-12` | — |
| 12 | `SCR-PAY-01` → `SCR-TKT-01` `/bookings/{reference}` | a `201` in hand | the screen writes `fr.last_booking_reference` **then** navigates, carrying the confirm response in the client's navigation state | checkout → confirmation | `page` | `FR-XXXX-XXXX` in the reference block, the seats, the hall, the showtime, the film, the amount paid — and, **on this first render only**, the sentence naming the address the receipt is going to | `P-TKT-03` | — |
| 13 | (the worker) | a message on the queue | none — the customer has left the loop | queue → worker: claim `receipt_dispatch` by `UPDATE … WHERE booking_id AND dispatch_seq AND status IN (pending, failed, stale sending)`; then worker → SES | `process` | the emailed receipt carrying the booking reference — **the customer's only proof of purchase and their only way into the hall** | `P-TKT-05` | — |

**Thirteen steps, thirteen seams.** The one moment that crosses none — tapping seats and watching the
total build — is folded into step 4, because `P-SEA-03` is explicit that it sends no request, writes
no Redis key and inserts no row.

**What this walk proves and what it does not.** It reaches the win condition end to end. It does not
prove step 13 arrives: SES starts sandboxed and sends only to verified addresses, so on the deployed
environment as specified today **the ordinary outcome of step 13 is a failure**, and that is walk 10.

---

## Walk 2 — a returning customer books again

Same person, second visit. They already have an account, a live cookie and at least one past booking.
The interesting difference is not speed; it is the stored state a first visit did not have.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-BRW-01` `/` | a browser holding `fr_session`, issued at most `SESSION_TTL_SECONDS` (43200, `ASSUMED`) ago | opens the site | browser cookie → the router's authorisation dependency → Postgres: the user row is loaded **by primary key on every authenticated request** and the token's `pv` is compared to `password_version` | `system` | either a resolved caller, or `401` with `Your session has ended. Sign in to continue.` if the twelve hours elapsed or a password reset moved `pv` | `P-ACC-05` `P-ACC-06` | — |
| 2 | `SCR-ACC-04` `/account/bookings` | signed in | opens their bookings to check a reference | `GET /api/me/bookings`; the caller is resolved by the dependency and **the query filters on that caller** — no user id is ever read from the request | `system` | two groups, `upcoming` and `past`, split at `showtime.ends_at` against the injected clock, each paged independently, money as integer paise | `P-ACC-10` `P-ACC-11` `P-ACC-12` | — |
| 3 | `SCR-SEA-01` | signed in, a showtime chosen | selects seats and presses `Hold these seats` — **no sign-in round trip, so `P-ACC-13` never fires** | API → Redis `SET NX`, as walk 1 step 7 | `system` | a hold. This is the run `SC-1`'s 120-second target is measured against; the first-time run of walk 1 is reported separately with no target | `P-HLD-01` `P-HLD-04` `P-ACC-15` | — |
| 4 | `SCR-SEA-01` → `SCR-PAY-01` | a live hold | presses `Continue to payment` | seat map → checkout. **On arrival the screen reads `fr.last_booking_reference` from `sessionStorage` and issues no request**: present and matching this route means *already confirmed* and it redirects to that reference's confirmation page | `page` | the checkout panel — **unless the previous booking in this same tab was on this same showtime**, in which case the stored value still matches and the screen redirects them to their *earlier* booking and they can never reach checkout for the hold they are holding | `P-PAY-01` | **`J-CUS-01`** |
| 5 | `SCR-PAY-01` → `SCR-TKT-01` | a live hold, prices in hand | presses `Pay …` | as walk 1 steps 9–12 | `system` | a second booking, a second reference, and `fr.last_booking_reference` overwritten | `P-PAY-09` `P-PAY-10` | — |
| 6 | `SCR-ACC-04` | two bookings on the account | reopens the list | `GET /api/me/bookings` → Postgres, ordered `starts_at ASC` for upcoming and `DESC` for past, with `created_at` and `id` as total tie-breakers so paging is stable | `system` | both bookings, and — if both are on one showtime — **twenty seats bought by one customer on a showtime whose cap row is titled "ten seats per showtime"** | `P-ACC-10` `P-ACC-11` `P-HLD-04` | **`J-CUS-10`** |

**The returning path is where stored client state becomes a hazard rather than a convenience.**
`sessionStorage` is scoped to the tab and not to the account or to the hold, and step 4 is the second
place in this product where that produces a wrong screen. The first is already written down at
`SCR-PAY-01` — customer A signs out, customer B signs in in the same tab and is redirected to A's
confirmation URL — and the fix for it (clear every `fr.*` key on sign-out) does not reach this one,
because the same customer signing in twice on one showtime never signs out.

---

## Walk 3 — a seat is taken by someone else while they were choosing

The customer has chosen `C12` locally. Nothing on the server knows that. Another customer holds it.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` | `C12` chosen locally, no lock held by anyone | none — another session acts | another customer's `POST /holds` → Redis `SET lock:seat:{st}:{C12} NX` returns OK, then that request runs `DEL cache:seatmap:{st}` | `system` | nothing yet. **Scarcity is consumed at the hold and nowhere earlier**, so this customer's selection was never protected | `P-SEA-03` `P-SEA-06` | — |
| 2 | `SCR-SEA-01` | the same, up to about 13 s later | none — the poll fires | seat map poll → `GET /seatmap`; assembled with `sold` winning over any lock; worst-case staleness is the 10 s cache TTL plus the 3 s poll | `system` | `C12` repaints `held_by_other` with the changed-seat outline, is dropped from the selection, and the banner reads `C12 is no longer available. It has been removed from your choices.` — **`P-SEA-03` owns that sentence; the return-from-sign-in case is a different sentence owned by `P-ACC-13`** | `P-BRW-11` `P-BRW-12` `P-SEA-02` `P-SEA-03` `P-SEA-05` | — |
| 3 | `SCR-SEA-01` | the same, but they press `Hold these seats` inside the poll window, before the map has caught up | presses the primary action | API → Redis: `SET NX` returns nil for `C12`; the server issues one `GET` to tell "someone else holds it" from "this customer already holds it"; every key **this request won** is released by compare-and-delete and **only those** | `system` | `409 SEAT_UNAVAILABLE` with `details.unavailable_seats = ["C12"]`, and `C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.` **Zero seats are held afterwards** | `P-HLD-01` `P-HLD-07` `P-HLD-14` `P-SEA-06` | — |
| 4 | `SCR-SEA-01` | a banner naming one seat, the rest of the selection intact | changes `C12` for `C14` and presses again | API → Redis `SET NX` on the new set, ascending seat id | `system` | a hold on the amended set. The banner cleared itself when the selection changed — `SEAT_UNAVAILABLE` is not dismissible and does not need to be | `P-HLD-01` `P-SEA-06` | — |
| 5 | `SCR-SEA-01` | **variant:** a hold is already live and they are adding two more seats, one of which goes | presses `Hold 2 more seats` | API → Redis `SET NX` on the two new seats only; the request is all-or-nothing **over the seats it names**, not over the whole hold | `system` | `409 SEAT_UNAVAILABLE` rendering `… No seats were held. Your other choices are still selected …` — **which is false: three seats are still held, and the screen spec says so in terms** | `P-HLD-01` `P-HLD-07` `P-HLD-14` `P-HLD-02` | **`J-CUS-05`** |

**Losing the race is the system working, and every string on this walk says so without blaming the
customer.** The one place it stops being true is step 5, and it is a message about the customer's own
seats at the moment they are counting them.

---

## Walk 4 — the 3-minute hold expires while they are on the payment screen

**Required time-boundary walk.** The only authoritative clock is Redis: the server never compares
`now` against `expires_at`, it asks whether the key is there.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-PAY-01` + `SCR-SEA-02` | a live hold, countdown at `1:00` | none — the clock moves | `time`: 60 s remaining, the single warning threshold — never 60/30/10 | `time` | the bar and digits switch to `--fr-countdown-urgent` and one line is announced once: `Less than a minute left. At 0:00 your seats are released and you will need to choose them again.` | `P-HLD-09` | — |
| 2 | `SCR-PAY-01` + `SCR-SEA-02` | still reading the panel | none — the clock reaches zero | `time`: `expires_at` passes; **Redis deletes the keys at their TTL and nothing else runs** — no cleanup job exists and none is needed | `time` | the countdown stops at `0:00`; the pay action is disabled; the component states the hold has ended and **names no cause**, because a TTL, a shutdown drain and a re-acquired key reach `0:00` identically. `SCR-PAY-01` **also** says the customer is returned to the seat map with the selection re-applied — the two cannot both be observed and no delay is specified | `P-HLD-02` `P-HLD-03` `P-HLD-09` `P-SEA-06` | **`J-CUS-06`** |
| 3 | `SCR-PAY-01` | their device clock is a minute slow, so the button still looks live; they press it at the exact instant of expiry | presses `Pay …` | `API → Redis GET` at `P-PAY-10` step 2 returns nil — **before the showtime row is locked and before any payment is attempted** | `system` | `409 HOLD_EXPIRED`: `The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free.` The client's countdown was wrong and the outcome was not | `P-HLD-03` `P-HLD-14` `P-PAY-01` `P-PAY-10` | — |
| 4 | `SCR-PAY-01` | they press `Pay` one second **before** expiry and the simulated capture straddles the boundary | presses `Pay …` | `time`: the lock key expires **during** the capture, after re-validation has already passed. Redis is not read again between re-validation and commit | `time` | the transaction continues and **the money moves**. The countdown reads `Your hold has ended. We are waiting for the answer to your payment. Do not close this page.` and then the booking reference. The seats are protected by the unique constraint, not by the lock, from that instant on | `P-SEA-06` `P-PAY-07` `P-PAY-10` `P-PAY-11` | **`J-CUS-07`** |
| 5 | `SCR-PAY-01` | the same, but another customer acquired the freed key and committed first | presses `Pay …` | `API → Postgres`: the unique constraint on `(showtime_id, seat_id)` fires at step 7. It is **caught, translated, never retried and never logged as an exception** | `system` | `409 SEAT_UNAVAILABLE`: `C12 was taken by another customer before your payment finished. Your booking was not made and you have not been charged.` The whole transaction rolls back, payment row included | `P-PAY-11` `P-HLD-14` `P-SEA-06` | — |

### The four questions this walk was required to answer, answered from the documents

1. **What they see.** At `0:00` with no confirm in flight: the countdown stops, the pay action is
   disabled and reads `Hold expired`, and the component states the hold has ended **and does not name
   why and does not claim the seats are free**. `SCR-PAY-01` additionally specifies an automatic return
   to the seat map with the selection re-applied. **Those two are mutually exclusive as written and no
   ordering or delay is given — `J-CUS-06`.**
2. **What happens to the seats.** Redis deletes the lock keys at the TTL. No job runs. On the seat map
   the cells are **not** pre-emptively repainted — they change when the next poll reports them, so the
   customer watches the seats leave rather than finding them gone. Another customer can take them
   immediately.
3. **If they submit payment at the instant of expiry.** `409 HOLD_EXPIRED`, decided by the key's
   absence and never by a clock comparison, raised at step 2 of the confirm transaction — **before the
   showtime row is locked and before any payment is attempted**. Nothing is charged. At
   `expires_at - 1s` the same request returns `201`; at `expires_at` and beyond it returns `409`. Those
   three assertions are a transcribable test and they are exercised by advancing an injected clock, not
   by sleeping.
4. **Can the money move after the hold is gone.** **Yes, in exactly one reachable way, and it is
   specified rather than accidental.** If re-validation passed while the key was live and the key then
   expires during the simulated capture, the transaction does not stop: Redis is not consulted again
   before commit, and the outcome is settled by the database guard. The customer is charged, the
   booking commits, and the on-screen countdown has already told them their hold ended. The reverse —
   money moving on a hold that was already gone at re-validation — is **impossible**, because payment
   is step 6 and re-validation is step 2.

**The unresolved case is a confirm in flight at `0:00`.** `SCR-SEA-02` keeps the busy state and tells
the customer `Do not close this page.` `SCR-PAY-01`'s *Expired* state says the customer is returned to
the seat map and does not exclude the in-flight case. A screen that navigates away while telling the
customer not to leave abandons the response to a request that may commit — `J-CUS-07`.

---

## Walk 5 — the sales cut-off passes mid-checkout

> **⚠ `PROVISIONAL` (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`).** `SALES_CUTOFF_MINUTES = +15` and a
> positive value means **after** the advertised start. The rejected reading is 15 minutes **before**,
> and the two are half an hour apart. This walk is written against the specified direction and does
> not re-decide it. Reversing it changes one signed configuration value and three assertions.

Showtime starts `2026-08-14T19:30:00+05:30`. `sales_close_at = 19:45:00+05:30`.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` | selection made at 19:44:58 IST | presses `Hold these seats` | API → the cut-off is compared against the **injected clock in the cinema's zone**, read from the `cinema` row, `now < sales_close_at`; the check runs **before any lock is touched** | `system` | a hold granted at 19:44:59, `expires_at = 19:47:59`. **This is the only place the cut-off is ever checked** | `P-HLD-06` `P-BRW-07` `P-HLD-01` | — |
| 2 | `SCR-PAY-01` | a live hold, checkout open | none — the clock moves | `time`: `now >= sales_close_at` at 19:45:00. The showtime is now closed for **new** holds | `time` | **nothing changes on this screen and nothing is specified to.** `SCR-PAY-01` publishes no sales-closed state, carries no banner for it, and runs no poll that would learn about it — the seat map's 3-second poll stopped when this route mounted | `P-HLD-06` `P-BRW-07` | **`J-CUS-11`** |
| 3 | `SCR-PAY-01` | past the cut-off, hold still live | presses `Pay …` at 19:46:10 | `API → Postgres` transaction. **Step 4 reads the showtime and does not gate on the cut-off**; `SALES_CLOSED` is not in `EP-PAY-01`'s error array and cannot be raised by it | `system` | `201`, a booking, a reference. The customer buys a ticket for a film that started 16 minutes ago, which is the ruled behaviour and not a defect | `P-PAY-10` `P-PAY-01` `P-HLD-06` | — |
| 4 | `SCR-PAY-01` → `SCR-SEA-01` | **variant:** they go back to add one more seat first | presses `Back to seats` — which **does not release the hold** — then taps a further seat and presses `Hold 1 more seat` | checkout → seat map, then API → the cut-off check refuses **before any lock is touched** | `page` then `system` | `409 SALES_CLOSED`, and the banner for a customer who holds seats: `Sales for this showtime have closed. You can still pay for the seats you are holding.` The existing hold is untouched and may still be confirmed | `P-HLD-06` `P-HLD-14` `P-SEA-06` | — |
| 5 | (arithmetic, no surface) | — | — | `time`: the effective last moment a booking can complete is the cut-off plus the hold | `time` | `19:44:59 + 180 s = 19:47:59` — **nearly eighteen minutes after the advertised start.** That is the honest number and it belongs in the runbook | `P-HLD-06` | — |

**The cut-off is a property of the showtime and never of a seat**, which is why `SALES_CUTOFF_PASSES`
is a self-loop in all five states of the seat lifecycle machine: every seat becomes unselectable
without any seat changing state.

---

## Walk 6 — the simulated payment fails and they retry

The failure is deliberate, never random: it fires when the request's `Idempotency-Key` begins with
`PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-PAY-01` | a live hold, an `Idempotency-Key` carrying the failure prefix | presses `Pay …` | `API →` the simulated provider at step 6. The `payment` row is committed `failed` **in its own transaction**, so the state is observable; the booking transaction rolls back in full, **taking the idempotency record with it** | `system` | `402 PAYMENT_FAILED`. No booking, no captured payment, and a key that is free to be used again | `P-PAY-07` `P-PAY-09` `P-PAY-10` | — |
| 2 | `SCR-PAY-01` | a `402` in hand | reads the banner | API → the response must carry **one of two different sentences** depending on whether the hold survived the capture | `system` | either `… Your seats are still held - the time left is shown above. You can try again.` or `… The hold on your seats has also ended and they have been released.` — **but no step reads Redis after the capture, and the lifecycle machine states Redis is not read again between re-validation and commit**, so the server cannot know which is true | `P-PAY-01` `P-PAY-07` `P-SEA-06` | **`J-CUS-02`** |
| 3 | `SCR-PAY-01` | the hold survived; the banner invites a retry | presses `Pay …` again | `API → Postgres`: the same key inserts cleanly because the first attempt rolled it back; then `API →` the simulated provider, **which reads the same prefix on the same key** | `system` | `402` again, identically, for as long as the hold lasts. **The retry the copy invites cannot succeed** unless something mints a new key, and nothing specifies that it does | `P-PAY-07` `P-PAY-09` | **`J-CUS-04`** `J-CUS-08` |
| 4 | `SCR-PAY-01` | **variant:** the failure was Redis being unreachable, not the provider | presses `Pay …` | `API → Redis` at step 2 is unreachable; the confirm **refuses rather than relying on the database constraint alone** and never falls back to Postgres for the hold check | `system` | `503 DEPENDENCY_UNAVAILABLE`: `We cannot complete your booking right now. You have not been charged…` The lock key is untouched, keeps its original `expires_at`, and the retry works if Redis returns in time | `P-HLD-10` `P-PAY-01` `P-PAY-09` | — |

**Why step 3 matters more than it looks.** The artificial delay, the double-tap guard and the
idempotency retry path exist so that a person can exercise them by hand. With the failure trigger
bound to a key that is generated once per hold, the sequence *fail, then retry, then succeed* — the
whole point of having a deliberate failure at all — is unreachable from the product.

---

## Walk 7 — they double-click Confirm

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-PAY-01` | a live hold | presses `Pay …` | `API → Postgres`: `INSERT` the idempotency record **first, in the same transaction, before any other work**, unique on `(user_id, idempotency_key)`. **There is no check-then-act window — the index is the check and the act in one statement** | `system` | ownership of the key, `status = in_progress`, and a button that is disabled for the duration of the request — **so a genuine double-click cannot reach the server from this screen at all** | `P-PAY-09` `P-PAY-10` | — |
| 2 | `SCR-PAY-01`, second tab or a refresh | the first request still capturing | sends the same key again | `API → Postgres`: the insert violates the unique constraint; the winner is `in_progress` | `system` | `409 IDEMPOTENCY_IN_FLIGHT` with `Retry-After: ceil(1500/1000) + 1 = 3`, and `This booking is still being processed.` **The second request is never made to wait** — holding the connection would tie up one of roughly 110 | `P-PAY-09` `P-XCT-11` `P-SEA-06` | `J-CUS-03` |
| 3 | `SCR-PAY-01` | a `409` on screen, no control in the banner | none, or presses `Pay …` again | nothing specifies whether the client retries automatically after `Retry-After` or waits for the customer | `system` | an unspecified next move. Every further press spends a token from a 10-per-minute-per-user bucket, **including one that returns a replayed result** | `P-PAY-09` `P-XCT-07` | **`J-CUS-12`** |
| 4 | `SCR-PAY-01` → `SCR-TKT-01` | the winner commits | the winner's response lands | `API → Postgres`: the idempotency row is updated to `completed` with `booking_id` and `response_body` **inside the same transaction as the booking** | `system` | one booking, one capture, one reference | `P-PAY-09` `P-PAY-10` | — |
| 5 | `SCR-PAY-01` | **variant:** the same key, same fingerprint, minutes later, after the hold expired | re-sends | `API → Postgres`: the insert violates; the winner is `completed` | `system` | the stored `response_body` with the original status code, byte for byte. **The expired hold is irrelevant — the booking already exists** | `P-PAY-09` | — |
| 6 | `SCR-PAY-01` | **variant:** the same key with a different body | re-sends | `API → Postgres`: the fingerprint differs from the stored one | `system` | `422 IDEMPOTENCY_KEY_REUSED`: `This checkout is out of date. Return to the seat map and choose your seats again.` The record is **never expired and never deleted**, so this answer is permanent | `P-PAY-09` | — |

**The path the worked example demonstrates is not the path the product produces.** `P-PAY-09`'s
worked example calls step 2 the "double-click" case, but `SCR-PAY-01` disables the button for the
duration of the request, so the in-flight branch is reachable only from a second tab or a refresh —
and the refresh route is itself specified two contradictory ways (`J-CUS-03`).

---

## Walk 8 — they close the tab mid-checkout and come back

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-PAY-01` | a live hold, 90 s remaining | closes the tab | **nothing is sent.** There is no unload-time release — an unload handler is unreliable and a fire-and-forget release from a closing page can arrive after the key has expired and been re-acquired. `sessionStorage` is discarded with the tab | `time` | the lock keys survive in Redis for the remainder of the 180 s and free themselves. **The only copy of the hold token is gone** | `P-SEA-06` `P-HLD-09` `P-HLD-12` | — |
| 2 | `SCR-BRW-01` `/`, new tab | 40 s later | reopens the site | browser → the `fr_session` cookie survives the tab, because `Max-Age` is set explicitly to `SESSION_TTL_SECONDS` rather than left as a browser-session cookie | `system` | the same signed-in customer, with no hold token, no `Idempotency-Key` and no `fr.last_booking_reference` | `P-ACC-05` `P-ACC-06` | — |
| 3 | `SCR-SEA-01` | signed in, no stored state | opens the same seat map | `API → Redis`: the keys are still live and carry a token; the server emits the wire value `held`, and **the client decides `held_by_me` against `held_by_other` from its own token** — which it no longer has | `system` | **their own seats drawn as `held_by_other`, not tappable in any state.** No endpoint returns a customer's live holds; `holds:user:{user_id}:showtime:{showtime_id}` exists server-side and is exposed by nothing. They cannot select the seats, so they cannot press Hold, so `P-HLD-01` step 4's "reuse the existing token" path is unreachable for up to 180 s | `P-SEA-02` `P-SEA-05` `P-HLD-03` `P-HLD-04` | **`J-CUS-09`** |
| 4 | `SCR-SEA-01` | the same, if they try a different seat and hit the cap | presses `Hold these seats` | `API → Redis`: the cap reads the `holds:user:…` set, which still counts the seats they can no longer see or reach | `system` | `422 SEAT_LIMIT_EXCEEDED`: `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` — accurate, and unactionable from where they are standing | `P-HLD-04` `P-HLD-14` | `J-CUS-09` |
| 5 | `SCR-ACC-04` | **variant:** the tab was closed **after** the confirm was sent | opens their bookings | `process`: closing the tab abandons the **response**, not the **request**. The server completes the confirm and the booking is made without the customer ever seeing the confirmation screen | `process` | the booking in the list and — separately — on the emailed receipt. The reference never depended on that screen | `P-SEA-06` `P-ACC-10` `P-TKT-03` | — |

**The specified behaviour is correct on money and wrong on recovery.** Nothing is oversold, nothing
is charged and nothing leaks. But the product tells a customer that seats they are currently holding
were `taken by another customer`, and offers no route back to a hold they are still paying the cap
for. The whole window is bounded at 180 seconds, which is why this is filed rather than escalated.

---

## Walk 9 — they try to book an 11th seat

`MAX_SEATS_PER_BOOKING = 10`. **Every published string showing the number renders the configuration
value; a literal `10` is a defect.**

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` → API | 10 seats selected; the interface refuses the eleventh tap with the note `Up to 10 seats.` and sends nothing | **bypasses the interface** and submits 11 seat ids directly | `API →` body validation, **before any Redis key is written** | `system` | `422 SEAT_LIMIT_EXCEEDED`: `You can hold up to 10 seats for one showtime. You chose 11.` The interface limit is a convenience; **the test asserts the eleventh seat is refused by the API with the interface bypassed** | `P-SEA-03` `P-HLD-04` `P-HLD-14` `P-SEA-06` | — |
| 2 | `SCR-SEA-01` | holding 6 on this showtime | asks for 5 more | `API → Redis`: read `holds:user:{user_id}:showtime:{showtime_id}` and sum the seat counts under each token — **a lookup of at most ten known keys, never a `SCAN`** — before any lock is touched | `system` | `422 SEAT_LIMIT_EXCEEDED`: `You can hold up to 10 seats for one showtime. You are holding 6 and chose 5 more.` **The six already held are untouched and their expiry does not move** | `P-HLD-04` `P-HLD-01` `P-HLD-02` | — |
| 3 | `SCR-SEA-01` | holding 6 | asks for 4 instead | `API → Redis`: `SET NX` on the four new seats with `PX` set to **the milliseconds remaining until the existing `expires_at`**, under the **existing** token — a hold is extended, never duplicated | `system` | one hold, one token, ten seats, one unchanged expiry instant. The four new seats are priced at whatever base is current **now**, so one hold may legitimately carry two base prices | `P-HLD-01` `P-HLD-02` `P-HLD-11` | — |
| 4 | `SCR-PAY-01` → `SCR-SEA-01` | ten seats bought | pays, then immediately holds ten more on the same showtime | `API → Redis` at post-commit step 13: the token is deleted from `holds:user:…` **deliberately**, so the cap stops counting seats the customer now owns | `system` | a second hold of ten on the same showtime, and a second booking. **The cap bounds concurrent holds, not what one customer can buy on one showtime** | `P-PAY-10` `P-HLD-04` | **`J-CUS-10`** |
| 5 | `SCR-SEA-01` | holding 10 on showtime A | holds 4 on showtime B | `API → Redis`: the cap is keyed per showtime and there is no cross-showtime cap | `system` | `201`, and `4 seats held by you`. Two films in one evening is a legitimate purchase pattern and nothing rules against it | `P-HLD-04` | — |

---

## Walk 10 — SES fails after the payment is captured

> **`OPEN-EMAILFAIL-01` is a live Article X row, class reserved: product.** `P-TKT-10` decides
> nothing and **no sentence shown to a customer whose receipt definitively failed exists anywhere in
> the PRD.** This walk records the mechanism, states the customer's position, and writes no such
> sentence. Nothing below is a proposal.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | (no surface) | the confirm transaction at steps 9–10 | none — the server acts | `API → Postgres`: `receipt_dispatch` (`dispatch_seq = 1`, `status = pending`, `attempts = 0`) and the `outbox_message` are inserted **inside the booking transaction**. They commit with the booking or neither exists | `system` | a durable, committed obligation to send a receipt. **There is no state in which a dispatch row exists without its outbox message** | `P-PAY-10` `P-TKT-04` | — |
| 2 | (no surface) | committed | none | `API → queue` (SQS in AWS, ElasticMQ locally): the relay sends the message and marks **the outbox row** `sent`. The dispatch row stays `pending` — two rows with a `sent` state are two different facts | `process` | a receipt job on the queue. If the relay never ran, the worker's relay loop finds `pending` rows before each poll: **receipts are delayed, never lost** | `P-PAY-10` `P-TKT-04` `P-TKT-05` | — |
| 3 | (the worker) | a `receipt.send` message | none | `worker → Postgres` claim, then `worker → SES`. **SES returns an error** | `system` | `status = failed`, `last_error` carrying the SES error, and **the queue message is not deleted**, so it is redelivered | `P-TKT-05` | — |
| 4 | (the queue) | repeated failures | none | `queue → dead letter queue` once redelivery exceeds `maxReceiveCount` (a Zone C value) | `process` | a message sitting in a queue **nobody is watching**. DLQ depth is not alarmed; outbox pending count is not alarmed; the SES bounce and complaint rate is not alarmed. Exactly one alarm exists in this system and it is on the ECS running task count | `P-TKT-05` `P-TKT-11` | — |
| 5 | `SCR-TKT-01` `/bookings/{reference}` | the customer returns an hour later | opens their booking | confirmation page on a **later visit** — the confirm response is no longer in the client's navigation state | `page` | the reference block, the seats, the hall, the showtime, the amount paid, and **no sentence about the email in any form.** Not "sent", not "on its way", not "delayed". The failed state is **indistinguishable on screen** from the succeeded state, because the dispatch state is deliberately not on the customer API | `P-TKT-03` `P-TKT-10` | — |
| 6 | `SCR-TKT-01` | a booking whose dispatch row is `failed` | presses `Send the receipt again` | `API → Postgres`: `SELECT … FOR UPDATE` the dispatch row; `failed` is an accepting state, so `dispatch_seq` increments, `status` returns to `pending`, and a new outbox row is inserted in the same transaction | `system` | `202`, a live-region line naming the address, and the same loop again. **It is a convenience for a customer who deleted the email; it is explicitly not the answer to SES failing**, because a customer who never received anything may not know to look | `P-TKT-07` `P-TKT-05` | — |

### The customer's position at that moment, stated plainly

They have paid. The payment is captured and the booking is committed and final — **a failed send
alters no booking field**. There is no cancellation and no refund in v1, so they cannot undo it. The
emailed receipt is their only proof of purchase and their only way into the hall, and it does not
exist. **The product does not tell them so.** The page they would look at renders identically whether
the receipt was delivered an hour ago or has been sitting in a dead letter queue since, and nobody is
watching that queue. What they do have is the reference itself, on the confirmation page, in their
bookings list, and re-fetchable at `/bookings/{reference}` — none of which ever depended on the email.
Whether that reference gets them past the door when they cannot show a receipt is **exactly** the
question `OPEN-EMAILFAIL-01` reserves.

### What the documents cannot answer

Five things, and each is `OPEN` rather than merely unwritten:

1. **What the customer is told**, if anything, when the send has definitively failed.
2. **Whether the booking stays valid** when the artefact that proves it never arrived.
3. **Whether the money is theirs or the business's** at that point. There is no refund path and one
   invented here would be a money decision made by a model.
4. **Whether an address that hard-bounces is marked** and what that does to a customer's ability to
   receive a ticket. SES publishes bounces and complaints to SNS and **nothing subscribes**.
5. **Whether a second channel exists.** There is no phone number and no second address on an account.

### One consequence worth saying out loud, and it is not a defect in the PRD

**SES starts sandboxed and sends only to verified addresses.** As specified today, on the deployed
environment, a receipt to any unverified address fails, retries, and dead-letters — so this walk is
not the edge case, it is the default until the client's sandbox-exit request lands. That dependency is
already announced: `docs/30 Deployment/AWS_PREP_QUEUE.md` row 10, needed by Phase 5, marked
**request now**, status `REQUESTED`. This lane files nothing new for it; it names it because walk 10's
probability depends entirely on it. *(reasoned from the specification, not observed — nothing in this
project has run in AWS.)*

---

## Seams this lane crossed, and what each one taught

| Seam | Where it bit |
|---|---|
| seat map → checkout | `J-CUS-01` — a stored booking reference that is not cleared when a second hold is taken on the same showtime makes checkout unreachable for the second booking |
| application → Redis (the hold lock) | the only authoritative clock in the product. `SET NX PX` in one command; compare-and-delete on release; expiry needs no cleanup job. Walk 8 shows the cost of the token living only in one tab |
| application → Postgres (the unique constraint) | the truth. It is what makes walk 4 step 4 safe, walk 5 step 3 safe, and walk 7 step 1 raceless |
| application → the simulated provider | `J-CUS-02` and `J-CUS-04`. The provider is in-process and holds no external ledger, which is the whole reason the capture-before-insert window is empty in effect |
| API → worker → queue → SES | walk 10. Durable to the queue, and from there onward invisible |
| the 3-minute hold TTL | walk 4. Two clocks, one authority, and one screen that both disables a control and navigates away from it |
| the sales cut-off | walk 5. Checked once, at the hold, and never at confirm — and the checkout screen never learns it passed |

## Coverage note

`coverage_customer.txt` lists exactly the `P-XXX-nn` ids cited in the tables above, one per line,
duplicates included. Rows from `E1`, `E4` and `E8` appear only where this lane genuinely walked them;
`P-BRW` rows other than `-01`, `-07`, `-11` and `-12` were not read and are not cited, and no `P-XCT`
row beyond `-07` and `-11` was read beyond its heading.


---

> **The section below was written by a separate, independent lane** (`J-ENT`), walking the
> receipt and the door without sight of the customer walks above. It lives here rather than in
> its own file because `SRC-003` removed the cinema-staff role, so there is no staff journey to
> put it in. Its defect ids are `J-ENT-nn`.

## RECEIPT_AND_ENTRY

Everything from the instant the money is taken to the instant a person at the entrance decides whether
to let the customer in. The product's promise is kept or broken here: **the emailed receipt carrying a
unique booking reference is the customer's only proof of purchase and their only way into the hall**
(`SRC-003 OPEN-TICKET-01`, `OPEN-EMAIL-01`). There is **no QR code, no scanner, no validation endpoint
and no state anywhere that marks a reference as used** (`SRC-003 OPEN-TICKET-02`, `P-TKT-08`,
`SRC-001 §E E-3`, `§E E-9`, `SRC-002 §E E-5`). Entry is a human being reading eight characters by eye.

Five walks. Every step names the seam it crosses. Where the documents do not answer a question, the
walk says so and the question is filed in `defects_entry.tsv` — it is not answered here.

---

### RE-1 · Payment captured, to the receipt in the inbox

The send is asynchronous and durable before it is fast. The customer's screen never waits for it, and
the customer is never told an email has been sent, because at that moment it has not been.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-PAY-01` checkout | seats held, hold token live, pay pressed | the confirm transaction captures the simulated payment, inserts the booking with its reference, then the `receipt_dispatch` row (`dispatch_seq=1`, `pending`, `attempts=0`) and the `outbox_message` (`topic=receipt.send`) — steps 6, 7, 9, 10 — and commits at step 12 | `API -> Postgres: one transaction; booking + receipt_dispatch + outbox_message commit together or not at all` | `system` | a committed booking, an 8-character reference, and a receipt job that cannot be lost | `P-PAY-10` `P-TKT-01` `P-TKT-04` | — |
| 2 | (no surface — server side) | committed, response not yet emitted | the same request calls the queue's `send` on the fast path and marks the **outbox** row `sent`; the `receipt_dispatch` row stays `pending` | `API -> queue (SQS in AWS, ElasticMQ locally): SendMessage` | `system` | a message on the queue, or a `pending` outbox row if the call failed | `P-TKT-04` `P-PAY-10` | `J-ENT-04` |
| 3 | `SCR-PAY-01` -> `SCR-TKT-01` | confirm returned `201` | the client navigates to `/bookings/{reference}` carrying the confirm response in navigation state, which is the **only** test for the first-render state | `checkout -> booking page (SCR-PAY-01 -> SCR-TKT-01)` | `page` | the reference in the reference block, plus, once only, `A receipt is on its way to name@example.com.` | `P-TKT-03` `P-TKT-01` | — |
| 4 | (worker) | idle, long-polling | the worker receives the message, reads `topic`, branches to the `receipt.send` handler, and binds `request_id` to its logging context for the whole job | `queue -> worker: ReceiveMessage, long poll QUEUE_POLL_WAIT_SECONDS=20` | `process` | one job, correlated to the originating API request by `request_id` | `P-TKT-05` `P-XCT-12` | — |
| 5 | (worker) | job in hand | the claim: `UPDATE receipt_dispatch SET status='sending' ... WHERE booking_id=? AND dispatch_seq=? AND (pending OR failed OR stale sending)`. Zero rows means another delivery owns it and the message is deleted | `worker -> Postgres: conditional claim, pending -> sending` | `system` | exactly one sender for this booking, whatever the queue does | `P-TKT-05` | — |
| 6 | (worker) | claim held | reads the booking, its seats, screen, showtime and movie from PostgreSQL — the payload carries no customer data — and renders `SCR-TKT-02`, both parts | `worker -> Postgres: read for render` | `system` | a plain-text part and an HTML part with the same facts, no image, no attachment, no QR | `P-TKT-06` | `J-ENT-10` |
| 7 | (worker) | rendered | calls SES through the mail port; on success writes `status='sent'`, `sent_at`, `ses_message_id` and deletes the queue message. `MAIL_PROVIDER` and `SES_SENDER_ADDRESS` are required at boot with no default | `worker -> SES: SendEmail` | `system` | a message id, which is a record that **SES accepted the message** | `P-TKT-05` `P-XCT-15` | `J-ENT-05` |
| 8 | (outside the product) | SES holds the message | SES attempts delivery to the customer's mail provider, which may accept it to the inbox, file it as spam, or reject it. Bounces and complaints publish to SNS and **nothing subscribes** | `SES -> the customer's mail provider` | `system` | a receipt in an inbox, or in a spam folder, or nowhere — the product cannot tell the three apart | `P-TKT-06` `P-TKT-10` | `J-ENT-03` `J-ENT-11` |
| 9 | (worker) | step 2 failed, or the API died before it | the outbox row is still `pending`; before each poll the worker selects `pending` rows older than `OUTBOX_RELAY_MIN_AGE_SECONDS`=30 with `FOR UPDATE SKIP LOCKED` and relays them | `outbox row age crosses the 30-second relay threshold` | `time` | the receipt enqueued roughly 30–50 seconds after the crash *(reasoned from the configured values, not observed)* | `P-TKT-04` `P-XCT-18` | — |
| 10 | (worker) | a deploy lands mid-send | SIGTERM: the worker stops polling, finishes the message in hand and exits. A worker killed instead leaves the row `sending` with no sender | `SIGTERM -> worker drain; claim left sending` | `process` | either a completed send, or an abandoned claim | `P-XCT-17` `P-TKT-05` | — |
| 11 | (worker) | abandoned `sending` claim | redeliveries arrive every visibility timeout and each compares the claim's age against `RECEIPT_CLAIM_STALE_SECONDS`=900; the eighth reclaims it and sends | `claim age 960 s crosses the 900 s stale threshold` | `time` | a **late** receipt, never a duplicate one — provided `maxReceiveCount` exceeds 8 | `P-TKT-05` | `J-ENT-07` |
| 12 | (queue) | SES kept refusing | redelivery exhausts `maxReceiveCount`; the message moves to the dead letter queue and `receipt_dispatch` stays `failed` with the SES error. The one ruled alarm watches running task count only | `queue -> dead letter queue; no alarm, no screen, no email to the operator` | `system` | a customer who has paid, no receipt, and nobody informed | `P-TKT-05` `P-TKT-11` `P-XCT-14` | `J-ENT-08` |

**What the customer sees in the window before the email arrives.** On the first render of `SCR-TKT-01`
— and only then — the page shows the reference block, the booking facts (film, hall, showtime, seats,
amount paid) and one sentence, `A receipt is on its way to name@example.com.` It does **not** say an
email has been sent, because at that instant it has not been. On any later visit, including a reload
one second later, the page renders the same reference block and **no sentence about the email in any
form** — not "sent", not "on its way", not "delayed". That omission is deliberate: what a customer is
told about a receipt that may already have definitively failed is `OPEN-EMAILFAIL-01`, which is `OPEN`
and reserved to the client. There is **no state on the page that distinguishes "queued", "in flight",
"delivered" and "definitively failed"** — all four render identically, because the dispatch state is
deliberately not on the customer API (`P-TKT-09`).

**The four seams, named.** API to queue (step 2, plus the relay at step 9); queue to worker (step 4);
worker to SES (step 7); SES to the customer's mail provider (step 8). **Only the first three are
inside the product.** The product's knowledge of the receipt ends when SES returns a message id, and
that is the seam that carries the promise.

---

### RE-2 · The customer arrives at the cinema and a human checks the reference

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-TKT-02` the receipt email | in the mail client, offline-capable, no sign-in | opens the message; reads `Booking reference: FR-ABCD-EFGH`, the film, `Hall 3`, `21 Aug 2026, 7:15 pm (Asia/Kolkata)`, `Seats F7, F8, F9`, `Paid Rs 843.72` | `mail client -> the reference on a phone screen; the product renders nothing here` | `page` | eight characters in `FR-XXXX-XXXX` presentation form, plus the seats and the hall | `P-TKT-06` | `J-ENT-10` |
| 2 | `SCR-TKT-02` -> `SCR-TKT-01` | wants the booking page instead of the email | follows `<PUBLIC_BASE_URL>/bookings/FR-ABCD-EFGH`; the link carries **no token**, so an unauthenticated visit gets `401` and is sent to sign in and returned | `receipt email -> /bookings/{reference}, with a sign-in round trip` | `page` | the same facts on screen, conditional on a session and a network | `P-TKT-03` `P-TKT-09` `P-TKT-02` | — |
| 3 | `SCR-TKT-01` or the email | at the entrance | shows the screen to the person on the door, or reads the reference aloud | `the customer's screen -> the person at the door; **the product has no surface on the far side**` | `page` | the person now holds eight characters and nothing to compare them against | `P-TKT-08` | `J-ENT-01` `J-ENT-06` |
| 4 | (nothing) | the person wants to verify the reference | there is no door screen, no staff account, no scanner and no validation endpoint. The only lookup in the product, `EP-TKT-01`, is authenticated and returns **only the caller's own** booking; another account's reference returns a 404 byte-identical to an unknown one, **and there is no admin override for any role** | `door -> API: no endpoint returns a booking to anyone but its owner` | `system` | nothing. The check is whatever the venue does off-system | `P-TKT-08` `P-TKT-09` `P-TKT-02` | `J-ENT-01` |

**What the human actually does, and what the PRD specifies they see.** `P-TKT-08` happy path step 2
is, in full: *"A person compares it against the day's bookings by whatever means the venue uses."*
**That is the entire specification of the entry check.** No `SCR-` id exists for the door. No
endpoint returns a showtime's bookings to anybody: the reporting lane states as a hard property that
**no reports response contains a customer name, an email address, a booking reference or a
per-booking row**, the thirty admin endpoints contain no booking read, and `EP-TKT-01` is ownership-only
by design so that it *cannot* quietly become the door tool. The change log holds nothing either — a
customer booking is not a privileged write, so `P-PAY-10` step 8 is a no-op and no `audit_log` row is
ever written for a booking.

**So "the day's bookings" is a list that does not exist anywhere in the product.** The person on the
door can read the reference; they cannot check it. This is the most important finding in this lane and
it is filed as `J-ENT-01`. **No screen is invented here.** `P-TKT-08`'s own lane note records that the
venue's process — a printed list, a laptop, a phone — was deliberately not specified because it is a
business process; the gap is that nothing in the product can produce the input that process needs, and
that consequence is not written down anywhere.

---

### RE-3 · The same reference is presented twice

`SRC-003 OPEN-TICKET-02` accepts this: *"nothing prevents the same reference being presented twice.
That is accepted for a demonstration project and is a real hole in a live one."* The walk is what the
acceptance leaves behind.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | (the entrance) | 18:50, party A shows `FR-ABCD-EFGH` for seats `F7, F8, F9` | the person reads it and admits them. **Nothing is written. No endpoint is called. No row changes.** Nothing anywhere records that this reference has been used | `door -> the venue's process; no product read and no product write` | `system` | three people in seats `F7, F8, F9`, and a product that does not know it | `P-TKT-08` | `J-ENT-02` |
| 2 | (the entrance) | 19:05, party B shows the identical eight characters | the person has no way to tell which party is the account that paid: no used-ticket state exists, no endpoint returns the booking's owner, and the reporting surfaces return no per-booking row | `door -> API: no read exists that names a booking's owner` | `system` | two parties with equal claim to one booking | `P-TKT-08` `P-TKT-09` | `J-ENT-01` `J-ENT-02` |
| 3 | `SCR-TKT-01` on a claimant's phone | the person asks a claimant to prove it | the only discriminator the product can produce is a **signed-in session that owns the booking**: `/bookings/{reference}` renders for the owner and 404s for everyone else. It requires the claimant's password, a network and a working session, and **no document specifies this as the door procedure** | `door -> SCR-TKT-01 on the claimant's device, behind a sign-in` | `page` | possibly a discriminator; possibly nothing, if the claimant cannot sign in | `P-TKT-09` `P-TKT-03` | `J-ENT-02` |
| 4 | (afterwards) | the incident is over, one party is in and one is not | nothing is recorded. The `audit_log` vocabulary is closed and published by the administration section, and **contains no action for anything at a door**; a booking is not a privileged write, so no audit row exists for it in the first place | `door incident -> audit_log: no action string exists and no write happens` | `system` | no trace: the business cannot later answer what happened | `P-XCT-03` `P-PAY-10` | `J-ENT-02` |

**What the documents cannot answer, and is not answered here.** Which party is admitted; whether the
second is turned away, seated elsewhere, or asked to buy again; what the person on the door is
entitled to ask for; and what the customer who paid and was second in the queue is owed. `SRC-003`
accepts the *duplication*; it rules nothing about the *resolution*, and `P-TKT-08` exception 1 records
only that "**nothing happens** — no software detects it". **The policy is not invented here.** It is
filed as `J-ENT-02`.

One further consequence, stated because `P-TKT-08` exception 1's phrasing invites the wrong reading:
"two people holding the same eight characters both get in" cannot be literally true of a booking, which
is a fixed set of numbered seats. Two parties cannot occupy `F7, F8, F9`. The failure is not a doubled
admission; it is a seat dispute inside the hall with nothing to arbitrate it.

---

### RE-4 · The reference itself

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | (server, inside the confirm transaction) | a booking row is being inserted | 7 characters are drawn independently and uniformly from `23456789ACDEFHJKMNPQRTVWXY` using `secrets` and an 8th check character is appended (`SRC-004 R-5`), stored uppercase with no prefix and no separators, under a `UNIQUE` constraint. A collision retries, **bounded at five attempts**; the fifth failure is `INTERNAL_ERROR` and the booking is not made | `API -> Postgres: INSERT under UNIQUE(booking.reference), bounded retry` | `system` | one reference that belongs to that booking alone | `P-TKT-01` `P-PAY-10` | — |
| 2 | `SCR-TKT-01` / `SCR-TKT-02` / the bookings list | stored value, 8 characters | rendered as `FR-XXXX-XXXX`. **The `FR` and the hyphens are presentation only and are never stored**; the same presentation form appears on the confirmation page, in the email, and on every row of the customer's own bookings | `stored value -> presentation form on three surfaces` | `page` | a string a person can hold in short-term memory in three groups | `P-TKT-01` `P-TKT-06` `P-ACC-10` | — |
| 3 | the customer's screen | at the door, or on the telephone | a person reads the characters by eye or aloud, and another person hears or transcribes them. **No software is in this path at all** — no scanner and no confirmation; the check character (SRC-004 R-5) helps only a person who computes it, which nobody at the door does | `screen -> a person's eye or ear -> a second person` | `page` | eight characters, possibly not the eight that were sent | `P-TKT-01` `P-TKT-08` | `J-ENT-06` |
| 4 | `SCR-TKT-01` | the customer types what they read into the site | the server strips whitespace and `-`, uppercases with an **ASCII-only** uppercase, drops a leading `FR` when the input is 10 characters, then asserts exactly 8 characters all in the alphabet and matches by equality — never `LIKE`, never a case-insensitive collation, never a similarity search. **Nothing is mapped, aliased or guessed** | `browser -> API: GET /api/bookings/by-reference/{reference}` | `system` | the booking, or a 404 that is **byte-identical** for malformed, unknown, and another customer's reference | `P-TKT-02` `P-TKT-09` | — |
| 5 | (server) | repeated attempts | two token buckets in Redis guard the lookup — 20 per minute per user (`Retry-After: 3`) and 60 per minute per IP (`Retry-After: 1`, singular, and it ships) — and the limiter **fails closed**, returning `503` when Redis is unreachable | `API -> Redis: token bucket, failing closed` | `system` | a refusal that tells an attacker nothing about which guesses were real | `P-TKT-02` `P-TKT-09` | — |
| 6 | (logs) | the send and the lookup both log | `booking_id` and `request_id` are logged; **a log line may never carry the booking reference and the customer's email address together**, because the pair is enough to walk into a hall | `API / worker -> stdout: JSON log line, central redaction` | `system` | an operator who can trace a booking without holding the means to enter with it | `P-XCT-12` | — |

**Is it unique, and how is that enforced?** Yes, by a `UNIQUE` constraint on the column, inside the
same transaction as the booking — not by the arithmetic. The space is `30^8 = 656,100,000,000`. At
100,000 stored references the chance one fresh draw collides is `1.524 x 10^-7`; the expected number
of colliding pairs across the first 100,000 is `100,000^2 / (2 x 656,100,000,000) = 0.0076`, so one
collision per ~13.1 million bookings, absorbed by a retry.

**Is it guessable?** Not through the product, and completely at the door. Online, `EP-TKT-01` enforces
**ownership, with the role never consulted and no admin override**, so a correctly guessed reference
belonging to someone else returns exactly the same 404 as a malformed one — the endpoint is not an
oracle, and the two rate-limit buckets cap attempts anyway. At the door there is nothing to guess
against: `P-TKT-08` exception 2 is *"a reference is invented at the door — nothing in the product
checks it"*. The reference's unguessability is therefore doing no work at the only place it is used.

**Length and character set.** Eight characters from thirty: the digits `2-9` and the letters
`ABCDEFGHJKMNPQRSTVWXYZ`. Excluded are `0`, `1`, `I`, `L`, `O` and `U`, which is exactly the exclusion
`SRC-003 OPEN-TICKET-01` asked for (*"no `0`/`O`, no `1`/`I`/`l`"*).

**Can it be read aloud or transcribed without ambiguity? No, and the exclusion list stops short.**
What remains inside the alphabet:

- **Visually confusable on a phone screen:** `2`/`Z`, `5`/`S`, `8`/`B`, `6`/`G`.
- **Confusable when spoken:** the whole `B` `C` `D` `E` `G` `P` `T` `V` `Z` `3` set, plus `M`/`N` and
  `F`/`S`, and `5`/`9` on a bad line.
- **There is no check character and no checksum**, so a single substitution produces another
  well-formed reference rather than a detectable error — and because both members of every confusable
  pair are *in* the alphabet, the mis-read value can be a real other booking's reference.
- `P-TKT-02` refuses to correct anything, and it is right to: *"a system that guesses can admit the
  wrong person."* The consequence is that the failure surfaces as a flat 404 with no hint, and at the
  door as no failure at all.

**Does the reference have `OPEN-SEATLABEL-01`'s defect? Partly — and the answer is stated both ways.**
**No** to the collision half: `row_label` is stored unnormalised, so `C12` and `c12` are two seats a
person reads as one name; a reference cannot do that, because it is generated uppercase from a fixed
alphabet, stored uppercase, and normalised with an ASCII uppercase on the way back in, so two stored
references can never differ only in case or spacing. **Yes** to the exposure half: it is the same
surface — a string printed on the emailed receipt and read aloud at a door with no software in the
path — and it has the same deadline shape, because a reference already issued to a customer cannot be
re-cut. The mechanism differs, so it is filed separately as `J-ENT-06` rather than folded into
`OPEN-SEATLABEL-01`.

---

### RE-5 · The customer is at the door with no receipt

Three ways in: SES definitively failed after payment was captured (`OPEN-EMAILFAIL-01`, **`OPEN`**),
the mail was filed as spam, or the customer deleted it. In all three they have paid.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | the mail client | in the queue at the entrance | searches for the message. The subject is `Your FrontRow booking FR-ABCD-EFGH`, so it is findable **by the reference they do not have**; searching the sender or "FrontRow" is the only route left. A spam-filed message and a message never sent look identical from here | `mail client -> nothing` | `page` | nothing | `P-TKT-06` | `J-ENT-11` |
| 2 | the site on a phone | signed out | signs in, opens their own bookings, and follows the row to `/bookings/{reference}`. Every row carries the reference in `FR-XXXX-XXXX` form, the seats, the hall and the amount — **this route never depended on the email** | `sign-in -> bookings list -> booking page`; `browser -> API: GET /api/me/bookings` | `page` | the reference on screen, if they can sign in and have a network | `P-ACC-10` `P-TKT-03` `P-TKT-09` | `J-ENT-09` |
| 3 | the sign-in screen | password forgotten | requests a password reset. The reset request writes a `password_reset.send` row into **the same outbox**, relayed through **the same queue**, consumed by **the same worker**, and sent through **the same SES identity** that just failed to deliver the receipt. The response is deliberately uniform, so the customer cannot tell whether anything was sent | `API -> queue -> worker -> SES: password_reset.send` | `process` | nothing, when SES is the component that is failing | `P-TKT-04` `P-TKT-12` | `J-ENT-09` |
| 4 | `SCR-TKT-01` | signed in, booking on screen, receipt never arrived | presses `Send the receipt again`. What happens depends on a row state the customer cannot see: `pending` with `attempts=0` -> `202 queued:false`, *"The first receipt has not been sent yet"*; `sending` or `pending` with `attempts>0` -> `202 queued:false`, *"A receipt is already being sent"*; `sent` or `failed` -> accepted, `dispatch_seq+1`, one new outbox row; `suppressed` -> `409 RECEIPT_SUPPRESSED` | `browser -> API: POST /resend-receipt`, then `API -> queue` | `system` | a re-enqueued job, or a refusal whose reason they cannot act on | `P-TKT-07` `P-TKT-02` | `J-ENT-12` |
| 5 | `SCR-TKT-01` | pressed it twice | the per-booking interval `RECEIPT_RESEND_MIN_INTERVAL_SECONDS`=300 refuses with `429` and `Retry-After: 300 − elapsed`, rendered *"You can request another in 4 minutes."* Refusals at step 4 spend **no** token, so a customer who tried while the worker was down is not locked out | `per-booking resend interval, 300 s, counting down` | `time` | a four-minute wait, in a queue, before a show | `P-TKT-07` | — |
| 6 | `SCR-TKT-01` | the send has definitively failed | the page renders **exactly what it renders on any successful later visit**: heading, reference block, facts. No banner, no email status, no route to the truth — the dispatch state is deliberately off the customer API, and no wording exists for this case because `OPEN-EMAILFAIL-01` reserves it | `receipt_dispatch = 'failed' -> no customer surface at all` | `system` | the reference on screen — which is the only thing that was ever independent of the email | `P-TKT-10` `P-TKT-09` `P-TKT-03` | `J-ENT-12` |
| 7 | (the operator) | the same failure, from the other side | the message is in the dead letter queue. **Dead letter queue depth is not alarmed**, nor is outbox pending count, nor the SES bounce rate; `/metrics` exposes queue depth and **nothing scrapes it**. The one ruled alarm watches running task count | `dead letter queue -> nobody` | `system` | nothing happens until a person looks at `receipt_dispatch` | `P-TKT-11` `P-XCT-14` | `J-ENT-08` |

**What recovery the product actually offers, and whether it is reachable from a queue on a phone.**
`P-TKT-10` lists four routes: the reference on the confirmation page; that page again at
`/bookings/{reference}`; the reference in the bookings list; and the customer's own resend. **All four
require an authenticated session**, a network, and a device — and the route that restores a session
when the password is gone travels the same SES path that failed. `P-TKT-10` does not state that shared
precondition, which is filed as `J-ENT-09`.

What is genuinely robust is narrower and worth saying plainly: **the reference is shown on screen at
the moment of confirmation and stored in the booking row, so a customer who wrote it down, screenshotted
it, or kept the tab open has their proof of purchase whatever SES does.** The emailed receipt is the
only **offline** artefact — there is no PDF attachment (rejected deliberately), no wallet pass and no
printable — so a customer with no email, no signal and no note has nothing at the door, and
`J-ENT-01` means the venue cannot look them up either.

**The policy for the open row is not invented here.** What a customer whose receipt definitively failed
is told, and whether their booking stays valid, is `OPEN-EMAILFAIL-01`, reserved to the client. This
walk records the mechanism and the silence; it writes no sentence into either.
