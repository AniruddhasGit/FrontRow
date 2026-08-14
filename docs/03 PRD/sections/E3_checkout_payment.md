# E3 — Checkout and payment

This epic covers everything between the moment a customer has a live seat hold and the moment a
booking row is committed in PostgreSQL. It contains the checkout screen, the money arithmetic that
produces the figure on it, the single endpoint that turns a hold into a booking, and the transaction
inside that endpoint. It does not contain the hold itself, the seat lock, or the seat state machine —
those belong to lane E2 — and it does not contain the booking reference, the receipt email or the
confirmation screen, which belong to lane E4. It hands E4 a committed booking row and an outbox row.

**The one thing that will be got wrong.** `SRC-001 §5.3.1` requires payment to be taken before a
booking is confirmed, which puts the capture *before* the booking insert and leaves a window in which
a process can die with a payment captured and no booking. The temptation is to write the ordering
down and not say what the window leaves behind. This section names the window, names every step it
spans, states exactly what survives a crash at each point, and states how a retry recovers it. The
second temptation is to treat the rounding rule as a detail: it is not, because rounding the total
once instead of rounding each seat produces a figure that disagrees with the per-seat prices the
customer was already shown, and both figures are on the same screen. `SRC-001 §9.5` — payment handled
by a third-party provider — is **withdrawn** by erratum `E-10`. There is no provider, ever, at any
point in this project.

---

## S4 — Product specifications

### `P-PAY-01` · Take payment before the booking is confirmed · `RULED`
`[SRC: SRC-001 §5.3.1 · SRC-001 §E E-10 · SRC-003 OPEN-PAY-01 · SRC-003 OPEN-PAY-02 · FR-ADR-029 · FR-ADR-041]`
`[BRD: R-PAY-01]`

**Behaviour.** A booking row exists only after a payment record for it has reached the `captured`
state. There is no confirm-now-pay-later path, no reserved-unpaid booking, and no state in which a
booking exists without a captured payment. The capture is against the simulated provider described in
`P-PAY-07`; no external provider is contacted at any point.

**Who may do it.** Any authenticated account acting on its own behalf — `customer`, `manager` or
`admin`. A `guest` cannot: `FR-ADR-014` stops a guest at the hold, one step earlier, so an
unauthenticated request never reaches this specification. Enforced once, on the router, as an
authentication dependency, never inside the handler (`SRC-001 §7.4`).

**Preconditions.**

1. The request carries a valid JWT for an existing user row.
2. The request carries an `Idempotency-Key` header (`P-PAY-09`).
3. The request carries a hold token that is live in Redis, owns every seat it names, and belongs to
   the authenticated user (`FR-ADR-025`, `FR-ADR-026`).
4. The hold carries a per-seat price snapshot taken at hold acquisition (`P-PAY-05`).
5. Redis is reachable. If it is not, the confirm path fails with `DEPENDENCY_UNAVAILABLE` and never
   falls back to PostgreSQL for the hold check (`SRC-002 §7.9`, `FR-ADR-028`).

**Happy path.**

1. The customer presses the pay action on the checkout screen.
2. The server runs the transaction in `P-PAY-10`, which captures the simulated payment at step 6 and
   inserts the booking at step 7.
3. The transaction commits. The response is `201` carrying the booking, its seats, its per-seat prices
   and its total.
4. The Redis locks are released and the seat-map cache key is deleted, both after commit
   (`FR-ADR-029`, `FR-ADR-030`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No JWT, or an expired one | `401` `AUTH_REQUIRED` | "Sign in to complete this booking." |
| 2 | The hold token is unknown, or its Redis keys are gone | `409` `HOLD_EXPIRED` | **Specified once in `P-HLD-14` (lane E2), at its *at confirm* row. Not restated here.** |
| 3 | The hold token exists but was issued to a different user | `403` `HOLD_NOT_OWNED` | **Specified once in `P-HLD-14` (lane E2), at its *at confirm* row. Not restated here.** |
| 4 | The simulated capture returns `failed` | `402` `PAYMENT_FAILED` | "The payment did not go through and you have not been charged. Your seats are still held - the time left is shown above. You can try again." **when the hold survived**, and "The payment did not go through and you have not been charged. The hold on your seats has also ended and they have been released. Choose them again if they are still free." **when it did not** — the server knows which, because the confirm re-validates the hold, and one unconditional sentence would be false in the second case. **This row owns both strings.** They are **not** `P-HLD-14`'s: that row's message set carries no `PAYMENT_FAILED` entry at all, so the earlier attribution pointed at a row that does not have it. `P-PAY-01`'s own note below already says E3 keeps its own copy for the codes E2 does not publish, and this is one of them. |
| 5 | A seat was already sold — the unique constraint fires | `409` `SEAT_UNAVAILABLE` | **Specified once in `P-HLD-14` (lane E2), at its *at confirm* row. Not restated here.** |
| 6 | Redis is unreachable | `503` `DEPENDENCY_UNAVAILABLE` | **Specified once in `P-HLD-14` (lane E2), at its *at confirm* row. Not restated here.** |
| 7 | Over the rate limit | `429` `RATE_LIMITED`, with `Retry-After` | "Too many attempts. Try again in 6 seconds." — the span is computed from the emptied bucket's refill rate, never from its capacity, and is rendered by **S7.20**. The arithmetic is under **Worked example — the `Retry-After` span**, below |
| 8 | Anything unhandled | `500` `INTERNAL_ERROR`, the transaction rolls back in full | "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote `a1b2c3d4`." |

**Where the copy for the four hold-related codes lives, and why it is not here.** `SEAT_UNAVAILABLE`,
`HOLD_EXPIRED`, `HOLD_NOT_OWNED` and `DEPENDENCY_UNAVAILABLE` are published as one set by lane E2's
`P-HLD-14`, which calls itself "the complete message set" and carries a row for each of the four
marked explicitly *at confirm* — that is, for this request. **E3 defers to `P-HLD-14` for all four and
writes no wording of its own for them**, because the same sentence held in two lanes is the shape of a
drift, and these four had already drifted: E2 argued at length that its own `HOLD_EXPIRED` sentence
was untrue in two of the three cases it covers, and a second copy of that sentence here would have
shipped whatever E2 concluded. **Anyone changing the wording of these four changes it in `P-HLD-14`
and nowhere else.** E3 keeps its own copy only for the codes E2 does not publish: `PAYMENT_FAILED`,
`IDEMPOTENCY_IN_FLIGHT`, `IDEMPOTENCY_KEY_REUSED`, `REQUEST_INVALID`, and the generic
`AUTH_REQUIRED`, `RATE_LIMITED` and `INTERNAL_ERROR` lines. `SALES_CLOSED` is not an error of this
endpoint at all (`P-PAY-10` step 4).

**Every instant this endpoint returns that a customer reads as a wall-clock time carries the cinema's
UTC offset, and the client converts nothing.** `EP-PAY-01`'s `201` serialises `starts_at` and
`created_at` as `2026-08-20T14:00:00+05:30` — the offset read **from the cinema row** at serialisation
time, never a constant in the code and never `Z`. This is `P-BRW-06`'s rule, which lane E1 already
applies to every browse response, extended to the booking path; the argument is the same one it gives:
**a client converting UTC to a local time is a second implementation of `FR-ADR-018`, and it is the one
that is wrong on a device whose own clock is set to another country.** A customer in Dubai opening this
product must be shown the time the film starts *at the cinema*, and the only place that fact lives is
the cinema row (`P-ADM-26`, which rules that the cinema row wins). Hardcoding `Asia/Kolkata` in the
client is the other failing option: it is right today and silently wrong the moment `EP-ADM-29` changes
the zone.

**`expires_at` is the deliberate exception and stays UTC.** It is never rendered as a time of day —
the client subtracts it from the current instant to draw `m:ss` (`P-HLD-09`) — so it is arithmetic,
not a wall-clock fact, and an offset on it would add a conversion to a value that exists to be
subtracted. **The test is what the customer reads, not what the field holds**: an instant that reaches
a screen as a time gets the cinema's offset; an instant that reaches a screen as a duration stays UTC.

**Why the `500` sentence says "No payment was taken", and why that clause is not optional.** Two rows
in this product published a sentence for the same code on the same path: this one, and `P-TKT-01`
exception 2, which carried the fuller *"…No payment was taken."* — and `SCR-PAY-01` rendered the
shorter one, so the customer was shown **the less true of two available sentences at the worst moment
in the product.** The clause is adopted here and on `SCR-PAY-01`. It is always true on this path:
every `500` in this epic rolls the transaction back in full, and the `payment` row is inside that
transaction (`P-PAY-10` crash rows 1–11), so no capture survives a failed confirm. **A customer whose
booking just failed has exactly one question, and it is about their money** — a message that leaves
it unanswered sends them to look for a charge that does not exist. All four `500` strings this lane
publishes carry the clause, not two of them, because two would have re-created the drift this fixes.

**Server-side validation.** `hold_token`: string, **exactly 43 characters from the URL-safe base64
alphabet**, required; absent, the wrong length, or carrying a character outside that alphabet is
`400` `REQUEST_INVALID`, checked before Redis is touched. That is the bound `EP-PAY-01` publishes and
the same bound `EP-HLD-01`..`EP-HLD-04` publish for the token they issue — the endpoint block owns the
wire shape (`S1.2` rank 1), and an earlier draft of this row saying *1–128 characters* was one of three
disagreeing bounds for one field. `showtime_id`: integer, positive, required; a value that does not match the
showtime the hold was taken on is `400` `REQUEST_INVALID`, because the two disagreeing is a client
defect and not a race. **Seat identifiers are never accepted in this request.** The seats come from
the hold record and from nowhere else — accepting a seat list here would let a caller confirm seats it
never held.

**Worked example.** Hold acquired at `2026-08-14T14:00:00Z` with `SEAT_HOLD_TTL_SECONDS=180`, so
`expires_at = 2026-08-14T14:03:00Z`. A confirm request arriving at `14:02:59Z` proceeds. A confirm
request arriving at `14:03:01Z` is refused at step 2 of `P-PAY-10` with `409` `HOLD_EXPIRED`,
regardless of what the client's countdown displayed (`FR-ADR-047`). The instant is read from the
injected clock, never from the container's wall clock (`CONSTITUTION.md` Art IX.5).

**Worked example — the `Retry-After` span in exception 7.** The bucket is `S7.4`'s **booking confirm**
row: `EP-PAY-01` carries two independent buckets and both must have a token, **10 per minute per user
id** and **30 per minute per real client IP**. **Whichever of the two refused is the one the span is
computed from**, so both are derived here:

```
per user, 10 / 60 s   ->  refill 0.1667 tokens/s  ->  one token in 6 s  ->  Retry-After: 6
per IP,   30 / 60 s   ->  refill 0.5000 tokens/s  ->  one token in 2 s  ->  Retry-After: 2

6 < 120  ->  "6 seconds"                  S7.20
2 < 120  ->  "2 seconds"                  S7.20

message  ->  Too many attempts. Try again in 6 seconds.
         ->  Too many attempts. Try again in 2 seconds.
```

The per-user bucket is the narrower and is the one an ordinary customer empties, so **6 seconds is the
worked value the copy above shows**. Neither branch reaches `S7.20`'s singular: the shortest span this
endpoint can produce is 2 seconds.

**The number in the message and the number in the header are the same value, and it is computed at
the moment of refusal rather than written into the string.** An earlier draft published *"Try again in
30 seconds"*, which is the per-IP bucket's **capacity** copied into a sentence that wants a **refill
interval** — a bucket's capacity and its refill interval are different quantities and only the second
one is a duration. The rendering rule itself — the 120-second threshold and `m = ceil(seconds / 60)` above it — **is
owned by `S7.20` for the whole document and is not restated here.** Every span this lane publishes is
under 120 seconds and therefore renders as seconds.

---

### `P-PAY-02` · Keep money as integer paise on every layer of the checkout path · `RULED`
`[SRC: SRC-003 OPEN-LOCALE-01 · SRC-001 §7.6 · SRC-002 §7.1 · FR-ADR-036]`
`[BRD: R-PRC-01]`

**Behaviour.** Every money value in this epic is an exact whole number of paise held in an integer.
Currency is INR. The minor-unit ratio is **100** and it is a named configuration value,
`CURRENCY_MINOR_UNIT_RATIO`, never a literal in an expression, a fixture or a seed script. `100` and
the basis-point denominator `10000` are the only two constants on the money path and both are named.

**No float anywhere.** No `Decimal` anywhere either, except at the boundary where a value arrives as
text and is parsed, validated and converted to an integer number of paise before it goes further. The
checkout path has no such boundary today — every figure it handles originates as an integer inside the
system — so in practice this epic contains no `Decimal` at all.

**Who may do it.** Not a user action. It is a constraint on the implementation of this whole epic.

**Preconditions.** `CURRENCY_CODE` and `CURRENCY_MINOR_UNIT_RATIO` are present in the environment and
validated at startup; a missing value crashes the process at boot with a message naming the variable
(`SRC-002 §7.1`, `FR-ADR-053`).

**Happy path.**

1. A money value is computed as an integer in paise.
2. It is persisted in a `bigint` column whose name ends in `_paise`.
3. It travels through the API as an integer field whose name ends in `_paise`.
4. It becomes a formatted string only in the presentation layer, at render time, with Indian digit
   grouping (`COMPONENTS.md §0.4`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `CURRENCY_MINOR_UNIT_RATIO` missing or not a positive integer at boot | The process exits non-zero before binding a port | Nothing. There is no running application to show a message. |
| 2 | A money field arrives in a request as a decimal string or a float | `400` `REQUEST_INVALID` | "This request could not be processed. Return to the seat map and choose your seats again." |

**Server-side validation.** Every money field on every request and response in this epic: type
integer, minimum `0`, no upper bound below the `bigint` ceiling. A non-integer is rejected; it is never
coerced, because coercion is where a fractional paisa enters.

**Worked example.** ₹275.00 is `27500`. ₹1,661.46 is `166146`. A field named `price` holding `275.00`
is a defect; the field is `price_paise` and holds `27500`. **The ratio is a one-way door**
(`SRC-001 §7.6`): bookings are permanent, so reinterpreting the unit later would silently rewrite what
every past customer paid, and there is no migration that fixes it because nothing records which rows
were written under which interpretation.

---

### `P-PAY-03` · Compute a seat price by integer half-up, per seat · `RULED`
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-003 OPEN-LOCALE-01 · SRC-001 §5.2.4 · FR-ADR-037 · FR-ADR-038]`
`[BRD: R-PRC-03 · R-PRC-01]`

**Behaviour.** One function computes a seat price from two integers, and every caller in the system
uses it — the seat map, this checkout screen, the receipt, the dashboard and the seed script. Two
implementations of this formula is the failure mode, not the formula being wrong.

```
seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000
```

`base_price_paise` is `showtime.base_price_paise`, set by the admin per showtime. `uplift_basis_points`
is `seat_category.uplift_basis_points`, one basis point being 0.01%, applied **uniformly across every
hall and every show** (`SRC-003 OPEN-PRICE-01`). `10000` is the basis-point denominator and `5000` is
half of it; adding half the denominator before an integer floor division is integer half-up. Both are
named constants. Standard is not a special case in code — it is a row whose uplift is `0`, and the
same expression runs for it.

**Who may do it.** Not a user action. The admin sets the two inputs (`R-ADM-05`, lane E5); this
specification governs how they combine.

**Preconditions.** Both inputs are non-null integers. `base_price_paise` is `>= 0`.
`uplift_basis_points` is `>= 0`.

**Happy path.**

1. Read `base_price_paise` from the showtime and `uplift_basis_points` from the seat's category.
2. Apply the expression above in integer arithmetic.
3. Return an integer number of paise.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A showtime with no base price | Cannot occur. The column is `bigint NOT NULL` with no default, so the row cannot be created (`FR-ADR-037`) | Nothing. |
| 2 | A negative `uplift_basis_points` reaches the admin write | `422` `VALIDATION_FAILED` on the admin form, before any showtime uses it | Not this screen. Lane E5 carries the admin copy. |

**Server-side validation.** `base_price_paise`: integer, `>= 0`. `uplift_basis_points`: integer,
`>= 0`. The function accepts nothing else; a float argument is a type error, not a rounded result.

**Worked example — required, a named multi-seat selection across two categories.**

Showtime: `DEMO MOVIE 03`, Screen 4, `2026-08-21T19:30:00+05:30`.
`showtime.base_price_paise = 27500` (₹275.00).
Category uplifts, `ASSUMED` names (`SRC-003 OPEN-SEAT-01`): Standard `0`, Premium `1250` (12.5%),
Recliner `3333` (33.33%).

Selection: **five seats — `F7`, `F8`, `F9` Premium and `J3`, `J4` Recliner.**

Premium, each of `F7`, `F8`, `F9`:

```
(27500 * (10000 + 1250) + 5000) // 10000
= (27500 * 11250 + 5000) // 10000
= (309375000 + 5000) // 10000
= 309380000 // 10000
= 30938                                        ->  Rs 309.38
```

The exact value is `27500 * 1.1250 = 30937.5` — an exact half. Half-up takes it to `30938`. Half-even
would give `30938` here too because `30938` is the even neighbour; case 3 below is where the two rules
visibly disagree.

Recliner, each of `J3`, `J4`:

```
(27500 * (10000 + 3333) + 5000) // 10000
= (27500 * 13333 + 5000) // 10000
= (366657500 + 5000) // 10000
= 366662500 // 10000
= 36666                                        ->  Rs 366.66
```

The exact value is `27500 * 1.3333 = 36665.75`. Half-up takes it to `36666`. Floor would give `36665`.

Standard, for completeness — no rounding occurs:

```
(27500 * (10000 + 0) + 5000) // 10000 = 275005000 // 10000 = 27500   ->  Rs 275.00
```

The booking total for this selection is in `P-PAY-04`, which is where the second half of the rule
lives.

---

### `P-PAY-04` · Sum already-rounded seat prices; never round the total · `RULED`
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-001 §5.2.4 · FR-ADR-038 · FR-ADR-039]`
`[BRD: R-PRC-03]`

**Behaviour.** `booking_total_paise` is the arithmetic sum of the already-rounded per-seat prices from
`P-PAY-03`. **The total is never itself rounded, and the rounding rule is never applied to it.** It is
stored on the booking row as `total_paise` (`FR-ADR-039`).

**Who may do it.** Not a user action.

**Preconditions.** Every seat in the booking has a rounded price from `P-PAY-03`.

**Happy path.**

1. Compute each seat's price by `P-PAY-03`.
2. Add the integers.
3. Store the sum as `booking.total_paise`, and assert at write time that it equals the sum of the
   `booking_seat.price_paise` rows. That assertion is a test, not a database constraint — a constraint
   would need a trigger (`FR-ADR-039`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Some seat prices are known and some are not, on the client | Not a server case. The client shows no total at all, and the pay action stays disabled (`COMPONENTS.md §5`) | The total line is absent. Nothing else changes. |
| 2 | The stored total does not equal the sum of the seat rows | `500` `INTERNAL_ERROR`, and the transaction rolls back | "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote `a1b2c3d4`." |

**Server-side validation.** `total_paise`: integer, `> 0` for any booking with at least one seat. A
booking with zero seats cannot be created, because the hold it comes from holds at least one seat
(`FR-ADR-026`).

**Worked example — required, the same selection, and the same selection computed the wrong way.**

Continuing `P-PAY-03`: three Premium at `30938` and two Recliner at `36666`.

**The rule — round per seat, then sum:**

```
Premium   30938 * 3 = 92814
Recliner  36666 * 2 = 73332
total               = 166146 paise            ->  Rs 1,661.46
```

**The wrong way — carry the exact values and round the total once:**

```
Premium   30937.5 * 3 = 92812.5
Recliner  36665.75 * 2 = 73331.5
sum                    = 166144.0
half-up                = 166144 paise         ->  Rs 1,661.44
```

**The difference is 2 paise.** `166146 - 166144 = 2`.

The reason the rule exists is on the same screen as the answer: the checkout panel lists `F7`, `F8`,
`F9` at ₹309.38 each and `J3`, `J4` at ₹366.66 each. Those five printed figures add up to ₹1,661.46.
A total of ₹1,661.44 sitting under them is a number the customer can disprove with a calculator, and
the business has no answer for which of the two is right.

**Half-up against half-even, the case where they visibly disagree** (`FR-ADR-038`): a base of `25000`
with a Recliner uplift of `3333` gives an exact `33332.5`. Half-up gives `33333`; half-even gives
`33332`, because `33332` is the even neighbour. This project uses half-up, because it is what a person
doing the arithmetic by hand produces, and the operator is also the client.

---

### `P-PAY-05` · Fix the price at hold acquisition and snapshot it onto every booked seat · `RULED`
`[SRC: SRC-001 §5.2.4 · SRC-001 §7.6 · SRC-003 OPEN-PRICE-01 · FR-ADR-035 · FR-ADR-039]`
`[BRD: R-PRC-04]`

**Behaviour.** The price a customer pays is the price that was current when their hold was granted. At
hold acquisition the API computes the per-seat prices and stores them with the hold in Redis under the
hold token (`FR-ADR-035`). The confirm transaction **reads those stored figures and does not recompute
them**. An admin editing the showtime's base price, or a category uplift, while this customer is at
checkout cannot change what this customer is charged.

Admin price edits are never blocked. They take effect for holds acquired after them. The protection
window is exactly the hold — at most 180 seconds — and needs no separate expiry.

**What is stored alongside the output, so the figure can be audited later** (`FR-ADR-039`). On each
`booking_seat` row:

| Column | Holds |
|---|---|
| `price_paise` | the rounded per-seat price the customer paid — the output of `P-PAY-03` |
| `base_price_paise_applied` | the showtime base price that produced it |
| `uplift_basis_points_applied` | the category uplift that produced it |
| `seat_category_id` | the category at the time of booking, copied rather than joined for display |

On the `booking` row: `total_paise`, from `P-PAY-04`.

The three inputs are stored beside the output on purpose. Storing only `price_paise` makes the figure
unauditable: nobody can tell whether ₹366.66 was a 33.33% uplift on ₹275.00 or a 20% uplift on
something else. `SRC-001 §7.6` requires the system to answer for its own records.

**Nothing recomputes.** No display path, no receipt, no bookings list and no dashboard multiplies a
base price by an uplift for a booking that already exists.

**Who may do it.** Not a user action.

**Preconditions.** The hold record carries a price snapshot. A hold without one cannot be confirmed —
that is a server defect and yields `500` `INTERNAL_ERROR`, not a recomputation.

**Happy path.**

1. Read the per-seat prices from the hold record in Redis.
2. Sum them by `P-PAY-04`.
3. Write `price_paise`, `base_price_paise_applied`, `uplift_basis_points_applied` and
   `seat_category_id` onto each `booking_seat` row, and `total_paise` onto the booking.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The admin changes the base price while this hold is live | The change is accepted and this customer is unaffected. The audit row records before and after (`FR-ADR-019`) | Nothing. The checkout total does not move. |
| 2 | The hold record exists but carries no price snapshot | `500` `INTERNAL_ERROR`, transaction rolled back. **The price is never recomputed as a recovery** | "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote `a1b2c3d4`." |

**Server-side validation.** Every snapshot column: integer, `>= 0`, non-null. `seat_category_id`:
integer, positive, non-null.

**Worked example.** At `14:00:00Z` a customer holds `F7` on the showtime in `P-PAY-03`, and the hold
stores `30938`. At `14:01:10Z` an admin raises `base_price_paise` from `27500` to `30000`. At
`14:02:40Z` the customer confirms. The `booking_seat` row for `F7` is written as
`price_paise = 30938`, `base_price_paise_applied = 27500`, `uplift_basis_points_applied = 1250`. The
customer is charged ₹309.38, which is what they were shown. A hold taken at `14:01:20Z` by a different
customer stores `(30000 * 11250 + 5000) // 10000 = 33750`, which is ₹337.50, and pays that.

---

### `P-PAY-06` · Charge the sum of the seat prices and nothing else · `RULED`
`[SRC: SRC-003 OPEN-PRICE-02 · SRC-003 OPEN-PRICE-03 · FR-ADR-040]`
`[BRD: R-PRC-05]`

**Behaviour.** The amount charged equals the sum of the per-seat prices from `P-PAY-03`, with nothing
added and nothing taken away.

- **No tax.** No tax column, no tax rate, no net-and-tax split, no tax line on the checkout screen or
  the receipt, and no zero-rate placeholder. A line reading "Tax: ₹0.00" is a statement about tax that
  the client did not authorise.
- **No discounts.** No discount code field, no coupon entity, no promotional price, no student or
  concession rate, no membership pricing.
- **No fees.** No booking fee, no convenience fee, no service charge.
- **No space left for one.** The checkout panel's layout does not reserve a row for a future line item
  (`COMPONENTS.md §5`, `§8`).

**The stored total is a single figure and cannot be split later.** Nothing records what portion was
ever intended as tax, so a retrospective GST split across existing bookings would be guesswork. That
is the irreversible part of this decision and it is written here so it is a known deferral rather than
something an accountant discovers.

**Who may do it.** Not a user action.

**Preconditions.** None.

**Happy path.**

1. Sum the per-seat prices.
2. Present that figure as the total, with no other line beneath the seat lines except the total
   itself.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A request body carrying a `discount_code`, `coupon`, `fee` or `tax` field | `400` `REQUEST_INVALID`. Unknown fields are rejected, not ignored, so a field nobody specified cannot be quietly accepted | "This request could not be processed. Return to the seat map and choose your seats again." |

**Server-side validation.** The confirm request body accepts exactly two fields, `hold_token` and
`showtime_id`. Any additional property is a `400`.

**Worked example.** The five-seat selection in `P-PAY-04` totals `166146` paise. The amount captured
is `166146`. The amount stored on the booking is `166146`. There is no other figure on the screen, in
the request, in the response, or in the database for this booking.

---

### `P-PAY-07` · Run the simulated provider as a real interface, unreachable without a visible flag · `RULED`
`[SRC: SRC-003 OPEN-PAY-01 · SRC-003 OPEN-PAY-02 · SRC-001 §E E-10 · SRC-002 §7.1 · FR-ADR-041]`
`[BRD: R-PAY-03]`

**Behaviour.** Payment is simulated behind an interface that carries real states. **No gateway is
integrated at any point in this project.**

**The states are `pending -> authorized -> captured`, plus `failed`.** They exist on a `payment` row
and the transitions are enforced: a capture from `pending` is rejected, and `failed` is terminal.
There is **no `refunded` state**, because there is nothing to reverse (`P-PAY-12`).

**One `payment` row per booking attempt**, carrying the state, the amount in paise, the transition
timestamps and the `Idempotency-Key` that produced it. It is a separate row rather than columns on the
booking, because the state machine has its own history and because it is where a real provider's
reference would go if one ever existed. **`booking.payment_id` points at `payment.id`**, not the
reverse, because the payment row exists before the booking row does (`P-PAY-10` steps 6 and 7).

**The artificial delay is configuration and is bounded well below the hold.**
`PAYMENT_SIMULATED_DELAY_MS` is validated at startup to be greater than `0` and **strictly less than
one tenth of `SEAT_HOLD_TTL_SECONDS * 1000`** — under 18,000 ms at the ruled 180-second hold. A
misconfiguration crashes at boot, not at checkout. The delay exists so the busy state, the double-tap
guard and the idempotency retry path are exercised by hand.

**The bound is a tenth of the hold, not the whole hold.** `FR-ADR-041` requires the delay to sit "well
below" the hold, and a delay that merely fits inside it does not satisfy that: a value of `60000` is
inside a 180-second hold and still spends a third of the customer's remaining time inside one request,
so the customer is paying for seats that are about to expire. **The tenth is the only rule; there is no
looser one anywhere in this document**, and a value that passes one check must not fail another.

**`PAYMENT_PROVIDER` has no default.** The application crashes at startup if it is unset. The only
value it accepts is `simulated`; any other value crashes at startup with a message stating that no
other provider exists. There is no fallback to `simulated`, because a fallback is how a deployment
quietly becomes a fake shop.

**The configured provider is visible outside the interface.** It is written to the boot log once and
reported in the `/health/ready` payload, so an operator can tell which provider is configured without
clicking through checkout. The `/health/ready` payload is lane E8's; this specification states what it
must carry.

**A `failed` outcome is produced deliberately, never randomly.** The trigger is the request's
`Idempotency-Key` beginning with the value of `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`. A random failure
rate would make tests flaky and a demonstration unpredictable. The trigger is a header prefix rather
than a request-body field so that no failure-control field ever enters the public request contract.

**The failed attempt is recorded and the booking transaction rolls back.** The `payment` row for a
failed capture is written in its own committed transaction so that the failure is observable; the
booking transaction that contained the attempt rolls back in full, including its idempotency record.
The key is therefore free to be retried with the same fingerprint. `[JUDGMENT CALL]` — see the lane
notes.

**Who may do it.** Not directly a user action; it is invoked by `P-PAY-10` step 6 on behalf of the
authenticated user.

**Preconditions.** `PAYMENT_PROVIDER=simulated`, `PAYMENT_SIMULATED_DELAY_MS` set and within its
bound, `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX` set. All three validated at boot.

**Happy path.**

1. Insert a `payment` row in `pending` with the amount and the idempotency key.
2. Wait `PAYMENT_SIMULATED_DELAY_MS`.
3. Transition to `authorized`, then to `captured`, recording each timestamp.
4. Return the payment id to the confirm transaction.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | `PAYMENT_PROVIDER` unset | Process exits non-zero at boot, before binding a port | Nothing. There is no running application. |
| 2 | `PAYMENT_PROVIDER` set to anything other than `simulated` | Process exits non-zero at boot with a message stating that no other provider exists | Nothing. |
| 3 | `PAYMENT_SIMULATED_DELAY_MS` >= `SEAT_HOLD_TTL_SECONDS * 1000 / 10` — at a 180-second hold, `>= 18000` | Process exits non-zero at boot, with a message naming the variable, the configured value and the computed bound | Nothing. |
| 4 | The idempotency key starts with `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX` | The payment row is committed as `failed`; the booking transaction rolls back; `402` `PAYMENT_FAILED` | "The payment did not go through and you have not been charged. Your seats are still held - the time left is shown above. You can try again." **when the hold survived**, and "The payment did not go through and you have not been charged. The hold on your seats has also ended and they have been released. Choose them again if they are still free." **when it did not** — the server knows which, because the confirm re-validates the hold, and one unconditional sentence would be false in the second case. **Published once by `P-PAY-01` exception 4, which owns both strings. Not restated here** — and not `P-HLD-14`'s, which carries no `PAYMENT_FAILED` row. |
| 5 | A capture is attempted against a payment already in `captured` | Rejected by the state machine. The confirm path never reaches this — the idempotency record catches the retry first (`P-PAY-09`) | Nothing. The replayed response is returned instead. |

**Server-side validation.** `PAYMENT_PROVIDER`: string, must equal `simulated`.
`PAYMENT_SIMULATED_DELAY_MS`: integer, `> 0`, `< SEAT_HOLD_TTL_SECONDS * 1000 / 10`.
`PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`: string, 1–32 characters.

**Worked example.** With `SEAT_HOLD_TTL_SECONDS=180` the hold is `180 * 1000 = 180000` ms and the
startup bound is a tenth of it: `PAYMENT_SIMULATED_DELAY_MS < 18000`. `1500` boots. `17999` boots.
`18000` does not. `60000` does not — it is inside the hold and is refused anyway, which is the point of
the tenth. The configured value is `1500` (**`ASSUMED`** — `FR-ADR-041`
says "a small number of seconds" and names no figure). A confirm request arriving at `14:00:00.000Z`
therefore has its payment `captured` at approximately `14:00:01.500Z`, and the transaction commits
after that. Against a hold that expires at `14:03:00Z`, a request begun as late as `14:02:58Z`
completes inside the hold. A request begun at `14:02:59.500Z` reaches commit at about
`14:03:01.000Z` — the hold has expired by then, and this does **not** matter: the hold was validated at
step 2 while it was still live, the seats are already protected by the Redis locks until `14:03:00Z`
and by the unique constraint thereafter. `FR-ADR-042` states that a customer already holding seats may
finish checking out.

---

### `P-PAY-08` · Collect, store and display no card data, and leave no field for it · `RULED`
`[SRC: SRC-001 §7.4 · SRC-003 OPEN-PAY-01 · SRC-001 §E E-10 · FR-ADR-041]`
`[BRD: R-PAY-04]`

**Behaviour.** The product never asks for a card number, never records one, and never displays one.

**On the checkout screen there is no card number field, no CVV field, no expiry field, no
cardholder-name field, and no disabled or greyed placeholder for any of them.** The pay action is a
button and nothing else. A form that looks like a payment form is the failure this rule prevents: a
simulated payment that looks real to a customer takes their seat, takes nothing else, and they find
out at the door.

**No card-shaped data anywhere else either** — not in a log line, not in a database column, not in a
test fixture, not in a seed script, not in an example request in this document. With no provider the
system never sees a card, so the rule is trivially satisfiable. It stays stated so that nobody adds a
card-shaped fixture out of habit.

**Who may do it.** Not a user action. It is a prohibition on this epic's implementation and on its
tests.

**Preconditions.** None.

**Happy path.** The confirm request body contains `hold_token` and `showtime_id`. That is the whole of
it.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A request carrying a field named for a card instrument | `400` `REQUEST_INVALID`, and **the offending field name and value are not echoed into the log or the response** | "This request could not be processed. Return to the seat map and choose your seats again." |

**Server-side validation.** The request body schema forbids additional properties, so no card-shaped
field can be accepted even by accident. Error responses never echo a rejected field's value.

**Worked example.** Not applicable — this specification computes no number. It is stated here that it
computes none, so that a reviewer does not read the absent worked example as an omission.

---

### `P-PAY-09` · Require `Idempotency-Key`, and behave in exactly three ways on a duplicate · `RULED`
`[SRC: SRC-002 §8.3.1 · SRC-001 §5.3.2 · SRC-002 §7.9 · FR-ADR-020 · FR-ADR-052]`
`[BRD: R-PAY-02]`

**Behaviour.** The confirm endpoint requires an `Idempotency-Key` header. **A missing header is a
`400`, not a permitted omission** — an optional idempotency guard is the one the double-click path
skips.

The record is a row in PostgreSQL, **inserted first, in the same transaction as the booking, before any
other work**, with a unique constraint on `(user_id, idempotency_key)`. The insert either succeeds —
this request owns the key — or it violates the constraint, in which case this request is a duplicate.
There is no check-then-act window, because the database's unique index is the check and the act in one
statement.

The row carries `user_id`, `idempotency_key`, `request_fingerprint` (a hash of the canonicalised
request body, which for this endpoint is `hold_token` and `showtime_id`), `status`
(`in_progress` / `completed`), `booking_id`, `response_body` as `jsonb`, `created_at` and
`completed_at`.

**The three duplicate behaviours, and they are the whole set:**

| The winner's state | What the duplicate gets |
|---|---|
| `completed` | The stored `response_body` with the original status code. Never a second booking, never a second capture. |
| `in_progress` | `409` `IDEMPOTENCY_IN_FLIGHT` with a `Retry-After`. Not a block, not a wait, and not a replay of a result that does not exist yet. |
| any state, but the fingerprint differs | `422` `IDEMPOTENCY_KEY_REUSED`. The key has been reused for a different request; honouring it would return one booking's result for another booking's request. |

**The second request is never made to wait.** Holding a connection open for the duration of the first
request ties up one of roughly 110 connections on a `db.t3.micro` for as long as the first takes.

**The record is never expired and never deleted** (`SRC-003 OPEN-OPS-02`, `FR-ADR-012`). A key that
expires is a key whose retry after the window creates a second booking.

**Scope is per user.** Two customers can generate the same key — a weak client generator, or a copied
request — and a global scope would hand one of them the other's booking.

**Who may do it.** Any authenticated account, as `P-PAY-01`.

**Preconditions.** The `Idempotency-Key` header is present, 1–255 characters.

**Happy path.**

1. Compute `request_fingerprint` from the canonicalised body.
2. Insert `(user_id, idempotency_key, request_fingerprint, status='in_progress')`.
3. The insert succeeds. This request owns the key and proceeds to `P-PAY-10` step 2.
4. At step 11 the row is updated to `completed` with `booking_id` and `response_body`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | The header is absent | `400` `REQUEST_INVALID`. No transaction is opened | "This request could not be processed. Return to the seat map and choose your seats again." |
| 2 | The header is present but empty, or longer than 255 characters | `400` `REQUEST_INVALID` | "This request could not be processed. Return to the seat map and choose your seats again." |
| 3 | The key exists for this user, `status = completed`, fingerprint matches | The stored `response_body` and the original status code, byte for byte | The confirmation, exactly as the first time. No banner, no second charge, no second booking. |
| 4 | The key exists for this user, `status = in_progress`, fingerprint matches | `409` `IDEMPOTENCY_IN_FLIGHT` with `Retry-After` | "This booking is still being processed." |
| 5 | The key exists for this user, fingerprint differs | `422` `IDEMPOTENCY_KEY_REUSED` | "This checkout is out of date. Return to the seat map and choose your seats again." |
| 6 | The same key sent by a different user | Treated as a fresh key. The unique constraint is on `(user_id, idempotency_key)`, so there is no collision | Nothing unusual. |
| 7 | A retry after the attempt rolled back — a failed payment, or a lost seat | The key row was rolled back with the transaction, so the retry inserts it again and proceeds normally | Nothing unusual. |

**Server-side validation.** `Idempotency-Key`: string, 1–255 characters, required. Compared as an
exact byte sequence; it is not trimmed, lowercased or otherwise normalised, because silently
normalising two different keys into one is how two distinct requests collide.

**Worked example — `Retry-After` for `IDEMPOTENCY_IN_FLIGHT`.** No source states a value.

```
Retry-After = ceil(PAYMENT_SIMULATED_DELAY_MS / 1000) + 1
```

With `PAYMENT_SIMULATED_DELAY_MS = 1500` this is `ceil(1.5) + 1 = 2 + 1 = 3` seconds. The formula is
tied to the only bounded wait in the transaction, so raising the artificial delay raises the advice
automatically. `[JUDGMENT CALL]` — the formula is the build session's under Art III.9.

**Worked example — `R-PAY-02`'s three cases, which must all return the original booking.** A customer
confirms at `14:02:40Z` with `Idempotency-Key: 9f2c…`, and the booking commits at `14:02:41.6Z` as
`FR-7K3M-QP42`, total `166146`.

| Case | When | What the server does | What is returned |
|---|---|---|---|
| **Refresh** | `14:02:45Z`, same key, same fingerprint | Insert violates the unique constraint; the winner is `completed` | The stored `response_body`: booking `FR-7K3M-QP42`, total `166146` |
| **Double-click** | `14:02:40.4Z`, same key, same fingerprint, winner still capturing | Insert violates; the winner is `in_progress` | `409` `IDEMPOTENCY_IN_FLIGHT`, `Retry-After: 3` |
| **Slow retry** | `14:04:10Z`, after the hold expired, same key, same fingerprint | Insert violates; the winner is `completed`. **The expired hold is irrelevant — the booking already exists** | The stored `response_body`: booking `FR-7K3M-QP42`, total `166146` |

In none of the three is a second `payment` row created, a second booking inserted, or a second capture
performed.

---

### `P-PAY-10` · Run the confirm transaction in this order, and recover from a crash at every step · `RULED`
`[SRC: SRC-002 §8.1.5 · SRC-002 §8.3.1 · SRC-001 §5.3.1 · SRC-001 §5.3.2 · SRC-001 §7.5 · SRC-002 §7.3 · FR-ADR-029 · FR-ADR-030 · FR-ADR-031]`
`[BRD: R-PAY-01 · R-PAY-02]`

**Behaviour.** One PostgreSQL transaction at `READ COMMITTED`, PostgreSQL's default. The correctness
guarantee is the unique constraint on `(showtime_id, seat_id)`, which holds at every isolation level;
raising to `SERIALIZABLE` would add serialisation failures and retries to every booking to protect
against an anomaly the constraint already prevents.

**`SELECT ... FOR UPDATE` is not the guard** and is used only where it helps: locking the showtime row
so the price read and any other read of that row see one consistent version. It is never used to check
whether a seat is free — a row lock cannot protect a row that does not exist yet, which is the trap
`GOTCHAS.md` records.

**The order inside the transaction.**

| Step | What happens | Record |
|---|---|---|
| 1 | Insert the idempotency record. A unique violation means this is a duplicate: roll back and run the duplicate path in `P-PAY-09` | `FR-ADR-020` |
| 2 | Re-validate the hold in Redis — every seat's key still exists and carries this hold's token. If not, roll back with `409` `HOLD_EXPIRED` | `FR-ADR-029` |
| 3 | `SELECT ... FOR UPDATE` the showtime row | `FR-ADR-035` |
| 4 | Read the showtime. **The sales cut-off is not enforced here** — it was enforced at hold acquisition and a customer already holding seats may finish checking out | `SRC-003 OPEN-BOOK-03`, `FR-ADR-042` |
| 5 | Take the per-seat prices from the hold snapshot and sum them. **Nothing is recomputed** | `FR-ADR-039`, `P-PAY-05` |
| 6 | Insert the `payment` row and drive it `pending -> authorized -> captured` through the simulated provider. This is where `PAYMENT_SIMULATED_DELAY_MS` is spent | `FR-ADR-041`, `P-PAY-07` |
| 7 | Insert the `booking` row and its `booking_seat` rows. **The unique constraint fires here if it is going to** | `FR-ADR-024`, `P-PAY-11` |
| 8 | Insert an audit row if the action is privileged. **A customer booking is not privileged, so this step is a no-op for this path** | `FR-ADR-019` |
| 9 | **Insert the `receipt_dispatch` row for this booking**, `dispatch_seq = 1`, `status = 'pending'`, `attempts = 0`, every timestamp null. **`P-TKT-04` owns this row and this is the only place the running application creates one** | `FR-ADR-032`, `P-TKT-04` |
| 10 | Insert the `outbox_message` row carrying the receipt job, `topic = 'receipt.send'`, whose payload names the `dispatch_seq` written at step 9 | `FR-ADR-031`, `P-TKT-04` |
| 11 | Update the idempotency record to `completed` with `booking_id` and `response_body` | `FR-ADR-020` |
| 12 | **COMMIT** | |

**Steps 9 and 10 are one pair and neither is optional.** `P-TKT-04` requires both rows to commit with
the booking or neither to exist, and it owns their shape — this row states only that they are written
here, at this position, inside this transaction. **An earlier draft of this table omitted step 9
entirely**, which is the defect worth naming rather than silently repairing: an engineer building this
epic from this row alone would have written the outbox row and no dispatch row, `P-TKT-05`'s claim
`UPDATE` would have matched zero rows, and **no receipt would ever have been sent** — with nothing
failing, nothing logging an error, and the loss discoverable only from `P-TKT-07`'s resend screen
three epics away. The receipt is the customer's only proof of purchase and their only way into the
hall, so a step that silently does not happen is the worst failure shape this transaction has.

**Step 9 comes after step 7 and not before it**, because `receipt_dispatch` is keyed on `booking_id`
and the booking row does not exist until step 7. Step 10 comes after step 9 for the reason `P-TKT-04`
gives: the payload carries the `dispatch_seq` just written, so the message refers to a row that
already exists at the moment it is composed.

**After the commit, outside the transaction, in this order:**

| Step | What happens | Record |
|---|---|---|
| 13 | Release this hold's Redis locks with the Lua compare-and-delete script, **then delete the hold record and remove its token from `holds:user:{user_id}:showtime:{showtime_id}`**. The hold is consumed and the seats are sold; leaving the index entry would keep `P-HLD-04`'s cap counting seats this customer no longer holds but owns, and refuse them a further booking on the same showtime for the remainder of the 180 seconds | `FR-ADR-025`, `FR-ADR-029`, `P-HLD-04` |
| 14 | `DEL cache:seatmap:{showtime_id}` | `FR-ADR-030` |
| 15 | Send the outbox message to the queue and mark **the `outbox_message` row** `sent` | `FR-ADR-031` |

**Step 15 marks the outbox row and not the dispatch row.** The `receipt_dispatch` row stays `pending`
until the worker claims it and transitions it (`P-TKT-05`); this path never writes it again after step
9. Two rows with a `sent` state are two different facts — that the job was handed to the queue, and
that an email reached SES — and collapsing them would let a queue hand-off be read as a delivered
receipt.

**Why the payment is captured before the booking insert, and what that leaves behind.**
`SRC-001 §5.3.1` requires payment before confirmation, so the order is not free. Capturing after the
insert would produce the worse window — a confirmed booking with no payment, which is a seat given
away. **The window this ordering creates is: captured at step 6, and the process dies before step 12, the commit.**
It is named here rather than glossed over.

In this system the window is real in shape and empty in effect, and the reason is stated so nobody
generalises it. The simulated provider has **no external ledger**: the only record a capture produces
is the `payment` row, which is inside the same transaction. A crash before commit rolls that row away
with everything else, so nothing was captured anywhere. The retry with the same key finds no
idempotency record, inserts one, and runs the whole transaction again — one capture, one booking.
**If a real provider were ever introduced the window would become real money**, because the capture
would have committed at the provider with no booking row here. `FR-ADR-041` rules out a real provider
entirely, which is why this ordering is acceptable here and would not be elsewhere.

**Who may do it.** Any authenticated account, as `P-PAY-01`.

**Preconditions.** Those of `P-PAY-01`.

**Happy path.** Steps 1–15 above, in order.

**Exception paths — what a crash between each pair of steps leaves behind, and how the retry recovers.**

| # | Crash point | What is left behind | How the retry recovers |
|---|---|---|---|
| 1 | Between steps 1 and 2 | Nothing in PostgreSQL — the idempotency row is uncommitted. The Redis seat locks are still held with this hold's token | The same key inserts cleanly and the transaction runs from the top. |
| 2 | Between steps 2 and 3 | Nothing in PostgreSQL. Locks still held | As above. |
| 3 | Between steps 3 and 4 | Nothing in PostgreSQL. The `FOR UPDATE` lock is released by the rollback | As above. |
| 4 | Between steps 4 and 5 | Nothing in PostgreSQL | As above. |
| 5 | Between steps 5 and 6 | Nothing in PostgreSQL | As above. |
| 6 | **Between steps 6 and 7 — the named window** | Nothing in PostgreSQL. The `payment` row was inside the transaction and rolled back with it. **Nothing was captured anywhere, because the provider is in-process and holds no external state** | The same key inserts cleanly, a fresh `payment` row is created and captured once, and one booking commits. **No double capture and no orphan booking.** |
| 7 | Between steps 7 and 8 | Nothing in PostgreSQL. The booking rows are uncommitted | As above. |
| 8 | Between steps 8 and 9 | Nothing in PostgreSQL. **No `receipt_dispatch` row and no outbox row yet** — and no booking either, so nothing is owed a receipt | As above. |
| 9 | **Between steps 9 and 10** | Nothing in PostgreSQL. The dispatch row is uncommitted, so the pair is not half-written: **there is no state in which a `receipt_dispatch` row exists without its outbox message**, because both are uncommitted together | As above. The retry writes both rows once. |
| 10 | Between steps 10 and 11 | Nothing in PostgreSQL. Both the dispatch row and the outbox row are uncommitted, so no receipt is owed for a booking that does not exist | As above. |
| 11 | Between steps 11 and 12 | Nothing in PostgreSQL | As above. |
| 12 | **During step 12, after PostgreSQL has durably committed but before the client receives the response** | The booking, its seats, the `payment` row, **the `receipt_dispatch` row (`pending`)**, the outbox row and a `completed` idempotency record all exist. The Redis locks are still held and the seat-map cache is stale | The retry with the same key hits the `completed` record and replays the stored `response_body`. The locks expire on their own at `expires_at`; the cache entry expires within its 10-second TTL. **The receipt is not lost**: the outbox row is `pending` and the relay finds it (row 15). |
| 13 | Between steps 12 and 13 | The booking exists. The Redis locks are still held | Nothing has to recover. The locks expire within the remainder of the hold and no cleanup job exists or is needed (`SRC-002 §8.1.4`). The seats are already booked, so the database refuses anyone else. |
| 14 | Between steps 13 and 14 | The booking exists, the locks are released, the seat-map cache still shows the seats as free | The cache entry expires within 10 seconds (`FR-ADR-030`). Inside that window another customer can win the Redis lock for one of those seats and will then lose at the unique constraint with `409` `SEAT_UNAVAILABLE`. **Correctness holds; the visible symptom is one customer losing a race they appeared to have won.** |
| 15 | Between steps 14 and 15 | The booking exists; the outbox row is still `pending` and the `receipt_dispatch` row is still `pending` | The worker's relay loop finds `pending` outbox rows before each queue poll and sends them, claiming with `SELECT ... FOR UPDATE SKIP LOCKED` (`FR-ADR-031`). Receipts are delayed, never lost. |
| 16 | After the queue send, before the outbox row is marked `sent` | The message is on the queue and the outbox row still reads `pending`. The `receipt_dispatch` row is `pending` | The relay sends it again. The worker suppresses the duplicate with its claim on the `receipt_dispatch` row (`FR-ADR-032`, `P-TKT-05`, lane E4). |

**Server-side validation.** As `P-PAY-01` and `P-PAY-09`. In addition, the transaction asserts that
the number of `booking_seat` rows written equals the number of seats in the hold; a mismatch is
`500` `INTERNAL_ERROR` and a rollback, never a partial booking.

**Worked example.** `SEAT_HOLD_TTL_SECONDS=180`, `PAYMENT_SIMULATED_DELAY_MS=1500`. A hold is taken at
`14:00:00.000Z` and expires at `14:03:00.000Z`. The customer presses pay at `14:01:30.000Z`. Step 1
completes at about `14:01:30.010Z`, step 2 at `14:01:30.020Z`, step 6 spends 1500 ms and reaches
`captured` at about `14:01:31.530Z`, and the commit lands at about `14:01:31.560Z`. The locks are
released at about `14:01:31.570Z` and the cache key is deleted immediately after. Total elapsed inside
the transaction: about **1.56 seconds**, of which about 1.50 seconds is the artificial delay. That is
the figure to measure in Phase 4 and to compare against the connection pool size, because it is how
long one of roughly 110 connections is held per confirm.

---

### `P-PAY-11` · Treat a unique-constraint violation as the guard working · `RULED`
`[SRC: SRC-002 §8.1.5 · SRC-001 §5.2.6 · SRC-001 §2.2 · FR-ADR-024 · FR-ADR-029 · FR-ADR-052]`
`[BRD: R-PAY-01]`

**Behaviour.** A unique-constraint violation on `(showtime_id, seat_id)` at step 7 of `P-PAY-10` is
**not an error. It is the second half of the double-booking guarantee firing.**

- It is **caught** and translated into `409` `SEAT_UNAVAILABLE`, naming the seats that were taken in
  `details.unavailable_seats`.
- It is **never retried.** Retrying a lost race loses it again, slower.
- It is **never returned as `500`.** A `500` would both mislead the customer and pollute the error
  rate the operator watches.
- It is **never logged as an exception.** It is logged at info level as an expected outcome with a
  counter, because the rate at which it fires is the signal that tells the operator the lock layer has
  a problem.
- The transaction rolls back in full, so no `payment` row and no partial booking survives.

**`INSERT ... ON CONFLICT DO NOTHING` is forbidden on the seat-occupancy insert.** It turns the guard
into silence: the booking would commit with fewer seats than the customer paid for and no error
anywhere.

**The constraint is total, not partial.** There is no `WHERE status <> 'cancelled'` clause, because
`P-PAY-12` rules out cancellation in v1. **If cancellation is ever added, this constraint has to be
revisited first** — a cancelled booking holding a seat forever is what a total constraint would then
produce.

**The database guard may not be waived, at any confidence, for any reason.** Waiving a quality check
is reserved to the client (`CONSTITUTION.md` Art III.8), and this is the check.

**Who may do it.** Not a user action. It is a server behaviour on a lost race.

**Preconditions.** The transaction has reached step 7.

**Happy path.** No violation occurs and the insert succeeds. That is the ordinary case.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | **Exactly one** of the requested seats already has a `booking_seat` row for this showtime | `409` `SEAT_UNAVAILABLE`, `details.unavailable_seats` naming it, whole transaction rolled back | **`P-HLD-14` row 4, the *at confirm* singular. Not restated here** (`P-PAY-01`). |
| 1b | **Two or more** of the requested seats already have `booking_seat` rows for this showtime | as row 1, with `details.unavailable_seats` naming **every** one of them, in the order they appear in the hold | **`P-HLD-14` row 4b, the *at confirm* plural. Not restated here.** The server renders the plural sentence itself; this endpoint never returns a singular naming one seat while rejecting several |
| 2 | The same violation, and the client re-sends the identical request with the same key | The idempotency row was rolled back too, so this is a fresh attempt. It reaches step 7 and violates again | The same message as row 1. The customer must change the selection; the server does not loop. |
| 3 | The constraint has been dropped — the red-proof drill (`FR-ADR-034`) | Two winners appear. **This is the drill, and the constraint is restored and the restore verified** | Not a customer-facing case. It runs against a local environment. |

**Server-side validation.** None beyond `P-PAY-01`; this specification is about a database response,
not a request field.

**Worked example.** The concurrency proof: `scripts/stress_seats.py` fires **50 simultaneous hold
requests for one seat and asserts exactly one succeeds** (`SRC-002 §9.1`; `P-HLD-13` owns the gate
and this section restates it rather than redefining it). **It is the hold, not the confirm** — a
confirm-based variant could not work, because forty-nine of the fifty would hold no lock and would
fail re-validation with `HOLD_EXPIRED` rather than meeting the unique constraint. The expected result is one
`201` and **49** responses of `409`, each carrying `code = "SEAT_UNAVAILABLE"` and each naming that
one seat in `details.unavailable_seats`. Some of the 49 lose at the Redis lock and some lose at the
unique constraint; the response shape is identical either way, which is deliberate — the customer does
not need to know which layer refused them, and the operator reads the split from the counters, not
from the response.

---

### `P-PAY-12` · Give the payment path no reverse · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-CANCEL-01 · SRC-003 OPEN-CANCEL-02 · SRC-001 §E E-2 · SRC-001 §6.6 · FR-ADR-013 · FR-ADR-041]`
`[BRD: R-PAY-05]`

**Behaviour.** A captured simulated payment is never unwound. The payment state machine has
`pending`, `authorized`, `captured` and `failed`, and **no `refunded` state exists**. There is no
refund table, no refund amount column, no cancellation reason, and no cancellation-policy
configuration. Those are the parts that require a money decision, and a money decision that nobody
made is worse than a missing column.

**There is no customer-initiated cancellation.** No endpoint, no button, no flow.

**`booking.status` and `booking.cancelled_at` exist in the schema and no v1 endpoint exposes either.**
`status` is written once, at confirmation, to the confirmed value. `cancelled_at` stays null for every
row v1 ever creates. They exist because `SRC-001 §6.6` forbids designing in a way that blocks a later
ask, and adding a status column to a table that already holds real bookings is a migration on live
data with a backfill nobody can verify. Two columns that are never written cost nothing now.

**Recorded, not challenged:** a customer who cannot attend loses their money. That is the ruled
behaviour for a demonstration project and it would need revisiting before a real customer ever booked.

**No withdraw-showtime capability exists in v1** (`SRC-003 OPEN-SHOWCANCEL-01`, `FR-ADR-023`). The one
route by which a booking could still end up cancelled is an admin withdrawing a showtime that already
has bookings, and what happens to those bookings and to the money is **unruled and reserved**. Because
the capability does not exist, the case cannot arise. **Nothing further is written here** — no
withdrawal endpoint, no screen, no refund behaviour, and no sentence about what a customer would be
told.

**Who may do it.** Nobody. This specification describes the absence of a capability.

**Preconditions.** None.

**Happy path.** None. There is no path.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A request to any cancellation or refund path | No such route is registered. FastAPI returns its own `404` for an unregistered path | Nothing this document specifies. There is no interface that produces this request. |
| 2 | A request attempting to set `status` or `cancelled_at` through any v1 endpoint | Both fields are absent from every request schema, so the field is rejected as an unknown property: `400` `REQUEST_INVALID` | "This request could not be processed. Return to the seat map and choose your seats again." |

**Server-side validation.** No request schema in this epic accepts `status`, `cancelled_at`,
`refund_amount_paise` or any similarly named field.

**Worked example.** Not applicable — this specification computes no number, deliberately. **The absence
of a refund amount is the point:** any figure written here would be a money decision made by a model.

---

## S5 — UX specification

### `SCR-PAY-01` · The checkout screen
**Route.** `/showtimes/{showtime_id}/checkout` · **Who reaches it.** An authenticated `customer`,
`manager` or `admin` holding live seats on that showtime. A `guest` cannot reach it, because a guest
cannot hold (`FR-ADR-014`, `FR-ADR-046`) · **Component basis.** `COMPONENTS.md §8` and `§8.1`, with
`§5` for the booking lines, `§6` for the error banner, `§7` for the countdown, `§0.2` for focus and
`§0.4` for money

**What the user arrives with / leaves with.** They arrive with a hold token in `sessionStorage`
(`FR-ADR-047`), an absolute `expires_at`, a seat list and a per-seat price snapshot. They leave with a
committed booking and its reference, or with a live hold and an error banner, or with an expired hold
and a return to the seat map.

**This is the only screen in the product with a pay action, and the seat map agrees.** The control the
customer presses on `SCR-SEA-01` once a hold is live reads `Continue to payment` and is **navigation
to this route** — it issues no request, captures nothing and cannot fail. The control below, labelled
`Pay ₹1,661.46`, is the only control anywhere in the product that submits `EP-PAY-01`. Both screens
state this from their own side deliberately: the claim is only checkable if the screen being excluded
also carries it.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Simulated-payment notice slab | `--fr-surface-notice`, `--fr-ink-on-notice`, `--fr-text-md`, `--fr-weight-medium`, `--fr-radius-md`, `--fr-space-4` | Full width, at the top of the panel, **above the heading, before anything else is read.** Persistent, never a tooltip, never dismissible, **never smaller than `--fr-text-md`.** The same colour in both themes, so a reader who has learned the dark theme still finds it unfamiliar | Not a field. It is unconditional: `PAYMENT_PROVIDER` accepts only `simulated` and any other value crashes the process at boot, so there is no runtime branch and no fetch that could fail and hide it |
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-sheet`, `--fr-space-5` | Holds everything below the notice | — |
| Heading | `--fr-font-display`, `--fr-text-xl`, `--fr-weight-black`, `--fr-track-tight`, `--fr-ink-strong` | "Confirm your booking" | — |
| Showtime line | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink` | Movie title, hall and start time. **The instant arrives already carrying the cinema's UTC offset and the client renders its wall-clock part as given — it converts nothing and reads no browser timezone** (`P-PAY-01`, `P-BRW-06`, `FR-ADR-018`). The format is `S7.19`'s | — |
| Booking lines, one per seat | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink`; category note `--fr-text-xs`, `--fr-ink-muted` | Seat label, category name, price. Rendered from the hold's price snapshot, never recomputed on the client from a base price | The client renders the integers it was given; it performs no arithmetic except the sum in the next row |
| Perforation above the total | dashed `--fr-stroke-hair` `--fr-rule`, `--fr-space-3` clear above and below | Marks the tear between what you chose and what you owe | — |
| Total | label `--fr-text-sm` `--fr-ink-muted` uppercase `--fr-track-caps`; figure `--fr-font-mono`, `--fr-text-xl`, `--fr-weight-bold`, `--fr-ink-strong` | The sum of the already-rounded per-seat prices (`P-PAY-04`), formatted with Indian digit grouping at render time only | If any seat price is missing the total is not shown at all and the pay action is disabled — a partial total is a wrong number |
| Countdown | `COMPONENTS.md §7`: `--fr-font-mono`, `--fr-text-xl`, `--fr-countdown-fill`; `--fr-countdown-urgent` in the last 60 seconds; track `--fr-surface-inset`, `--fr-radius-pill` | **Repeated here, not only on the seat map.** `m:ss`, computed from the server's absolute `expires_at`, never from a duration counted on the client | At `0:00` the pay action is disabled. The component never reads the wall clock; the current instant is an input |
| Pay action | `--fr-surface-accent`, `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min`, `--fr-weight-bold` | Label is `Pay ₹1,661.46` — the figure, not a generic word. One `POST` per press; the button is disabled for the duration of the request | Disabled when: no live hold, countdown at zero, a request already in flight, or any seat price missing |
| Back to seats | transparent fill, `--fr-stroke-hair` `--fr-control-edge`, `--fr-accent-ink` | Returns to the seat map. **It does not release the hold** — there is no client-side release (`FR-ADR-047`) | — |
| Error banner | `COMPONENTS.md §6`: `--fr-surface-danger`, `--fr-ink-on-danger`, leading rule `--fr-danger-ink`, `--fr-control-edge` | Above the panel. Branches on the error `code`, never on the message text | One banner at a time; the newest replaces the previous |

**There is no card number field, no CVV field, no expiry field, no cardholder-name field and no
placeholder for any of them** (`P-PAY-08`). **There is no tax line, no discount field and no booking
fee, and no space is reserved for one** (`P-PAY-06`).

**How this screen tells "already confirmed" from "hold expired", which are entered from the same
client-visible fact.** In both, the hold token in `sessionStorage` no longer resolves to a live hold.
The screen decides from **one stored value and no request**:

| | |
|---|---|
| **What is stored** | `fr.last_booking_reference` in `sessionStorage`: the `booking_reference` from a `201` response, and the `showtime_id` it belongs to. Nothing else — no seat list, no total, no idempotency key |
| **When it is written** | On a successful confirm, from `EP-PAY-01`'s `201` body, **before** the navigation to the confirmation screen, so a customer who navigates back finds it already there |
| **When it is cleared** | **On sign-out**, together with every other `fr.*` value; when a hold is acquired for a **different** showtime; and when the tab closes — `sessionStorage` has exactly the right lifetime and needs no expiry of its own (`P-HLD-09`) |
| **Present, and its `showtime_id` matches this route** | **Already confirmed.** Redirect to the confirmation screen for that reference |
| **Absent, or its `showtime_id` names another showtime** | **Expired.** The hold ended without producing a booking; return to the seat map per the row above |

**The screen does not re-send the confirm to find out.** A replay of `EP-PAY-01` spends a rate-limit
token whether or not it creates anything — `P-XCT-07` exception 4 is explicit that a retry carrying an
already-seen `Idempotency-Key` still consumes one, and `EP-PAY-01`'s own `rate_limit` field says the
same — and it can answer `409 IDEMPOTENCY_IN_FLIGHT`, or the stored `201`, or `409 HOLD_EXPIRED` when
no booking was ever made. **That is three outcomes to disambiguate in order to answer a question the
client already knows the answer to**, and it spends a token from a bucket the customer may need for a
real retry.

**Sign-out clears it, and that is the clause that matters most on a shared device.** Signing out
clears **every** `fr.*` value in `sessionStorage` — the pending selection (`P-ACC-13`), the hold token
and its `Idempotency-Key` (`P-HLD-09`), and `fr.last_booking_reference`. The hold itself is released
at the same moment; lane E2 carries that as the `SIGN_OUT` input of the seat lifecycle machine.

**The consequence of omitting it is sharper than a stranded hold, and it is why this is stated rather
than assumed.** `sessionStorage` is scoped to the tab, not to the account. Customer A confirms a
booking, signs out, and hands the laptop over; customer B signs in **in the same tab** and opens
`/showtimes/{id}/checkout`. The rule above fires on a value that is still customer A's: **the screen
redirects — with no request, so nothing authenticates and nothing is checked — to customer A's
confirmation URL.** Customer B lands on a 404 for a booking that is not theirs, **with a stranger's
booking reference in their address bar.** The reference is the only proof of purchase in this product
and the only thing that gets someone through the door (`OPEN-EMAILFAIL-01`), so leaking one into
another person's history is not a cosmetic defect. **Clearing on sign-out is what makes the
no-request redirect safe**, and the two rules may not be separated: anything that makes this screen
act on a stored value without a request depends on that value belonging to whoever is signed in now.

**Why the reference and not the idempotency key.** The key identifies a *request*; the reference
identifies the *booking*. A stored key tells the screen only that a confirm was once attempted, which
is also true of an attempt that failed — so it cannot distinguish the two states, which is the whole
job. The reference exists only if a booking exists.

**States.**

| State | What renders |
|---|---|
| **Empty** | Cannot occur with a valid hold — a hold holds at least one seat. If the route is reached with no hold token in `sessionStorage`, the screen redirects to the seat map for that showtime and renders nothing of the panel. |
| **Loading** (arriving, prices not yet in hand) | Panel at full height. Seat lines render as `--fr-surface-inset` blocks. The total is absent. The pay action is present and disabled. The panel never blanks and never collapses, because a panel that changes height moves the pay action under a thumb. |
| **Ready** | Notice slab, heading, showtime line, seat lines with prices, perforation, total, countdown, pay action enabled. |
| **In flight** (payment running) | The pay action shows a busy state and is disabled. **The countdown keeps running. Nothing else on the panel moves.** The panel does not blank and the seat lines do not reflow. |
| **Success** | The screen writes `fr.last_booking_reference` to `sessionStorage` from the `201` body, then navigates to the confirmation screen for the new booking (lane E4, `FR-ADR-048`). The write happens before the navigation, so a customer who comes straight back finds it. This screen writes no confirmation copy of its own. |
| **Error** | The banner renders above the panel with the copy in the table below, and the panel stays exactly as it was so the customer can see what they were buying. The pay action re-enables unless the state below says otherwise. |
| **Partial** | Some seat prices known, some not: the seat lines that are known render, the total is absent, and the pay action is disabled. A partial total is a wrong number. |
| **Last 60 seconds** | The countdown digits and bar switch to `--fr-countdown-urgent` and the warning line appears. The change is announced once through a live region. Nothing else changes. |
| **Expired** (`0:00`) | The countdown stops at `0:00`. The pay action is disabled. The component states that the hold has expired and **does not claim the seats are free** — the server owns that. The customer is returned to the seat map with their previous selection re-applied and the map refreshed (`FR-ADR-047`). |
| **Already confirmed** (the customer navigates back to this route after succeeding) | `fr.last_booking_reference` is present in `sessionStorage` for this showtime. The screen redirects to the confirmation screen for that reference and **issues no request**. It does not re-present a pay action for a booking that already exists. |
| **Receipt state** | Nothing renders here about the receipt. The email is asynchronous and this screen makes no claim about it (`FR-ADR-048`, lane E4). |

**Copy.** Every string a customer reads on this screen.

| Where | Verbatim |
|---|---|
| Notice slab | "No real payment is taken. This is a demonstration system. Nothing is charged and no card details are collected." |
| Heading | "Confirm your booking" |
| Total label | "TOTAL" |
| Pay action | "Pay ₹1,661.46" — the current total, formatted with Indian digit grouping |
| Pay action, busy | "Confirming…" |
| Pay action, disabled because the hold expired | "Hold expired" |
| Secondary action | "Back to seats" |
| Countdown label | **Rendered from `SCR-SEA-02` (lane E2). Not restated here** — see the note below the table |
| Countdown warning line, last 60 seconds | **Rendered from `SCR-SEA-02` (lane E2). Not restated here** |
| Countdown at zero, no confirm in flight | **Rendered from `SCR-SEA-02` (lane E2). Not restated here** |
| Countdown at zero, a confirm in flight | **Rendered from `SCR-SEA-02` (lane E2). Not restated here** |
| `AUTH_REQUIRED` | "Sign in to complete this booking." |
| `HOLD_EXPIRED` | **Rendered from `P-HLD-14` (lane E2), its *at confirm* row. Not restated here** — see the note below the table |
| `HOLD_NOT_OWNED` | **Rendered from `P-HLD-14` (lane E2), its *at confirm* row. Not restated here** |
| `SEAT_UNAVAILABLE` | **Rendered from `P-HLD-14`, its *at confirm* rows 4 and 4b — the singular at one lost seat, the plural at two or more. Not restated here.** **The screen substitutes nothing**: the server renders the complete sentence with every seat already named in it (`SCR-XCT-01`), and this screen displays `message` as received. `details.unavailable_seats` is read only to mark those seats on the map behind the panel, never to compose the words |
| `PAYMENT_FAILED` | "The payment did not go through and you have not been charged. Your seats are still held - the time left is shown above. You can try again." **when the hold survived**, and "The payment did not go through and you have not been charged. The hold on your seats has also ended and they have been released. Choose them again if they are still free." **when it did not** — the server knows which, because the confirm re-validates the hold, and one unconditional sentence would be false in the second case. **Published once by `P-PAY-01` exception 4, which owns both strings. Not restated here** — and not `P-HLD-14`'s, which carries no `PAYMENT_FAILED` row. |
| `IDEMPOTENCY_IN_FLIGHT` | "This booking is still being processed." |
| `IDEMPOTENCY_KEY_REUSED` | "This checkout is out of date. Return to the seat map and choose your seats again." |
| `REQUEST_INVALID` | "This request could not be processed. Return to the seat map and choose your seats again." |
| `RATE_LIMITED` | "Too many attempts. Try again in 6 seconds." — the number comes from `Retry-After` and is rendered by **S7.20**; the screen formats nothing itself. `P-PAY-01` exception 7 owns the sentence and carries the arithmetic |
| `DEPENDENCY_UNAVAILABLE` | **Rendered from `P-HLD-14` (lane E2), its *at confirm* row. Not restated here** |
| `INTERNAL_ERROR` | "Something went wrong and your booking was not completed. No payment was taken. If you need help, quote `a1b2c3d4`." — the request id comes from the error envelope and is shown on 5xx only |

**No error banner on this screen carries a control, and `HOLD_EXPIRED` is the case worth naming.**
`SCR-XCT-01` publishes a `Choose seats again` banner action against `HOLD_EXPIRED`. **That action is
for surfaces that are neither the seat map nor this screen.** Here the return is already automatic —
the **Expired** state above returns the customer to the seat map with their previous selection
re-applied and the map refreshed (`FR-ADR-047`) — so a button offering to do the thing that is already
happening is a control with nothing to do, and a customer who presses it during the navigation
presses a control that has left the screen. `SCR-SEA-03` reaches the same answer for the seat map for
the neighbouring reason — **a customer meeting `HOLD_EXPIRED` there is already on the screen the
button would send them to.** Two screens, one surface each, the same conclusion, and the
cross-cutting registry defers to both by name. **This screen's banner is text and a request id line;
it has no action slot, and that is specified rather than merely unmentioned.**

**The countdown's four rows are deferred, and this screen publishes no countdown copy at all.**
`SCR-SEA-02` declares itself "the single source for this component's label and its states" and says in
terms that the checkout screen's countdown is a **repetition of that component, not a second one**,
and that this lane specifies no label, no state and no wording for it. This screen previously
published a shortened warning line — *"At 0:00 your seats are released and you will need to choose
them again."* against `SCR-SEA-02`'s *"Less than a minute left. At 0:00 your seats are released and
you will need to choose them again."* — which is exactly the variant `SCR-SEA-02` calls a defect in
the other document. **It is deleted rather than reconciled**, because publishing a matching copy here
would leave two strings to keep in step and the next edit would separate them again. A developer
implementing this screen reads all four countdown strings out of `SCR-SEA-02` and nowhere else.

**The four deferred error rows.** `HOLD_EXPIRED`, `HOLD_NOT_OWNED`, `SEAT_UNAVAILABLE` and
`DEPENDENCY_UNAVAILABLE` are E2's copy, published as one set in `P-HLD-14` with a row for each marked
*at confirm*. **This screen renders those strings; it does not own them and it does not carry a second
copy of them**, because two copies in two lanes drift and these four already had (`P-PAY-01`). A
developer implementing this screen reads the four strings out of `P-HLD-14` and nowhere else. Every
other row in the table above is this screen's own and is specified here.

No apology, no exclamation mark, no figure of speech, and **no sentence that blames the customer for a
race they lost** (`SRC-002 §2.2`, `FR-ADR-052`). That rule governs the strings this screen owns; the
four it renders from `P-HLD-14` are held to the same rule there, and "someone beat you to it" is
forbidden in both places.

**Accessibility.**

- **Focus order** follows visual order: notice slab (as a landmark, not a control) → heading → seat
  lines → total → countdown → pay action → back to seats. The error banner, when it arrives, is
  inserted before the panel in the DOM so it precedes the panel in focus order as well.
- **Focus ring** is `--fr-stroke-bold` solid `--fr-focus-ring` with `outline-offset: 2px`, never
  removed and never replaced by a shadow (`COMPONENTS.md §0.2`).
- **Accessible names.** The pay action's accessible name includes the amount: "Pay 1,661 rupees 46
  paise". The countdown has an accessible name of "Seats held for 2 minutes 14 seconds", updated at a
  granularity that does not flood a screen reader — the live region announces only the 60-second
  threshold and the zero state, not every tick.
- **Live regions.** The error banner is announced through an assertive live region; an error that is
  only red has not been reported (`FR-ADR-051`). The 60-second warning and the expiry are announced
  once each through a polite live region.
- **Target size.** The pay action and the back action are at least `--fr-tap-min` tall.
- **The notice slab is not a control.** It has no dismiss affordance to reach, because it cannot be
  dismissed.
- **Motion.** The banner arrives over `--fr-motion-base` with `--fr-ease-out`, and collapses under
  `prefers-reduced-motion`. No motion on this screen carries information.

---

## S6 — API endpoints

This lane owns exactly one endpoint, and that is deliberate rather than an omission. Reading a hold
belongs to lane E2, which owns the hold; the booking reference, the receipt and the confirmation
screen belong to lane E4; `/health/ready`, which must report the configured payment provider
(`P-PAY-07`), belongs to lane E8. What is left is the single write that turns a hold into a booking.

**Confirm a booking.** The customer's pay action. It takes a live hold and an idempotency key,
captures a simulated payment, inserts the booking, and returns it. It accepts no seat identifiers and
no money field: the seats and the prices come from the hold record, so a caller cannot confirm seats it
never held or a price it was never quoted.

```endpoint
{
  "id": "EP-PAY-01",
  "method": "POST",
  "path": "/api/bookings",
  "summary": "Confirm a held selection into a booking, capturing the simulated payment first",
  "auth": "authenticated",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {"Idempotency-Key": "string, 1..255, REQUIRED — a missing header is 400 REQUEST_INVALID"},
    "body": {"hold_token": "string, opaque, exactly 43 characters from the URL-safe base64 alphabet, required", "showtime_id": "integer, positive, required, must match the showtime the hold was taken on"}
  },
  "responses": {
    "201": {"description": "The booking was created. The simulated payment reached captured before the booking row was inserted.", "body": {"booking_id": "integer", "booking_reference": "string, the PRESENTATION FORM FR-XXXX-XXXX including its hyphens - the same shape EP-TKT-01 and every other endpoint returning a reference carries. It is re-formatted at serialisation from the 8 characters stored on the booking row; the 8-character stored form is never what crosses the wire (P-TKT-01)", "showtime_id": "integer", "movie_title": "string", "screen_name": "string", "starts_at": "string, ISO-8601 instant serialised WITH THE CINEMA'S UTC OFFSET taken from the cinema row, e.g. 2026-08-20T14:00:00+05:30 - never UTC, never a hardcoded offset. The client renders the wall-clock part as given and CONVERTS NOTHING (P-BRW-06, FR-ADR-018, P-ADM-26)", "seats": "array of objects: {seat_id, seat_label, seat_category_name, price_paise, base_price_paise_applied, uplift_basis_points_applied}", "total_paise": "integer, the sum of the already-rounded per-seat prices, never itself rounded", "currency_code": "string, INR", "payment_status": "string, captured", "created_at": "string, ISO-8601 instant serialised with the cinema's UTC offset, exactly as starts_at - it is shown to the customer as the time they booked, so it is a wall-clock instant and the client converts nothing"}},
    "400": {"description": "The Idempotency-Key header is missing or malformed, a required body field is missing, or the body carries a property this endpoint does not define."},
    "401": {"description": "No valid token. A guest cannot reach this endpoint."},
    "402": {"description": "The simulated provider returned failed. The transaction rolled back; the hold survives if it has not expired."},
    "403": {"description": "The hold token exists but was issued to a different user."},
    "409": {"description": "The hold has expired, one or more seats were taken by another customer, or the same idempotency key is still in flight."},
    "422": {"description": "The same idempotency key was sent with a different request fingerprint."},
    "429": {"description": "Over the token bucket. Carries Retry-After in seconds."},
    "500": {"description": "Unhandled. The transaction rolled back and the request id is returned to the customer."},
    "503": {"description": "Redis is unreachable. The confirm path never falls back to PostgreSQL for the hold check."}
  },
  "errors": ["REQUEST_INVALID", "AUTH_REQUIRED", "HOLD_EXPIRED", "HOLD_NOT_OWNED", "SEAT_UNAVAILABLE", "IDEMPOTENCY_IN_FLIGHT", "IDEMPOTENCY_KEY_REUSED", "PAYMENT_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "errors_deliberately_absent": "SALES_CLOSED is NOT in the array above and cannot be raised by this endpoint. The sales cut-off is enforced once, at hold acquisition (P-HLD-06), and never re-checked at confirm - SRC-003 OPEN-BOOK-03 rules that anyone already holding seats may finish checking out, and a client ruling outranks FR-ADR-029 step 4, which reads otherwise (see this lane's contradiction 1). A customer whose cut-off passes mid-checkout completes normally: P-PAY-10 step 4 reads the showtime and does not gate on it. The absence is therefore a decision, not an omission, and it is recorded here because four sections discuss the cut-off at confirm and a reader who finds none of them conclusive would otherwise add the code.",
  "idempotency": "Required. The record is inserted in Postgres in the same transaction, before any work, unique on (user_id, idempotency_key). A repeat with the same key and the same request fingerprint returns the winner's stored response body and status code when the winner is completed, and 409 IDEMPOTENCY_IN_FLIGHT with Retry-After while the winner is still running. A repeat with the same key and a different fingerprint is 422 IDEMPOTENCY_KEY_REUSED. A key whose transaction rolled back is free to be used again. The record is never expired and never deleted.",
  "rate_limit": "Redis token bucket, two independent buckets and both must have a token: 10 per minute per user id, 30 per minute per real client IP. The real IP is the rightmost-but-one X-Forwarded-For entry with exactly one trusted proxy. The limiter fails closed with 503 when Redis is unreachable. A retry carrying an already-seen Idempotency-Key still consumes a token.",
  "authorisation_rule": "The router requires a valid JWT for an existing user row and nothing more; the booking is always written against that user id, which is taken from the token and never from the request body. There is no role check beyond authentication, because no source restricts owning a booking by role and a guest is already stopped one step earlier at the hold.",
  "satisfies": ["P-PAY-01", "P-PAY-04", "P-PAY-05", "P-PAY-06", "P-PAY-07", "P-PAY-08", "P-PAY-09", "P-PAY-10", "P-PAY-11", "P-PAY-12"],
  "brd": ["R-PAY-01", "R-PAY-02", "R-PAY-03", "R-PAY-04", "R-PAY-05", "R-PRC-03", "R-PRC-04", "R-PRC-05"]
}
```

One error code this endpoint needs is not in the `FR-ADR-052` registry. It is emitted rather than
invented inline:

```newerrorcode
{"code":"REQUEST_INVALID","http":400,"when":"A required header or body field is missing or malformed, or the body carries a property the endpoint does not define. On this endpoint the load-bearing case is a missing Idempotency-Key, which FR-ADR-020 requires to be a 400 — the registry in FR-ADR-052 has no 400 code, so there is no registered code to return.","raised_by":["EP-PAY-01","EP-HLD-02","EP-HLD-03","EP-HLD-04"],"why_needed":"ADJUDICATED IN THE MERGE PASS as REQUEST_INVALID, distinct from VALIDATION_FAILED (422) which five other lanes use for field-level failure. FR-ADR-020 states 'A missing Idempotency-Key header on booking confirmation is a 400' and FR-ADR-052's list contains no 400. Without a registered code the interface would have to branch on the HTTP status alone for this one case, which FR-ADR-052 explicitly rejects, or the handler would have to invent a string. Almost every write endpoint in this product has the same gap, so this belongs in the registry rather than in one lane."}
```

---

## Lane notes

### Article X candidates raised by this lane

**None.** Every reserved question this epic touches maps onto a row that already exists in
`CONSTITUTION.md` Article X:

- **`OPEN-SHOWCANCEL-01`** is the only route by which a captured payment could ever need unwinding.
  This lane names the surface — no withdraw-showtime capability exists in v1 — and writes no money
  behaviour, no endpoint and no screen for it (`P-PAY-12`, `FR-ADR-023`).
- **`OPEN-EMAILFAIL-01`** is downstream of this lane. `P-PAY-10` steps 9 and 10 make the receipt job durable
  through the outbox, and this section writes **no sentence** about what a customer is told when the
  receipt definitively fails. That is lane E4's surface and it is `NOT_DECIDED` (`FR-ADR-049`).
- **`OPEN-TLS-01`** and **`OPEN-ATTRIB-01`** do not touch this epic.

### Assumptions I had to flag

| Flag | Value | Where it bites |
|---|---|---|
| `ASSUMED` | Seat category names **Standard, Premium, Recliner** (`SRC-003 OPEN-SEAT-01`, "you pick") | Every worked example in `P-PAY-03` and `P-PAY-04` names them. **The arithmetic does not depend on the names**, only on the uplift integers, so a rename changes the examples and nothing else. The categories are a table, not an enum, so a fourth costs no migration. |
| `ASSUMED` | Category uplifts `0` / `1250` / `3333` basis points, and the base price `27500` paise, used in the worked examples | These are illustrative inputs, not configured values. A test written from the worked examples must supply them explicitly rather than read them from seed data. |
| `ASSUMED` | `PAYMENT_SIMULATED_DELAY_MS = 1500` | `FR-ADR-041` says "a small number of seconds" and names no figure. The value drives the `Retry-After` formula in `P-PAY-09` and the transaction-duration example in `P-PAY-10`. **Measure it in Phase 4 and replace the figure.** The *bound* is not assumed: `FR-ADR-041` requires the delay "well below" the hold, and `P-PAY-07` fixes that as **strictly less than a tenth of `SEAT_HOLD_TTL_SECONDS * 1000`** — 18,000 ms at the ruled 180-second hold. `1500` is a twelfth of that bound and has ample room. |
| `PROVISIONAL` | Sales close **15 minutes after** the advertised start (`SRC-003 OPEN-BOOK-03`, `FR-ADR-042`) | It bites this lane only through `P-PAY-10` step 4, which does **not** enforce the cut-off. Reversing the sign changes when a hold can be taken, and changes nothing in this epic. |
| `PROVISIONAL` | Base price is per showtime rather than global (`SRC-003 OPEN-PRICE-01`, `FR-ADR-037`) | `P-PAY-03` reads `showtime.base_price_paise`. If the client reverses this to one global price, the read moves to a configuration value and the formula, the rounding and every worked example are unchanged. |
| `PROVISIONAL` | Four roles (`SRC-003 C-1`, `FR-ADR-009`) | `EP-PAY-01`'s `roles` array lists three of them. If the role set collapses to one, the authorisation rule — "a valid JWT for an existing user row" — is unchanged, because it does not name a role. |

### Where I would have had to guess and did not

1. **What a customer is told when the receipt definitively fails after the payment is captured.**
   `OPEN-EMAILFAIL-01` is open and reserved: product. `FR-ADR-049` decides nothing. This section
   contains no copy for that case and no booking-state change for it. The mitigations that exist
   without a ruling — the reference on the confirmation screen and in the bookings list — are lane
   E4's and are cited, not extended.

2. **What happens to a captured payment when an admin withdraws a showtime that already has
   bookings.** `OPEN-SHOWCANCEL-01`, reserved: money and irreversible. No refund path, no reversal
   state, no `refunded` transition, and no withdrawal endpoint is specified anywhere in this lane.

3. **Whether a `manager` account may buy a ticket for themselves.** No source says. `FR-ADR-009` makes
   a manager read-only for *privileged* writes and `SRC-003 OPEN-OPS-03` is about privileged actions;
   a customer buying their own ticket is not a privileged action. I did not invent either a permission
   or a prohibition: `EP-PAY-01`'s authorisation rule requires **authentication and nothing more**,
   which is the only rule that follows from `FR-ADR-014` ("a booking carries a non-null foreign key to
   a user row") without adding a rule nobody wrote. If the merge pass wants managers excluded, that is
   a new prohibition and it needs a decision, not a default.

4. **A tax-inclusive or tax-exclusive interpretation of the stored total.** There is no answer,
   because there is no tax (`SRC-003 OPEN-PRICE-03`). I did not model a zero-rate field to "keep the
   option open" — a zero-rate field would require choosing inclusive or exclusive, which is exactly the
   question with no answer. `P-PAY-06` states instead that the total cannot be split later.

5. **A refund amount, a cancellation reason or a cancellation window.** All money. All absent.

### Judgment calls this lane made, logged

- **`[JUDGMENT CALL]` The deliberate payment-failure trigger is an `Idempotency-Key` prefix**
  (`PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`), not a request-body field. `FR-ADR-041` requires "a designated
  input that fails" and names none. A header prefix keeps any failure-control field out of the public
  request contract, which matters because `P-PAY-06` and `P-PAY-08` both forbid additional properties
  on the body. Rejected alternative: a `simulate_failure` boolean in the body, which would have to be
  accepted by the schema and would then exist in the contract forever.
- **`[JUDGMENT CALL]` A failed capture commits its `payment` row in a separate transaction** while the
  booking transaction rolls back. `FR-ADR-041` gives the payment record a `failed` state, and
  `FR-ADR-029` puts the capture inside a transaction that rolls back on failure — so a `failed` row
  written inside that transaction would be rolled away and the state would never be observable. The
  separate commit is what makes `failed` mean anything. Consequence, stated: a failed attempt's
  idempotency record rolls back with the booking transaction, so the same key can be retried, which is
  correct because nothing was charged.
- **`[JUDGMENT CALL]` `booking.payment_id` points at `payment.id`, not the reverse.** The payment row
  exists before the booking row does (`FR-ADR-029` steps 6 and 7), so a `payment.booking_id` foreign
  key could not be satisfied at insert time without reordering the transaction against
  `SRC-001 §5.3.1`. This is a data-model consequence and the `06 DataModel` package should carry it.
- **`[JUDGMENT CALL]` `Retry-After` for `IDEMPOTENCY_IN_FLIGHT` is
  `ceil(PAYMENT_SIMULATED_DELAY_MS / 1000) + 1`.** `FR-ADR-020` requires the header and names no
  value. Tying it to the only bounded wait in the transaction means raising the artificial delay
  raises the advice automatically.
- **`[JUDGMENT CALL]` The confirm request accepts no seat identifiers.** Nothing says it must not, and
  accepting them would let a caller confirm seats it never held. Adopting the narrower contract is the
  stricter option.
- **`[JUDGMENT CALL]` The published `RATE_LIMITED` span on this endpoint is 6 seconds, computed from
  the per-user bucket's refill interval.** Both published copies previously read *"Try again in 30
  seconds"*, which is the per-IP bucket's **capacity** rather than any bucket's refill interval — a
  capacity is a count and only the refill interval is a duration. `EP-PAY-01` carries 10 per minute per
  user and 30 per minute per IP; the per-user bucket is the narrower and refills one token every 6
  seconds, so 6 is the value the header carries and 6 is the number in the sentence. **Reversible** —
  it is one computed value in two cells and one worked example, and it moves automatically if either
  bucket is reconfigured. Under **S7.20** 6 is below 120 and therefore renders as seconds.
- **`[JUDGMENT CALL]` `SCR-PAY-01` distinguishes "already confirmed" from "hold expired" using a
  booking reference stored in `sessionStorage`, and issues no request to do it.** No source specifies
  the mechanism and both states are entered from the same client-visible fact. Rejected alternative:
  replaying `EP-PAY-01` — it spends a rate-limit token even on a replay (`P-XCT-07` exception 4), and
  it returns three different answers that would all have to be disambiguated to learn something the
  client already knows. Rejected alternative: a new field on the endpoint — `P-PAY-09`'s neighbours
  refuse to widen this endpoint and that refusal stands. **Reversible** — it is one stored key and one
  branch, and it adds nothing to the wire contract.
- **`[JUDGMENT CALL]` `SCR-PAY-01` states from its own side that `SCR-SEA-01`'s post-hold control is
  navigation.** The claim "the only screen in the product with a pay action" was only checkable by
  reading the other screen and finding a button labelled `Pay …` there. E2 relabelled that control
  `Continue to payment`; this screen now says what the other one does rather than only what it does
  not. **Reversible** — one paragraph in each file, and they must move together.

### Corrections applied in iteration 6, neither of which was a decision

| # | What was wrong | What it now says |
|---|---|---|
| `F1` | `P-PAY-01` bounded `hold_token` at 1–128 characters, while `P-HLD-03` and `P-HLD-08` said 1..255 and five endpoint blocks said exactly 43 | **Exactly 43 characters from the URL-safe base64 alphabet.** The endpoint block owns wire shape (`S1.2` rank 1), so all three P-rows were wrong and none of the blocks was |
| `F12` | `SCR-SEA-01` labelled its post-hold control `Pay ₹1,562.49` while this screen claimed to be the only one with a pay action | E2 relabelled that control `Continue to payment`; this screen carries the paragraph above naming it as navigation. The two statements are now consistent and each is checkable without the other |
| `F1` | `P-PAY-10`'s eleven-step transaction and fifteen-row crash table **never mentioned the `receipt_dispatch` insert**, while `P-TKT-04` states at length that the row is written inside this transaction | The insert is **step 9**, between the audit no-op and the outbox insert; the outbox insert moves to 10, the idempotency completion to 11, COMMIT to 12, and the three post-commit steps to 13–15. The crash table gains two rows and is now sixteen. **This was the most serious defect of the pass**: built from this row alone, no dispatch row would exist, `P-TKT-05`'s claim would match zero rows, and no receipt would ever be sent — with nothing erroring and nothing logging |
| `D12` | `SCR-PAY-01` cleared `fr.last_booking_reference` on a different-showtime hold and on tab close, **not on sign-out** | Cleared on sign-out too, with every other `fr.*` value. The consequence is stated at the site because it is sharper than a stranded hold: without it, customer B signing in **in the same tab** and opening the checkout route is redirected — **with no request** — to customer A's confirmation URL, landing on a 404 with **a stranger's booking reference in their address bar**. The no-request redirect and the sign-out clear may not be separated |
| `F7` | `PAYMENT_FAILED`'s two strings were attributed to `P-HLD-14` in **three** places, and that row's message set carries no `PAYMENT_FAILED` entry — a dead pointer, three times | `P-PAY-01` exception 4 **declared the owner**; `P-PAY-07` exception 4 and `SCR-PAY-01`'s copy row now defer to it. The strings themselves are unchanged and were already identical everywhere, so nothing shipped differently — only the pointer was wrong |
| `D7` | Three of lane E2's endpoints now raise `REQUEST_INVALID` for a malformed hold token, and this lane's `newerrorcode` block declared only `EP-PAY-01` as raising it | `raised_by` extended to `EP-PAY-01`, `EP-HLD-02`, `EP-HLD-03`, `EP-HLD-04`. The code, the status and the sentence are unchanged — this is the declaration catching up with a fourth caller, which is what the declaration discipline is for |
| `D12` | `SCR-XCT-01`'s `Choose seats again` action for `HOLD_EXPIRED` versus this screen, which deferred the string and specified no control | Settled explicitly: **no banner on this screen carries a control.** The return to the seat map is already automatic in the **Expired** state, so the button offers to do what is already happening, and a customer pressing it mid-navigation presses a control that has left the screen |
| `F3` | `EP-PAY-01`'s `booking_reference` read *"8 characters, presented as `FR-XXXX-XXXX`"* — two shapes in one field description — while every other endpoint returning a reference carries the presentation form | One shape: **the presentation form `FR-XXXX-XXXX`, hyphens included**, re-formatted at serialisation from the 8 stored characters. The stored form never crosses the wire |
| `F7` | `SALES_CLOSED` was absent from `EP-PAY-01`'s `errors` while four sections discuss the cut-off at confirm, leaving a reader unable to tell omission from decision | The block carries an explicit `errors_deliberately_absent` note: it **cannot** be raised here, because the cut-off is enforced once at hold acquisition and `SRC-003 OPEN-BOOK-03` rules that a customer already holding may finish. The absence is now a recorded decision |
| `D6` | `EP-PAY-01`'s `201` serialised `starts_at` as *"UTC, rendered in Asia/Kolkata"* and `created_at` as UTC, leaving the client to convert — a second implementation of `FR-ADR-018` that is wrong on a device set to another country | Both fields now carry **the cinema's UTC offset**, read from the cinema row, e.g. `2026-08-20T14:00:00+05:30`. The client converts nothing. `P-PAY-01` states the rule and `SCR-PAY-01`'s showtime line states it renders what it is given. **`expires_at` is the stated exception and stays UTC** — it is subtracted, never rendered as a time of day |
| `F6` | `P-HLD-14` row 4 had no plural partner for `SEAT_UNAVAILABLE` at confirm | E2 published row **4b**. Here: `P-PAY-11` exception 1 splits into 1 (one seat) and 1b (two or more), and `SCR-PAY-01`'s copy row stops claiming it substitutes seat labels into the sentence — the server renders the whole string, and `details.unavailable_seats` is read only to mark seats on the map |
| `F6 (500)` | The confirm `500` published *"…this booking was not completed."* while `P-TKT-01` exception 2 published the same plus *"No payment was taken."*, and this screen rendered the shorter one | `P-TKT-01`'s fuller sentence, in **all four** places this lane publishes a `500` — not the two the brief named, because two would have re-created the drift. It is true on every one of them: every `500` here rolls the transaction back and the `payment` row is inside it |
| `F7` | This screen published a shortened countdown warning line against `SCR-SEA-02`'s, which declares itself the single source for that component | All four countdown strings are now deferred to `SCR-SEA-02` and this screen publishes none. Deleted rather than reconciled — a matching copy is still two strings to keep in step |

### Contradictions found between approved records

Named here rather than resolved silently. Both sides are stated.

1. **Is the sales cut-off enforced in the confirm transaction?**
   - **`FR-ADR-029` step 4** says: "Check the sales cut-off (`FR-ADR-042`)."
   - **`FR-ADR-042`** says: "**Checked at hold acquisition, not at confirmation.** … the confirm path
     does not need to re-check and cannot reject a customer who is already paying."
   - **`SRC-003 OPEN-BOOK-03`** says: "anyone already holding seats may finish checking out."
   - **How this lane resolved it, and why:** the confirm path does **not** enforce the cut-off
     (`P-PAY-10` step 4). Under `CONSTITUTION.md` Art II.1 a client ruling outranks an `APPROVED` ADR,
     and `OPEN-BOOK-03` settles it directly. The consequence is that `SALES_CLOSED` is **not** an error
     of `EP-PAY-01` and does not appear in its `errors` array. The merge pass should decide whether
     `FR-ADR-029` step 4 wants rewording.

2. **Where in `FR-ADR-029`'s numbered list does the outbox insert go?**
   - **`FR-ADR-031`** says the outbox row "is inserted inside the booking transaction, at step 9 of
     `FR-ADR-029`, immediately before commit."
   - **`FR-ADR-029`'s own list** has ten steps, step 9 is "update the idempotency record to
     `completed`", and it contains **no outbox insert at all**.
   - **How this lane resolved it:** `P-PAY-10` places the outbox insert after the audit step and before
     the idempotency completion update, which satisfies both "inside the transaction" and "immediately
     before commit". The numbering is renormalised to twelve in-transaction steps plus three
     post-commit steps. No behaviour changes; only the step numbers do.

3. **A gap rather than a contradiction: the error registry has no 400 code.** `FR-ADR-020` requires a
   missing `Idempotency-Key` to be a `400`; `FR-ADR-052`'s list contains no code at `400`. Emitted as
   the `newerrorcode` block above rather than invented inline.

4. **A gap rather than a contradiction: a `failed` payment state that nothing can observe.**
   `FR-ADR-041` defines `failed`; `FR-ADR-029` puts the capture inside a transaction that rolls back on
   failure. Resolved by the judgment call above, and recorded here because a reviewer reading either
   record alone will not see the interaction.

### Seams this lane depends on and does not own

- **Lane E2** owns the hold, the Redis lock, the seat state machine, and — critically — the endpoint
  that a reloaded checkout screen reads to recover its seat list, prices and `expires_at` from a hold
  token in `sessionStorage`. **If no such read exists, `SCR-PAY-01` cannot survive a page refresh**,
  which `FR-ADR-047` explicitly requires it to. This section assumes that read exists and does not
  specify it. Lane E2 also owns **the customer-facing wording of every hold-related error code** —
  `HOLD_EXPIRED`, `HOLD_NOT_OWNED`, `SEAT_UNAVAILABLE` and `DEPENDENCY_UNAVAILABLE` — published as one
  set in `P-HLD-14` with an *at confirm* row for each. `P-PAY-01`, `P-PAY-11` and `SCR-PAY-01` all
  render those strings and none of them restates one. **If `P-HLD-14` ever stops publishing an *at
  confirm* row for one of the four, this lane has no copy for it and that is a gap to escalate, not a
  gap to fill.**
- **Lane E4** owns the booking reference format and generation, the receipt job, and the confirmation
  screen. `EP-PAY-01` returns `booking_reference` in its `201` body because it is this endpoint's
  response; the value's shape is `FR-ADR-015`'s and its rendering is `COMPONENTS.md §9`.
- **Lane E5** owns the admin writes that set `showtime.base_price_paise` and
  `seat_category.uplift_basis_points`. This lane consumes both and never writes either.
- **Lane E8** owns `/health/ready`, which `P-PAY-07` requires to report the configured payment
  provider, and the boot-time configuration validation for `PAYMENT_PROVIDER`,
  `PAYMENT_SIMULATED_DELAY_MS`, `PAYMENT_SIMULATOR_FAIL_KEY_PREFIX`, `CURRENCY_CODE` and
  `CURRENCY_MINOR_UNIT_RATIO`.
