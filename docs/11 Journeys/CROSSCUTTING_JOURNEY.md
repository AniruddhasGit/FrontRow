# Cross-cutting journeys — the nine rows no persona lane walked

```
Lane .............. CROSS-CUTTING (defect prefix J-XCT)
Produced by ....... GOAL_06 (goals/GOAL_06_journeys.txt), closing pass
Written ........... 2026-08-22
Sections read ..... docs/03 PRD/sections/E8_crosscutting.md  — P-XCT-01, -02, -06, -09,
                    -24, -25, -30 (hall layouts, seeded bookings), -32, read in full;
                    S7.1, S7.5, S7.13, S7.9 (seed variables), S7.18, SCR-XCT-05
                    docs/03 PRD/sections/E5_account.md      — P-ACC-04, -05, -06, -09,
                    SCR-ACC-01/-02/-03 field tables
                    docs/03 PRD/sections/E2_seat_hold.md    — P-SEA-03, P-HLD-08, -13, -14,
                    SCR-SEA-01, SCR-SEA-03, EP-HLD-04
                    docs/03 PRD/sections/E3_checkout_payment.md — P-PAY-10, -11, -12, SCR-PAY-01
                    docs/03 PRD/sections/S1_reading_rules.md · S3_personas_surfaces.md
                    docs/05 B DesignSystem/ — COMPONENTS.md §0, §1, §6, §7, §8, §11; tokens.css
                    docs/30 Deployment/AWS_PREP_QUEUE.md
Not read .......... docs/03 PRD/FrontRow_PRD.md (1.9 MB generated assembly)
Authority ......... CONSTITUTION.md Art II.1. A journey never outranks the PRD; where this
                    document and the PRD disagree, this document is reporting a defect in
                    the PRD and the defect is filed, not fixed here.
```

## Why this lane exists, and what makes it different from the other five

**This lane closes a measured coverage gap.** Five persona lanes walked FrontRow independently and
blind, touched **140 of the PRD's 163 P-rows**, and filed **64 defects**. `JOURNEY_INDEX.md` reports
that fourteen of the twenty-three untouched rows are build and infrastructure constraints with no
user standing in them — not walkable — and that **nine were walkable and were not walked**. Three of
those nine are load-bearing, including `P-XCT-01`, the row that states the product's central
invariant.

**This lane was not blind to the five persona lanes, and that is deliberate.** Isolation is what
makes an independent convergence evidence; there is nothing to converge on here, because the job is
to walk nine named rows that are known not to have been walked. `JOURNEY_INDEX.md` and
`DEFECTS_FOUND.tsv` were both read before the first walk. **Where a walk below lands on something
already in `DEFECTS_FOUND.tsv`, the existing `J-` id is cited in the prose and no new row is
created.** Three walks do that.

**Nothing here was observed.** No application code exists in this repository. Every statement is
read from the specification, and every claim about AWS behaviour is **reasoned, not observed**, and
is labelled at its point of use.

**One assumption is flagged wherever it bites rather than once.** Hall sizes are `ASSUMED`, not
`RULED` (`SRC-003 OPEN-SCALE-02`, the client said "pick random"). Walk 3 divides by 220 seats and
`P-XCT-30`'s derived 11 × 20 grid throughout, and says so at each figure.

---

## What the nine walks found, worst first

| | |
|---|---|
| Walks | **9** |
| Steps | **71**, every one crossing a named seam — `system` 42 · `page` 22 · `process` 4 · `time` 3 |
| Distinct P-rows cited in the step tables | **18** |
| Defects filed | **17** — 7 `blocks-code`, 8 `ambiguous`, 2 `cosmetic` |
| Prior defects re-encountered and **not** re-filed | 3 (`J-ENT-01`, `J-CUS-10`, `J-MGR-09`) |

**The single most consequential finding is `J-XCT-01`, and it lands on the one gate that is never
waivable.** `P-XCT-01`'s red-proof drill — drop the unique constraint, watch the stress script
produce more than one winner, restore it — **cannot produce more than one winner as specified**,
because `P-HLD-13` and `P-PAY-11` both fix the gate at the *hold* endpoint, where the unique
constraint plays no part. That is walked in full at Walk 1, steps 7 to 10.

---

# Walk 1 — `P-XCT-01`: two customers race for one seat, and Redis is wrong

**Who.** Two signed-in customers, A and B, in two browsers, both looking at the seat map for
showtime 41 and both wanting seat 312 (`C12` in Screen 6's labelling).

**What this walk is for.** `P-XCT-01` states the guarantee. No persona walk cited it. This walk finds
out whether that is because the row is complete and simply was not named, or because the guarantee is
stated somewhere no walk passes through. **It is the second.** The row is reachable from the product
only through the loser's error banner; everything else in it — the constraint, the drill, the
worked example — sits on a build gate that no customer, admin or manager stands in. That explains the
coverage gap and does not excuse it, because the row is not internally consistent with the two rows
that own its two halves.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` seat map, browser A | signed in, `C12` renders `available` | A taps `C12`, then presses `Hold these seats` | browser -> API -> Redis: `SET lock:seat:41:312 <tokenA> NX PX 180000`, one command | `system` | a hold token, `expires_at`, `C12` repainted `held_by_me` with a tick and a 2px border | `P-XCT-01` `P-SEA-03` | — |
| 2 | `SCR-SEA-01` seat map, browser B | signed in, B's last poll still shows `C12` `available` | B taps `C12` and presses `Hold these seats` in the same millisecond | API -> Redis: the same `SET … NX`, which returns nil because the key exists | `system` | `409 SEAT_UNAVAILABLE`, `details.unavailable_seats = ["C12"]` | `P-XCT-01` `P-HLD-14` | — |
| 3 | `SCR-SEA-03` banner over B's map | B pressed a control and got a refusal | B reads the banner, which branches on `code`, never on text | API -> browser: the one error envelope | `page` | `C12 was taken by another customer. No seats were held. Choose a different seat and press Hold these seats again.` (`P-HLD-14` row 2) | `P-HLD-14` | — |
| 4 | B's map, next poll | B has no hold | the 3-second poll returns | API -> Redis cache `DEL`ed by A's hold, rebuilt from Postgres | `system` | `C12` repaints `held_by_other` — a flat bar, no border, brass — never confusable with A's tick | `P-SEA-03` `P-XCT-01` | — |
| 5 | `SCR-PAY-01`, browser A | A holds `C12`, countdown running from a server-issued `expires_at` | A presses `Pay ₹333.31` | API -> Postgres: one transaction; step 2 re-validates the Redis token, step 6 captures the simulated payment, step 7 inserts `booking_seat` | `system` | `201`, a booking reference, the seats sold | `P-PAY-10` `P-XCT-01` | — |
| 6 | **Redis is wrong.** A's lock was evicted under memory pressure and B won a second lock for `C12` | B now holds a token for a seat A has already sold | B presses `Pay` | API -> Postgres step 7: the unique constraint on `(showtime_id, seat_id)` fires | `system` | `409 SEAT_UNAVAILABLE`, whole transaction rolled back, no `payment` row survives | `P-XCT-01` `P-PAY-11` `P-PAY-10` | **`J-XCT-02`** |
| 7 | The stress script, local Docker | fifty seeded customers authenticated in an untimed warm-up | fires fifty simultaneous requests for `(41, 312)` | script -> API -> Redis: fifty `SET … NX` on one key | `system` | one `201`, forty-nine `409 SEAT_UNAVAILABLE` | `P-HLD-13` `P-XCT-01` | — |
| 8 | The stress script | one winner holds the seat | the winner confirms; the script reads `booking_seat` directly from PostgreSQL | script -> Postgres: `SELECT count(*)` | `system` | `1`. The gate passes | `P-HLD-13` `P-XCT-01` `P-PAY-11` | — |
| 9 | The red-proof drill | the gate is green | drop the unique constraint on purpose and re-run | operator -> Postgres: `ALTER TABLE … DROP CONSTRAINT` | `system` | **still exactly one winner** — Redis grants one lock and one customer confirms, so the constraint was never reached | `P-XCT-01` `P-HLD-13` `P-PAY-11` | **`J-XCT-01`** |
| 10 | The red-proof drill | one winner with the constraint dropped | read the rule for that outcome | drill -> `P-XCT-01` exception 5 and `P-HLD-13` exception 4 | `process` | "the drill is recorded as **failed** and the whole proof is void" / "**stop the line**" — the specification declares its own correct implementation a stop-the-line finding | `P-XCT-01` `P-HLD-13` | **`J-XCT-01`** |

### Step 9 and 10, stated plainly, because this is the never-waivable gate

`P-HLD-13` owns the gate and says it in terms: fifty simultaneous **hold** requests, one `201`,
forty-nine `409`, then *"the winner confirms its hold"* and one `booking_seat` row.
`P-PAY-11`'s worked example says the same thing and says why: *"**It is the hold, not the confirm** —
a confirm-based variant could not work, because forty-nine of the fifty would hold no lock and would
fail re-validation with `HOLD_EXPIRED` rather than meeting the unique constraint."*

Under that shape, **the unique constraint fires zero times in a passing run of the gate.** Every one
of the forty-nine losers is refused by Redis at the `SET … NX`. Only one customer ever reaches
step 7 of `P-PAY-10`, and they reach it uncontended.

So dropping the constraint changes nothing observable. Redis still grants one lock, one customer
still confirms, and `SELECT count(*)` still returns 1. To make the drill produce two winners the
Redis lock layer would have to be bypassed as well, and **no row says to do that** — `P-XCT-01`'s
drill is five numbered steps and none of them touches Redis.

`P-XCT-01`'s own happy path reads differently again: step 1 is a hold, step 2 is a confirm, and step
4 then asserts *"fifty simultaneous requests"* without naming which endpoint they hit, while
exception row 1 attributes the `409` to *"the unique constraint fires at insert — another booking took
the seat first."* Three rank-2 rows, one gate, and the developer transcribing the acceptance criterion
has to decide which of them is describing the run. **`S1.2.1` case 1 says a tie between two rank-2
rows that survives is a defect to raise, not a judgement for the implementer.** Filed as `J-XCT-01`.

### Step 6 — the string the loser reads at confirm is the wrong one

`P-XCT-01` exception 1 publishes, verbatim:

> `C12 and C13 were taken by another customer. No seats were held. Your other choices are still selected.`

Its trigger is *"the unique constraint fires at insert"*, which is `P-PAY-10` step 7 — the confirm.
`P-HLD-14` declares itself the complete message set for these codes and gives the confirm case two
rows of its own:

> row 4b · `C12 and C13 were taken by another customer before your payment finished. Your booking was not made and you have not been charged.`

`P-PAY-11` defers to `P-HLD-14` rows 4 and 4b by name and deliberately does not restate them.
`P-XCT-01` restates a **different** row — `P-HLD-14` row 3, the *at hold* plural — for the confirm
case. Two of its three sentences are then false of the situation: the customer **did** hold seats,
and the transaction rolled back **in full** (`P-PAY-11`), so nothing of theirs is still selected.
`P-SEA-03` spends a paragraph on exactly this distinction — *"'Still selected', never 'still held'"* —
which is what makes the borrowed sentence findable rather than merely different. Filed as `J-XCT-02`.

### Redis down, walked separately, because the rule is the opposite one

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 11 | `SCR-SEA-01` | a customer with a live selection, Redis unreachable | presses `Hold these seats` | API -> Redis: connect timeout on an explicit client timeout | `system` | `503 DEPENDENCY_UNAVAILABLE` — *"Seat holds are unavailable right now. Browsing still works. Try again in a few minutes."* | `P-XCT-09` `P-XCT-01` | — |
| 12 | `SCR-SEA-01` | the same customer, the map polls | the 3-second poll fires | API -> Redis: the rate-limit token bucket cannot be evaluated, and the limiter runs **before** the cache | `system` | `503` — **not** a 200 served from PostgreSQL. The limiter fails closed and the fallback is never reached | `P-XCT-09` | — |
| 13 | the movie listing | the same outage | the customer navigates back to `/` | API -> Postgres: cache miss falls through | `system` | `200`. Browsing keeps working exactly where it is not rate-limited | `P-XCT-09` | — |

**There is no silent fallback and the specification is unambiguous about it.** `P-XCT-09` exception 5
records *"code falls back to the database for locking"* as forbidden and as a review finding rather
than a runtime path, and `S7.1` gives the reason without softening it: Redis being wrong produces two
holders, and with no database guard there is then nothing to stop two bookings. This half of the walk
found no defect, and that is believable: the conflict between `FR-ADR-028` (the cache degrades) and
`FR-ADR-058` (the limiter fails closed) was already adjudicated inside `P-XCT-09`, with the stricter
option taken and the reason written down. **The consequence is also stated rather than softened:**
with one EC2 instance, `/health/ready` returning 503 removes the only instance from the load
balancer, so browsing is down regardless of what the application would have served. *(Reasoned, not
observed — the load balancer's thresholds are Zone C values the client sets.)*

---

# Walk 2 — `P-XCT-32`: a freshly seeded deployment, and nobody can sign in

**Who.** The client, who is also the developer and the operator, standing in front of an environment
they have just built by hand.

**What this walk is for.** `P-XCT-32` is known-and-unbuilt and it stops **Phase 2 and Phase 4**, and
Phase 4 is the concurrency proof. No persona walk starts from "cannot log in at all", so no lane
reached it. This walk starts there.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | a terminal | RDS exists, the schema is migrated as an explicit step, the database is empty | the client runs `scripts/seed.py` with `SEED_DEFAULT_PASSWORD` unset | seed -> environment: the variable is read and found absent | `system` | **the seed exits non-zero before its first write**, naming the variable. Not a warning, not a generated value. The database is exactly as it was | `P-XCT-32` | — |
| 2 | a terminal | the client sets `SEED_DEFAULT_PASSWORD` and re-runs | the seed validates the value, hashes it **once** at `BCRYPT_COST` through the application's own function | seed -> Postgres: 63 user rows, six halls, 720 showtimes, 11,003 bookings | `system` | printed **addresses only**, grouped by role, with counts. Never the password | `P-XCT-32` `P-XCT-30` | — |
| 3 | a terminal | the seed has run | the client checks whether the value they chose is one the application would accept | seed precondition -> `P-XCT-06`'s bound | `system` | two different floors: the seed says "at least `PASSWORD_MIN_LENGTH` **bytes**", the application says 12 **characters** | `P-XCT-32` `P-XCT-06` | **`J-XCT-13`** |
| 4 | `SCR-ACC-01` sign in | the client opens the deployed site | signs in as `admin-01@demo.frontrow.invalid` with the value they set | browser -> API -> Postgres: bcrypt compare off the event loop | `system` | a session cookie, and Phase 2 proceeds | `P-XCT-32` `P-XCT-06` | — |
| 5 | `SCR-ACC-02` request a password reset | **the counterfactual: the variable was never set** | the client uses the only route the rest of the document specifies to a first password | API -> queue -> worker -> SES `SendEmail` | `process` | **`202` and the uniform sentence** — *"If that address has an account, a reset link has been sent to it."* | `P-XCT-32` `P-ACC-04` | — |
| 6 | the client's inbox | the reset was requested | waiting | SES -> nowhere. SES starts **sandboxed** and refuses any recipient the client has not verified, and `demo.frontrow.invalid` is reserved by RFC 2606 and can never be verified | `system` | **no mail, ever, and no error the requester can see** — `P-ACC-07` answers uniformly so it cannot disclose that the address is unreachable | `P-XCT-32` `P-ACC-04` | — |
| 7 | a terminal, back at the start | the client wants to run the seed against the **deployed** environment as `P-XCT-32` and `P-XCT-30` require | looks for the specification that says how | build session -> `docs/30 Deployment/`: eighteen `REQUESTED` rows, **none of them a way to run a one-off task against RDS with a secret supplied at run time** | `system` | nothing to build against, and Phase 2 blocked on it | `P-XCT-32` `P-XCT-30` | **`J-XCT-03`** |

### What a developer standing in front of a freshly seeded environment can and cannot do

**Can.** Sign in as `admin-01@…` through `admin-12@…`, `manager-01@…` through `manager-12@…` and
`customer-01@…` through `customer-50@…`, **if and only if they personally set
`SEED_DEFAULT_PASSWORD` in the environment the seed ran in and still remember it.** The addresses are
deterministic on purpose, so the identifiers are discoverable and the secret is not.

**Cannot.** Recover that password by any route in the product. Hashes cannot be read back
(`P-XCT-06`). The reset flow is not a route: SES is sandboxed and every seeded address is at a
domain that is guaranteed never to resolve, so out of the sandbox those sends would be **hard
bounces**, and a hard-bounce rate is charged against the sending identity's reputation and can get
the SES account suspended — taking the real receipt path down with it. `P-XCT-32` exception 7 says
this in terms: *"it does not work, and that is the whole reason this row exists."*

**And cannot run the seed against AWS at all, as of today.** `P-XCT-32` assigns the deployed run to
the client — *"the build session has no write access to anything in AWS and cannot run it there"* —
and `P-XCT-26` requires the build session to owe the client a Zone C specification for every item
the client must build. Running a container against RDS inside the VPC, with a secret injected at run
time and never committed, is a Zone C artefact. `AWS_PREP_QUEUE.md` has eighteen rows and no such
row; `docs/30 Deployment/` holds no specification for it; and `S7.9` puts `SEED_DEFAULT_PASSWORD` in
a seed-only table read by neither the API nor the worker, so **it cannot ride in on the task
definition's SSM `secrets` block** (row 6, row 15). The dependency is needed by **Phase 2**, and the
project's own rule is that a dependency is announced early enough to prepare, never on the day it
blocks. Filed as `J-XCT-03`.

**One thing this walk checked and did not find.** `P-XCT-32` is thorough where it is reachable: it
refuses the placeholder by value, refuses to print, refuses a per-account random password with a
stated reason, is idempotent so a re-run does not reset a password the client changed by hand, and
writes a `suppressed` `receipt_dispatch` row for all 11,003 seeded bookings rather than leaving them
on a branch `P-TKT-05` calls unreachable. The unit slip in step 3 is the only internal fault found,
and it is in the row's own preconditions — the same row that spends two paragraphs on bytes not being
characters.

---

# Walk 3 — `P-XCT-25`: the largest hall's seat map on a 375-pixel phone

**Who.** A customer on a 375-pixel-wide phone, choosing three seats in Screen 6.

> ⚠ **The denominator is `ASSUMED`, not `RULED`.** Screen 6 is 220 seats laid out **11 rows × 20
> columns**, derived by `P-XCT-30` from the six hall sizes the build session picked when the client
> said "pick random" (`SRC-003 OPEN-SCALE-02`). Every width figure below divides by that 20-column
> row. A client who names real halls replaces six numbers and every figure here recomputes.
> `P-XCT-25` states that a larger hall simply scrolls further, so **the assumption changes the
> arithmetic and not the design.** It is flagged again at each figure below.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-BRW-03` showtime page -> `SCR-SEA-01` | a guest on a 375px phone has picked a showtime in Screen 6 | the seat map loads | page -> API -> Postgres/Redis: the seat-map read, rate-limited per IP | `page` | the field, screen bar and row gutters drawn immediately at full size, seat cells as 60%-opacity blocks. **The frame never resizes when the data lands** | `P-XCT-25` `P-SEA-03` | — |
| 2 | `SCR-SEA-01` | the map has landed | the customer looks at the hall | layout -> viewport: a 20-column row is **20 × (24 + 4) − 4 = 556 px** *(20 columns is `ASSUMED`)* plus a 28 px pinned row gutter | `page` | a map wider than the phone. The seat is **not** shrunk: 24 px is the WCAG 2.2 target-size minimum | `P-XCT-25` `P-XCT-24` | — |
| 3 | `SCR-SEA-01` | the map is wider than the viewport | the customer swipes sideways inside the map | container -> its own horizontal scroll; the page body never scrolls sideways | `page` | roughly **half the hall visible at a time** — 375 px less a 16 px page gutter each side, less 16 px field padding each side, less the 28 px pinned gutter, is **283 px of a 556 px map** *(both figures `ASSUMED`)* | `P-XCT-25` | **`J-XCT-16`** |
| 4 | `SCR-SEA-01` | the map is open and the customer has not scrolled | the customer looks for the seats they want | first paint -> scroll container: **no row, screen or component states where the map opens** | `page` | seats 1 to about 10 of 20, chosen by nothing | `P-XCT-25` | **`J-XCT-06`** |
| 5 | `SCR-SEA-01` | three seats chosen in band `Recliner`, rows furthest from the screen | the customer scrolls down to read the summary panel, which sits **under** the map on a phone | page scroll -> the map's own container does **not** scroll vertically; rows grow it and the page scrolls | `page` | the total, the `Up to 10 seats.` note, and the primary action, all below 11 rows of map | `P-XCT-25` `P-SEA-03` | — |
| 6 | `SCR-SEA-01` | a chosen seat is taken by someone else between two polls | the 3-second poll returns and `SCR-SEA-03` fires above the map | banner -> "the scroll container's sticky header area, so it is visible without scrolling" | `page` | a banner pinned inside a container that scrolls **horizontally only**, on a page the customer has scrolled **vertically** past it | `P-XCT-25` `P-XCT-24` `P-SEA-03` | **`J-XCT-07`** |
| 7 | `SCR-SEA-01` -> `SCR-PAY-01` | a hold is live | presses `Continue to payment` | seat map -> checkout (`SCR-SEA-01` -> `SCR-PAY-01`), navigation only, no request | `page` | the checkout panel, the countdown repeated, and the simulated-payment slab above the heading at no smaller than body size | `P-XCT-25` `P-PAY-10` | — |

### The arithmetic, and where the published example stops short

`P-XCT-25`'s worked example is:

```
seat size ............... 24 px      --fr-seat-size
seat gap ................  4 px      --fr-seat-gap
per seat ................ 28 px
a 20-seat row ........... 20 × 28 − 4 = 556 px
plus row-label gutter ... 28 px      --fr-seat-gutter
total ................... 584 px  >  375 px viewport
```

Every figure is a token and the conclusion — it scrolls — is right. **What the example omits is that
the customer never has 375 px.** `COMPONENTS.md §0.1` puts a page gutter of `--fr-space-4` = 16 px on
each side on a phone, and `SCR-SEA-01` gives the map field padding of `--fr-space-4` = 16 px on each
side. The row gutter is **pinned left while the map scrolls**, so it consumes width permanently
rather than scrolling away. The visible strip is `375 − 32 − 32 − 28 = 283 px`, which is **10.1 of
the 20 columns** *(20 columns is `ASSUMED`)*. The example understates the scroll by a factor of about
two. That is `J-XCT-16` and it is cosmetic: nothing built from the example would be wrong, but a
reviewer checking "does it fit" against 584 versus 375 is checking a smaller gap than the one that
exists.

### Step 4 and step 6 are the two that actually bite a customer

**Step 4.** The map opens showing about half the hall and **nothing says which half.** The seat number
is inside each cell and the row letter is pinned, so a customer always knows where they are — but a
customer who wants the middle of row F has to discover that the middle exists. There is no minimap,
no column header, no scroll affordance specified, and no rule that the map opens centred on the
best seats, or scrolled to a restored selection, or at the left edge. Two implementers will pick
differently and both will pass every check in the document. This compounds with step 6 and with the
keyboard case in Walk 4, and all three are filed together as `J-XCT-06` because they are one missing
rule: **nothing in the specification ever scrolls the map container programmatically.**

**Step 6.** `SCR-SEA-03` and `COMPONENTS.md §6` both place the error banner *"inside the scroll
container's sticky header area, so it is visible without scrolling."* `COMPONENTS.md §1.3` states
that the map container scrolls **horizontally** and explicitly does not scroll vertically — *"rows
grow the container and the page scrolls normally"* — so a header sticky inside it is sticky against
an axis nobody is scrolling. Meanwhile `SCR-XCT-05` marks the application header **`Not sticky`**
and gives the reason by name: *"a sticky header steals vertical space from a 220-seat map on a 375px
phone, which `P-XCT-25` is about."* On the design target the customer reading row K is roughly 340 px
of map below the banner's anchor, and the banner naming the seat they just lost is off-screen. Filed
as `J-XCT-07`.

---

# Walk 4 — `P-XCT-24`: the booking path by keyboard, and by screen reader

**Who.** Two readers walking the same path: one using a keyboard and no pointer, one using a screen
reader. Browse, seat map, checkout, receipt.

**What this walk is for.** The target is **WCAG 2.2 Level AA, adopted by the build session, with no
conformance claimed and exactly one deviation recorded.** The brief asks whether the recorded
deviation is the one that actually bites.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-XCT-05` shell -> movie listing | a keyboard user lands on `/` | presses Tab once | page load -> the skip link, which is **first, always** | `page` | `Skip to content`, then `main`, which is focusable programmatically and carries the id the link targets | `P-XCT-24` | — |
| 2 | movie listing -> `SCR-BRW-03` | a film and a showtime chosen by keyboard | presses Enter on a showtime button, min height `--fr-tap-min` | route change -> focus moves to the destination's `h1` and the change is announced once in a polite live region | `page` | the seat map, focus never left on a control that no longer exists | `P-XCT-24` | — |
| 3 | `SCR-SEA-01` | focus is in `main` | presses Tab | shell -> the seat map, which is **one tab stop, not 220** | `page` | focus inside the grid. A grid of 220 tab stops is a keyboard trap with extra steps, not keyboard support | `P-XCT-24` | — |
| 4 | `SCR-SEA-01`, screen reader | focus is on a seat | reads the seat | DOM -> assistive technology: the accessible name | `page` | `Row C seat 12, Premium, available` — identity, category and state, with the number present even where the tick has replaced it visually | `P-XCT-24` | — |
| 5 | `SCR-SEA-01`, keyboard | focus is on `C10`, and the map shows about 10 of 20 columns *(`ASSUMED`)* | presses the right arrow to reach `C11` | arrow-key grid navigation -> the container's horizontal scroll position, which **nothing moves** | `page` | focus on a seat **outside the visible strip**, with the focus ring drawn where nobody can see it | `P-XCT-24` `P-XCT-25` | **`J-XCT-06`** |
| 6 | `SCR-SEA-01`, keyboard | focus has scrolled behind the **pinned** row gutter | continues arrow-keying left | focus -> an author-created sticky layer that overlays the leftmost cells | `page` | a focused control obscured by page content — WCAG 2.2 SC 2.4.11, new at AA in 2.2, unaddressed and unrecorded | `P-XCT-24` `P-XCT-25` | **`J-XCT-06`** |
| 7 | `SCR-SEA-01`, screen reader | a chosen seat is taken between two polls, and no request was sent | the map re-checks the local selection against the fresh map | poll -> the string `C12 is no longer available. It has been removed from your choices.` | `system` | **no surface and no announcement route.** `SCR-SEA-03` renders "the verbatim string for the `code`" and this event has no code, because nothing was requested | `P-SEA-03` `P-XCT-24` | **`J-XCT-08`** |
| 8 | `SCR-SEA-02` countdown | a hold is live, 60 seconds remain | the threshold is crossed | client -> a live region, announced **once** | `time` | bar colour, digit colour and a warning line change together. The digits are deliberately **not** a live region — a value announced every second is unusable | `P-XCT-24` | — |
| 9 | `SCR-PAY-01` -> receipt | a hold is live and the customer pays by keyboard | presses `Pay ₹999.93`; on failure the field error is associated with its field and announced | API -> browser: the error envelope, announced through a live region, never only coloured | `page` | either a booking reference, or an error a screen reader was told about | `P-XCT-24` `P-PAY-10` | — |

### The recorded deviation, and whether it is the one that bites

**The recorded deviation is the three-minute hold**, at `P-XCT-24` exception 3 and `S7.13`: the AA
timing criterion normally requires a time limit to be adjustable, and this one is not, because the
limit exists to release a scarce resource to other customers and an extension would let one customer
hold a seat indefinitely. The mitigation is real and is specified: the limit is displayed from the
start, warned once at 60 seconds, and the selection is restored on expiry so nothing is lost but the
seats.

**That is the honest one to record and it is arguably not the one that bites.** SC 2.2.1 carries an
"essential" exception for a time limit whose extension would invalidate the activity, and a seat hold
is that shape — the criterion's own canonical example is an auction. `P-XCT-24` records the deviation
without reaching that exception either way, which is the conservative choice and costs nothing.

**What is not recorded is the one this walk actually hit.** WCAG 2.2 adds SC 2.4.11 *Focus Not
Obscured (Minimum)* at Level AA, and the specified seat map engages it twice over: focus moves by
arrow key inside a container that is roughly half as wide as its content on the design target, and
the row gutter is a pinned layer that overlays the leftmost cells. **No row, screen spec or component
spec ever scrolls the map container programmatically**, for focus, for a restored selection, for a
named seat in an error, or on first paint. `P-XCT-24` says "every interactive element is reachable
and operable by keyboard, focus order follows visual order, and the focus indicator is visible
against every background it can appear on" — the ring's *colour* is measured against three grounds in
`CONTRAST.md`, and its *visibility on screen* is never specified. That is one missing rule producing
three symptoms, and it is `J-XCT-06`, the same defect Walk 3 steps 4 and 6 reached from the other
side.

### Checked and not filed, because a negative result is evidence

- **`autocomplete` is specified.** `SCR-ACC-01` gives the email field `type="email"`,
  `autocomplete="email"`, `inputmode="email"` and the password field
  `autocomplete="current-password"` / `new-password`; `SCR-ACC-02` and `SCR-ACC-03` carry the same.
  SC 1.3.5 and SC 3.3.8 are addressed. This was expected to be a gap and was not one.
- **Target size is met with the spacing exception.** `--fr-seat-size` is 24 px and `--fr-seat-gap` is
  4 px, so centre-to-centre is 28 px and 24 px-diameter circles centred on adjacent seats do not
  intersect. It clears SC 2.5.8 by 4 px, and `P-XCT-25` exception 2 refuses to shrink the seat to win
  a layout argument.
- **Colour is never the carrier.** Four seat states, each told apart by fill lightness, a mark and a
  border, with hue as a fifth and least important cue; `CONTRAST.md` is generated by `contrast.py` and
  a colour without a machine-readable annotation fails the check, so a colour cannot enter the system
  unmeasured. No contrast figure in the product is typed by hand.
- **Landmarks, focus-after-navigation, focus-after-sign-out, `prefers-reduced-motion`, and the
  nav-as-a-list** are all specified on `SCR-XCT-05` and `COMPONENTS.md §0.5`. The one motion
  exception — the changed-seat ring surviving as a static ring — is justified as information rather
  than decoration.

---

# Walk 5 — `P-XCT-06`: register, sign in, sign out, expire, over plain HTTP

**Who.** A first-time customer on the deployed environment, which has no TLS certificate because
`OPEN-TLS-01` is `OPEN` and `DEFERRED` and the client is still sourcing a domain
(`AWS_PREP_QUEUE.md` row 14, `BLOCKED`).

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ACC-01`, register tab | no account | submits an email and an 11-character password | API -> validation: minimum is 12 **characters** | `system` | `422 VALIDATION_FAILED` — *"Use a password of at least 12 characters."* | `P-XCT-06` | — |
| 2 | `SCR-ACC-01`, register tab | corrected to 25 Devanagari characters | submits | API -> bcrypt's 72-**byte** ceiling, enforced explicitly with its own message | `system` | `422` — *"Use a password of 72 bytes or fewer. Some characters count as more than one byte."* Not a silent truncation | `P-XCT-06` | — |
| 3 | `SCR-ACC-01`, register tab | a valid password | submits | API -> Postgres: unique index on `lower(email)`; bcrypt runs **in a thread**, not inside an `async def` | `system` | an account; the plaintext never logged, never returned, never stored | `P-XCT-06` `P-ACC-09` | — |
| 4 | `SCR-ACC-01`, sign-in tab | registered | signs in | API -> browser: `Set-Cookie: fr_session=<JWT>; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200` and `Secure` **from `COOKIE_SECURE`, which is off here** | `system` | a session that crosses the network in the clear | `P-XCT-06` `P-ACC-05` `P-ACC-06` | — |
| 5 | any authenticated request | signed in | the router dependency resolves the caller | API -> Postgres: a primary-key read of the user row on **every** request, comparing `pv` against the token's claim | `system` | a role read from the database and never from a claim, so a role change takes effect on the next request | `P-ACC-05` `P-XCT-06` | — |
| 6 | any non-`GET` endpoint | signed in, cookie auto-attached by the browser | a cross-site page attempts a state change | browser -> API: the only thing standing in the way is `SameSite=Lax` | `system` | **no CSRF token, no double-submit, no `Origin` check, and no passage naming `SameSite=Lax` as the defence** | `P-XCT-06` `P-ACC-05` | **`J-XCT-11`** |
| 7 | `SCR-XCT-05` header | signed in | presses `Sign out` | API -> browser: `204` with `Set-Cookie: fr_session=; Max-Age=0` and **the same attributes the cookie was issued with** | `page` | a signed-out browser. **The token is not revoked** — a copy taken off the network stays valid until `exp` or a password change | `P-ACC-05` `P-XCT-06` | **`J-XCT-12`** |
| 8 | any surface, 12 hours later | the customer left the tab open | makes a request | `exp` reached — `iat + SESSION_TTL_SECONDS`, 43200 s | `time` | `401 AUTH_REQUIRED` — *"Your session has ended. Sign in to continue."*, context preserved in `sessionStorage`, and `SCR-XCT-04` takes over | `P-ACC-05` `P-ACC-06` `P-XCT-06` | — |

### What `Secure` being off means for the walk, said at the level the client asked for

`COOKIE_SECURE` has **no default** and is off in the deployed environment. That is not an oversight
and it is not the lazy choice: setting `Secure` without TLS is not the stricter option, it is broken,
because the browser would never send the cookie over HTTP and nobody could stay signed in
(`FR-ADR-069`). So the session cookie travels as plain text across every network between the
customer's device and the load balancer.

**Concretely.** Anyone positioned on that path — the same coffee-shop wifi, a compromised home
router, an intermediate network — can read the `fr_session` cookie off the wire and replay it. They
then hold that customer's session for up to twelve hours. They can read that customer's bookings and
booking references, and because the reference is the only proof of purchase and entry is a human
reading it by eye (`J-ENT-01`, already filed by the entry lane), they can walk into the hall on those
seats.

The document does not paper over this. `P-ACC-05` says *"over plain HTTP the network can take a copy,
which is the largest single reason `OPEN-TLS-01` matters."* `P-ACC-06` takes the **shorter** of two
candidate session lifetimes specifically because every extra hour is an extra hour a copied token can
be replayed, and adopting the stricter option needs no signature. `P-XCT-06` records it as an
accepted weakness in writing, and it is why that environment is never called production and carries
no real customer data. **The mitigations are the honest ones available and none of them makes the
weakness go away.** The one thing that does is `OPEN-TLS-01` closing, and that is `BLOCKED` on the
client sourcing a domain.

### The two findings

**`J-XCT-11` — CSRF is nowhere.** The string `CSRF` does not occur anywhere in
`docs/03 PRD/sections/` or `docs/01 ADR/`. The product carries its session in a cookie the browser
attaches automatically, and `SameSite=Lax` is chosen and justified on a completely different ground —
*"the customer arrives from the seat map on the same site; `Strict` would drop the cookie on any
cross-site return and `None` would require `Secure`"*. As it happens `Lax` does block cross-site
non-`GET` requests and every state change in this product is non-`GET`, so the product is probably
defended. **A reviewer cannot tell that from the document**, and a developer who later adds a `GET`
that changes state, or relaxes `SameSite` for any reason, removes the only defence without ever
reading a sentence that says it was one.

**`J-XCT-12` — sign-out contradicts itself about who may do it.** `P-ACC-05`'s "Who may do it" says
*"Sign-out is `authenticated`"*; its own exception row 6 says *"Sign-out called with no session →
`204`, no body — signing out when not signed in is not an error"*; and `S3.8`, generated from the
endpoint blocks and therefore rank 1, lists `EP-ACC-03 POST /api/auth/logout` under **Public — no
session required**, "anyone". `S1.2.1` case 8 covers exactly this shape: a declared owner that states
a thing two ways is a defect in that row and it stops. The consequence is small but concrete — the
router the endpoint is mounted on decides whether a signed-out customer pressing `Sign out` on a
stale tab gets a `401` or a `204`, and `SCR-XCT-05` specifies that sign-out must not be blockable by
a failed request.

---

# Walk 6 — `P-ACC-04`: registering with an address that is not yours

**Who.** Two people who do not know each other. **R** registers using `victim@example.com`, which is
a real, valid, deliverable address belonging to **V**. R may have mistyped, or may have done it on
purpose; the product cannot tell and does not try.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ACC-01`, register tab | R has no account | registers as `victim@example.com` | API -> Postgres: shape check, trim, unique on `lower(email)`. **No confirmation link is sent and nothing is gated on verification** | `system` | a working account R can book with immediately | `P-ACC-04` `P-XCT-06` | — |
| 2 | `SCR-SEA-01` -> `SCR-PAY-01` | signed in as R | holds three seats and pays | API -> Postgres: `P-PAY-10`, one transaction, `booking.user_id` taken from the session | `system` | a booking and a reference | `P-ACC-04` `P-ACC-09` `P-PAY-10` | — |
| 3 | the confirmation screen | the booking committed | R reads the screen | API -> browser: *"A receipt is on its way to `victim@example.com`"* | `page` | **the typo made visible at the moment it costs something** — the specified mitigation, working exactly as designed | `P-ACC-04` | — |
| 4 | the confirmation screen | R has now seen the wrong address | R looks for a way to correct it | browser -> the route inventory: **58 endpoints, none of which changes an account's email address** | `page` | nothing. The address is unique on `lower(email)` and now taken forever | `P-ACC-04` `P-ACC-09` | **`J-XCT-10`** |
| 5 | V's inbox | V has never heard of FrontRow | a receipt arrives carrying a booking reference | worker -> SES -> V's mail provider | `process` | a valid reference for seats V did not buy, at a venue where **entry is a person reading the reference by eye** | `P-ACC-04` | — |
| 6 | `SCR-ACC-02` request a password reset | V decides to find out what this is | V requests a reset for their own address | API -> queue -> worker -> SES: the reset token goes **to the address, which is V's** | `process` | V can set the password and **take the account over**, including R's bookings and payment history | `P-ACC-04` `P-ACC-09` | **`J-XCT-09`** |
| 7 | `SCR-ACC-04` my bookings, as V | V now controls the account | reads the bookings list | API -> Postgres: `P-ACC-12` scopes to the caller, and the caller is now V | `page` | every reference R ever paid for. R has no route back: the address is not theirs and the reset goes to V | `P-ACC-09` `P-ACC-04` | **`J-XCT-09`** |

### What the row accepts, and what this walk found it does not

`P-ACC-04` is honest and it is `RULED` on an `APPROVED` and immutable record. It accepts one failure
in writing: *"an unverified address is a plausible route to a customer who has paid and cannot
enter"*, reached by a different road to `OPEN-EMAILFAIL-01`. It gives three reasons for not building
the gate — a second interruption in the flow the two-minute target protects, registration made
dependent on SES being healthy, and the observation that a verification gate does not catch the most
common bad address anyway, **which is a valid and deliverable address belonging to somebody else.**

**That third reason names this walk's situation and then stops.** The consequence the row records for
it is only that the receipt goes astray. Steps 6 and 7 are a different and larger consequence, and
they follow from two other rows the document already contains: `P-ACC-07`'s reset sends a
single-use token to the account's address, and `P-ACC-05` says a completed reset increments
`password_version` and **immediately stops every existing session for that account from being
accepted**. So the person who controls the address controls the account, deterministically, by
design, and by the mechanism the product built for the right reason. Registering with an address you
do not control does not merely misdeliver a receipt — it hands the account to whoever owns the
address, at a time of their choosing. Filed as `J-XCT-09`.

**Step 4 is the smaller half and it undercuts the row's own mitigation.** The mitigation is that the
address is shown back so a typo is visible at the moment it costs something. It is visible and
**there is nothing the customer can do about it.** The route inventory in `S3.8` is generated from
the endpoint blocks and lists 58 endpoints; the customer router holds ten, of which seven are `GET`
and three are hold operations. Nothing patches `/api/me`. The customer can register a second account
at the correct address, but the booking belongs to the first (`P-ACC-09`), and the first address is
taken forever by the unique index. Filed as `J-XCT-10`.

---

# Walk 7 — `P-ACC-09`: where a booking could end up without an owner

**Who.** Nobody, for most of this walk. `P-ACC-09` is a constraint and its happy path is every
booking that exists. The walk is therefore a hunt: three ways a booking could end up orphaned, walked
one at a time.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` as a guest | no session | presses the primary action, which reads `Sign in to hold these seats` | browser -> API `EP-HLD-01`: `401 AUTH_REQUIRED` if it reaches the server at all | `system` | **the boundary is at the hold, not at the seat map and not at payment.** Reading availability is browsing; a hold consumes a scarce resource for three minutes | `P-ACC-09` `P-SEA-03` | — |
| 2 | `EP-PAY-01` confirm | signed in | a caller submits a booking naming a different `user_id` | API -> request schema: **no endpoint accepts a `user_id` field** | `system` | rejection. The owner is read from the authorisation dependency's resolved caller. A field that does not exist cannot be forged | `P-ACC-09` `P-PAY-10` | — |
| 3 | **orphan route 1: a seeded booking** | a freshly seeded database | check who owns the 11,003 seeded bookings | seed -> Postgres: `owner = customer[booking_index mod 50]` | `system` | every seeded booking owned by a real seeded customer row, 220 or 221 each, so no seeded account has an empty bookings list. **No orphan here** | `P-ACC-09` `P-XCT-30` | — |
| 4 | **orphan route 2: a role change** | a customer with bookings is made a manager by `P-ADM-17` | the next request resolves the new role | API -> Postgres: the role is read from the row on every request, never from a claim | `system` | the bookings still belong to the same user row. `P-ACC-09` permits it in terms — the manager restriction is on privileged writes, not on being a customer. **No orphan** | `P-ACC-09` `P-ACC-05` | *(prior: `J-MGR-09`)* |
| 5 | **orphan route 3: a deleted account** | a user row is removed | `P-ACC-05` exception 5 fires on the next request from that session | API -> Postgres: *"Cookie valid, the user row does not exist"* → `401 AUTH_REQUIRED` | `system` | a specified state in which a user row that a booking references **is gone** | `P-ACC-05` `P-ACC-09` | **`J-XCT-05`** |
| 6 | the Phase 2 migration | a developer writes the `booking` table | chooses the referential action for `booking.user_id` | migration -> Postgres: `ON DELETE` is **`RESTRICT`, `CASCADE` or `SET NULL`, and no row says which** | `system` | a guess. `SET NULL` is impossible against a non-null column; `CASCADE` destroys paid bookings and every takings figure computed from them; `RESTRICT` makes `P-ACC-05` exception 5 unreachable | `P-ACC-09` `P-ACC-05` | **`J-XCT-05`** |

### What enforces it, and the one place it is not enforced

**Enforcement is structural and it is good.** The owner is never in the request — `P-ACC-09` states
that `booking.user_id` is read from the authorisation dependency's resolved caller and that no
endpoint accepts a `user_id` field, so there is no forgery surface to defend. There is no anonymous
order, no guest checkout and no placeholder user. There is no separate delivery-email field, because
a second address would be a second identity path for the customer's only proof of purchase. Two of
the three orphan routes this walk hunted are closed, and step 3 in particular was checked rather than
assumed: the seed's own rule assigns every one of its 11,003 bookings to a seeded customer.

**The third is open and it is a genuine `blocks-code` gap.** Two rows disagree about whether a user
row can disappear. `P-ACC-09` says the foreign key is non-null and the route inventory confirms no
endpoint deletes an account. `P-ACC-05` exception 5 specifies the behaviour when *"the user row does
not exist"* — a state the first row says cannot occur, and which is nevertheless reachable, because
`J-ADM-14` (already filed by the admin lane) establishes that the only route to creating an admin
account is a direct database action outside the router. Whatever creates a row by hand can remove
one. **No row anywhere states the referential action**, and the three candidates produce three
different products: one where deleting a user is refused, one where it silently destroys paid
bookings and every dashboard figure derived from them, and one the column type forbids. Filed as
`J-XCT-05`.

---

# Walk 8 — `P-HLD-08`: giving seats back

**Who.** A customer holding four seats — `J1`, `J2`, `J3`, `J4` — in Screen 6, with
`expires_at = 2026-08-14T14:05:37.412Z`. The customer lane reported that none of its ten walks
required a release, so this is the first walk through it.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-SEA-01` | four seats held, all rendering `held_by_me` with a tick and a 2px border | taps `J4` — the only state in the map that is tappable to give a seat back | browser -> API `EP-HLD-03` -> Redis: the compare-and-delete Lua script against `lock:seat:41:{J4}` with the hold's token | `system` | three seats, `expires_at` **unchanged**. Giving a seat back does not buy more time on the others | `P-HLD-08` | — |
| 2 | `SCR-SEA-01` | three seats held | the API finishes the release | API -> Redis: `DEL cache:seatmap:41`, **after** the lock release and never before | `system` | the seat free for everyone else within about three seconds instead of the cache's ten-second TTL | `P-HLD-08` | — |
| 3 | another customer's map | they were watching `J4` | their 3-second poll returns | API -> Redis cache miss -> Postgres rebuild | `system` | `J4` repaints `available`, with the changed-seat ring so the change is legible rather than a silent repaint | `P-HLD-08` `P-SEA-03` | — |
| 4 | `SCR-SEA-01` | three seats held | presses `Give up these seats`, the secondary control on the price summary | browser -> API `EP-HLD-04` `DELETE /api/holds/{hold_token}` -> Redis | `system` | `204`. **And no step list exists for this path** — no `DEL cache:seatmap`, and no removal of the token from `holds:user:{user_id}:showtime:{showtime_id}` | `P-HLD-08` | **`J-XCT-04`** |
| 5 | `SCR-SEA-01` | the whole hold is gone | the customer changes their mind and tries to take ten seats | API -> Redis: `P-HLD-04`'s cap counts from `holds:user:{user_id}:showtime:{showtime_id}`, which still names a hold that no longer exists | `system` | refused, until the 180 seconds elapse — **the exact failure `P-HLD-08` step 8 exists to prevent, reproduced on the other endpoint** | `P-HLD-08` | **`J-XCT-04`** |
| 6 | `SCR-PAY-01` | a hold is live and a confirm is in flight | a release for the same hold lands **first** | API -> Redis: compare-and-delete removes the key; the confirm's step-2 re-validation then finds nothing | `system` | `409 HOLD_EXPIRED` before the showtime row is locked and before any payment. **Nothing is charged**, and the customer is told exactly that | `P-HLD-08` `P-PAY-10` `P-HLD-14` | — |
| 7 | `SCR-PAY-01` | the booking has already committed | the same release lands **after** | API -> Redis: the compare-and-delete matches no live token and deletes nothing | `system` | the confirmation and its reference. A Redis operation cannot un-sell a committed `booking_seat` row | `P-HLD-08` `P-PAY-11` | — |
| 8 | `SCR-SEA-01` | the hold expired on its own 40 seconds ago; the client still paints `held_by_me` until the next poll | taps `J2` to give it back | API -> Redis: the key is gone | `time` | `409 HOLD_EXPIRED` — *"The hold on your seats has ended and they have been released. You have not been charged. Choose them again if they are still free."* | `P-HLD-08` `P-HLD-14` | — |

### The race is settled by ordering and it is settled correctly

Steps 6 and 7 are the part of this row worth reading twice. There is **no "confirm in flight" flag and
no error code refusing the release**, and the row says why in the negative: such a flag would be new
durable state that something has to set, clear, and clear again when the confirming process died
between setting it and committing, and `FR-ADR-025` keeps hold state out of PostgreSQL on purpose. A
third error code was proposed for this on lane E2 and was **removed, name and all**, with the reason
recorded. There are exactly two orderings, both safe, and the customer is told the truth in each. No
defect.

### Where the whole-hold release stops being specified

`P-HLD-08` gives the per-seat release eight numbered steps, and two of them are load-bearing and are
justified at length: **step 6**, the `DEL cache:seatmap:{showtime_id}` that `P-BRW-12` requires after
a release exactly as after a hold, and **step 8**, removing the token from
`holds:user:{user_id}:showtime:{showtime_id}` when the hold reaches zero seats — because *"leaving the
token in that set would keep the customer's cap consumed by a hold that no longer exists."*

**The whole-hold release gets one sentence.** *"Releasing the whole hold in one action is the
secondary control on the price summary."* `EP-HLD-04`'s block describes its `204` as *"every key in
the hold was released with the compare-and-delete script and the hold record was deleted"* — no cache
delete, and no mention of the cap index. Under `S1.2.1` case 7 an ordered step list is authoritative
on ordering and never on completeness, so a declared owner elsewhere adds its write; but here there
is **no list at all** for `EP-HLD-04`, and a developer building it from the endpoint block writes
neither. The two consequences are the ones `P-HLD-08` already wrote down for the per-seat path: a
seat-map that shows the released seats as held for up to ten seconds instead of three, and a customer
who gave every seat back and cannot take ten again until the TTL elapses — told, if they try, that
the seats were taken by another customer when the other customer is themselves. That last symptom is
`J-CUS-10`'s and `OPEN-HOLDRECOVER-01`'s territory, reached here by a different road; **the missing
step list is new** and is filed as `J-XCT-04`.

### One stale cross-reference, recorded because it is cheap and checkable

`S1.2.1` case 7 cites `P-HLD-08` as an example of a step list that *"never mentions the seat-map cache
`DEL` that `P-BRW-12` requires after both."* `P-HLD-08` step 6 now carries it. The rule is right and
its worked example has been overtaken by the fix. Filed as `J-XCT-17`, cosmetic.

---

# Walk 9 — `P-PAY-12`: a customer who paid and wants their money back

**Who.** A customer who booked three Recliner seats for Friday, cannot attend, and goes looking for a
way to undo it.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ACC-04` my bookings | signed in, the booking is upcoming | opens the booking | browser -> API `EP-ACC-08` -> Postgres | `page` | the reference, the seats, the total. **No cancel control, no cancel link, no "cancel" field, and no space left for one** | `P-PAY-12` `P-ACC-09` | — |
| 2 | `SCR-ACC-05` / `SCR-TKT-01` one booking | the booking is open | looks for anything that reverses it | screen spec -> what must not render: a cancel control, a refund control, a change-seats control | `page` | nothing. `FR-ADR-013` makes a confirmed booking final and a cancellation control on this screen is a defect, not a feature | `P-PAY-12` | — |
| 3 | any URL the customer can invent | determined | types `/api/bookings/{ref}/cancel` | browser -> API: **no such route is registered** | `system` | FastAPI's own `404`. Nothing this document specifies, because there is no interface that produces the request | `P-PAY-12` | — |
| 4 | `SCR-XCT-05` footer, on every screen | the customer looks for someone to ask | reads the only line on the subject anywhere in the product | shell -> footer: *"Demonstration environment. Payments are simulated and no card details are ever taken."* | `page` | **no About link, no Contact link, no footer links at all**, and no support desk — the client is the sole operator | `P-PAY-12` | **`J-XCT-15`** |
| 5 | the admin's side of the same question | the customer has reached the operator by some route outside the product | the admin looks for a capability | route inventory -> 30 admin endpoints: **no cancellation, no refund, and no showtime withdrawal** | `system` | nothing to do. The payment state machine has `pending`, `authorized`, `captured` and `failed` and **no `refunded` state exists** | `P-PAY-12` | — |
| 6 | the database, conceptually | the customer asks what their booking's status even is | reads what v1 exposes | Postgres -> API: `booking.status` and `booking.cancelled_at` exist and **no v1 endpoint returns either** | `system` | `status` written once at confirmation, `cancelled_at` null for every row v1 ever creates — kept because `SRC-001 §6.6` forbids designing in a way that blocks a later ask | `P-PAY-12` | — |

### Exactly where they end up, and what they are told

**They end up nowhere, and they are told nothing.** Not a refusal, not a policy sentence, not a
contact route. Every surface in the product is specified to render **no** cancellation control, and
that is correct and deliberate — `SRC-001 §5.4.3` is withdrawn by erratum `E-2`, `SRC-003
OPEN-CANCEL-01` rules out customer cancellation, `OPEN-CANCEL-02` rules out refunds, and a bookings
list with a cancel control would be a specification derived from a withdrawn clause. **What no
surface does is say so.** The absence is specified as an absence of controls and never as a statement
to a person, and the product has no About page, no Contact page, no footer links and no support desk
by explicit decision (`SCR-XCT-05`: *"inventing an 'About' or a 'Contact' would be inventing product
content the client will see"*). Filed as `J-XCT-15`, `PRD-fix` — the policy is ruled, so writing one
sentence of copy for it is not a money decision and needs no client ruling.

### What the documents do and do not say — recorded without inventing a policy

**What is said, verbatim in `P-PAY-12`:** *"Recorded, not challenged: a customer who cannot attend
loses their money. That is the ruled behaviour for a demonstration project and it would need
revisiting before a real customer ever booked."*

**What is deliberately not said, and this walk does not fill it in:** what a customer would be told if
a showtime were ever withdrawn with bookings on it. `P-PAY-12` names that as the one route by which a
booking could still end up cancelled, states that the capability does not exist in v1 so the case
cannot arise, and then stops — no withdrawal endpoint, no screen, no refund behaviour and **no
sentence about what a customer would be told**, because `OPEN-SHOWCANCEL-01` is reserved. `J-ADM-12`
(already filed by the admin lane) reaches the same hole from the admin's side: no combination of
existing capabilities stops one showtime selling. **Neither this walk nor that one may write the
missing sentence**, and this document does not.

**One thing worth stating plainly rather than dramatising.** In v1 the customer has not actually paid
anything. `PAYMENT_PROVIDER` accepts only `simulated`, any other value crashes the process at boot,
and the checkout slab says so before anything else on the screen is read: *"No real payment is taken.
This is a demonstration system. Nothing is charged and no card details are collected."* So
`P-PAY-12`'s recorded consequence — *"a customer who cannot attend loses their money"* — describes an
environment the specification currently forbids. That is not a contradiction to file: the row is
recording the shape of the decision for the day it stops being simulated, and it says so in its own
next clause. It is recorded here because a reader walking this path deserves to know that the
dramatic reading of step 5 is not the true one today, and that the true one is `J-XCT-15`: the
product is silent, and silence is what a customer meets.

---

## Prior defects re-encountered and deliberately not re-filed

| Walk · step | What the walk hit | Already filed as |
|---|---|---|
| 5 · the plain-HTTP consequence | a replayed session yields booking references, and entry is a human reading a reference with no way to verify it | `J-ENT-01` (`already-open:OPEN-DOORVERIFY-01`) |
| 8 · step 5 | a customer whose cap is consumed by a hold that no longer exists is told the seats went to another customer when that customer is themselves | `J-CUS-10`, and `OPEN-HOLDRECOVER-01` |
| 7 · step 4 | a manager who books in a hall they report on | `J-MGR-09` (`already-open:OPEN-MGRBOOK-01`) |

## Why the zero-defect check does not apply, and what was re-walked anyway

This lane filed 17 defects, so the brief's zero-defect rule is not engaged. Three walks were
nevertheless re-entered from a second starting state, and two of the three top findings came only
from the re-entry:

- **Walk 1** was walked first as the happy race — A wins, B is refused — which found nothing. It was
  re-entered from the build gate rather than from the customer, and steps 7 to 10 produced
  `J-XCT-01`, the most consequential finding in this document.
- **Walk 6** was walked first as a mistyped address, which produced only `J-XCT-10`. It was
  re-entered from the address's real owner rather than from the registrant, which produced
  `J-XCT-09`.
- **Walk 4** was walked first as the keyboard reader, then again as the screen-reader reader; step 7
  (`J-XCT-08`) is only visible on the second pass, because the failure is that a string is never
  announced.

## What this lane could not do

- **Nothing was executed.** No application code exists. Every seam behaviour is read from the
  specification, and every AWS statement is reasoned, not observed.
- **`E8_crosscutting.md` was still not read end to end.** Eight of its thirty-two P-rows were read in
  full — the five this lane was assigned plus `P-XCT-02`, `P-XCT-09` and the parts of `P-XCT-30` the
  walks needed — along with `S7.1`, `S7.5`, `S7.9`, `S7.13` and `S7.18`. **Twenty-four `P-XCT` rows
  and roughly two thirds of `S7` were not read.** `JOURNEY_INDEX.md` names that population as the
  most likely place an unfound defect is hiding, and this lane narrowed it rather than closing it.
- **Four of the nine rows were walked partly from a neighbouring epic's rows.** Walk 1 leans on
  `P-PAY-10`/`P-PAY-11` and `P-HLD-13`, Walk 8 on `EP-HLD-04`'s block, Walk 6 on `P-ACC-07`'s
  behaviour as described by `P-XCT-32` and `P-ACC-04` rather than from `P-ACC-07` itself, and Walk 9
  on `SCR-ACC-05`'s prohibitions as restated in `E5`. Where a claim rests on a restatement rather
  than on the owning row, it is a claim about a restatement.
- **Every width figure in Walk 3 divides by an `ASSUMED` denominator** — `OPEN-SCALE-02`. The
  assumption is flagged at each figure rather than once.
- **No accessibility testing was performed and none is claimed.** Walk 4 reads the specification
  against the criteria; `P-XCT-24` forbids a conformance claim for exactly this reason, and this
  document makes none.
