# 11 Journeys — index

```
Produced by ....... GOAL_06 (goals/GOAL_06_journeys.txt)
Written ........... 2026-08-22
Derived from ...... docs/03 PRD/sections/ (the section files, not the generated assembly)
                    SRC-001 + §E · SRC-002 + §E · SRC-003 · docs/01 ADR/ · docs/02 BRD/
                    docs/05 B DesignSystem/ (for the seat-map and accessibility walks)
Authority ......... CONSTITUTION.md Art II.1. A journey never outranks the PRD; where a
                    journey and the PRD disagree, the journey is reporting a defect in the
                    PRD and DEFECTS_FOUND.tsv is where it is filed.
Verify ............ py tools/verify_goal06.py           re-derives every figure below
                    py tools/verify_goal06.py --selftest red-proofs the checks themselves
```

> **A journey is a walk, not a feature list.** Its job is to find what a per-screen specification
> cannot see: the seams between screens. On this product the seams are where the money is — a hold
> expiring while the customer is on the payment screen is not a bug in the seat map and not a bug in
> checkout. It lives between them.

> **Nothing here was observed.** No application code exists in this repository yet. Every statement
> in every walk is read from the specification, and every claim about AWS behaviour is **reasoned,
> not observed**, and is labelled that way at each point of use. No accessibility testing was
> performed and none is claimed.

---

## How this was produced

**Five persona lanes walked the product independently and could not see each other's work.** Each
read the PRD from its own persona's entry point, filed its own defects, and returned before any merge
happened. That isolation is the deliverable, not a scheduling convenience: `CONSTITUTION.md`
Art VII.7 says the writer never verifies its own work, and one author walking five personas in
sequence grades every walk with the context that wrote the previous one.

**It paid on the first merge.** Three lanes that could not see each other converged on the same hole
— see *The convergence*. A single writer would have had to notice it three times, and would more
likely have rationalised it once.

**A sixth lane then closed a measured coverage gap.** The five persona lanes touched 140 of 163
P-rows; nine of the 23 untouched rows were walkable and simply had no persona standing in them,
including the seat guarantee itself. The cross-cutting lane (`J-XCT`) walked those nine.
**It was deliberately not blind** — it read this index and the defect register first, so it closed
the gap without re-filing what was already found, and it declined to re-file three defects it
re-encountered.

**Every lane re-entered its own walks from awkward starting states** rather than walking the happy
path once, and the record says that is where the value was:

- the customer lane reports a happy-path pass alone would have found **four of its twelve**;
- the cross-cutting lane walked the seat-guarantee race first as a happy race and **found nothing**,
  then re-entered it from the build gate and produced `J-XCT-01`, the most serious defect in this
  document.

---

## The documents

| File | Lane(s) | Lines | Steps | Defects |
|---|---|---|---|---|
| `CUSTOMER_JOURNEY.md` | customer (`J-CUS`) + receipt and entry (`J-ENT`) | 509 | 93 | 24 |
| `CROSSCUTTING_JOURNEY.md` | cross-cutting floors (`J-XCT`) | 648 | 71 | 17 |
| `ADMIN_JOURNEY.md` | admin (`J-ADM`) | 397 | 53 | 16 |
| `MANAGER_JOURNEY.md` | manager (`J-MGR`) | 269 | 45 | 14 |
| `GUEST_JOURNEY.md` | guest (`J-GST`) | 209 | 51 | 10 |
| `DEFECTS_FOUND.tsv` | all six, merged, worst severity first | — | — | **81** |
| | | | **313** | |

**There is no `STAFF_JOURNEY.md`.** `SRC-003` removed the cinema-staff role and the door scanner, so
the receipt-and-entry walk lives inside `CUSTOMER_JOURNEY.md` as the `RECEIPT_AND_ENTRY` section. It
was written by a separate lane that had not seen the customer walks, and its defect ids are `J-ENT`.

### Seams crossed, across all 313 steps

| Seam type | Steps |
|---|---|
| `system` — to Redis, Postgres, S3, the queue, SES, the simulated payment provider | 188 |
| `page` — one surface to another | 73 |
| `time` — a TTL, a sales cut-off, a display window, a token expiring | 38 |
| `process` — API to worker, into asynchronous work | 13 |
| `page` then `system` in one action — recorded as the hybrid it is rather than filed under whichever half read better | 1 |

**Zero steps carry an empty seam or a seam of "none",** checked mechanically rather than asserted.
Two lanes returned `process` = 0 and both explained it rather than leaving it to be noticed: a guest
never reaches asynchronous work, because everything behind the hold requires an account; and nothing
an admin does is asynchronous, because every admin write is one request and one transaction.

---

## P-row coverage — 150 of 163 touched, 13 untouched

Both counts are computed from the P-rows column of the step tables by script, so the figure measures
these documents rather than a companion file that could drift from them. Re-derive with
`py tools/verify_goal06.py`.

| | |
|---|---|
| P-rows in `docs/03 PRD/sections/` | **163** |
| touched by at least one journey step | **150** |
| **untouched** | **13** |

Per document, before de-duplication: customer 63 · guest 48 · admin 33 · manager 21 · cross-cutting 18.

### The 13 untouched rows, and why

**All thirteen are build, process and infrastructure constraints** — true statements about how the
system is made, with no user standing anywhere in them. A journey cannot walk them, and one claiming
to would be padding.

| Row | Subject |
|---|---|
| `P-XCT-10` | `/health/live` and `/health/ready` behave differently on purpose |
| `P-XCT-13` | expose `/metrics`, and say that nothing scrapes it |
| `P-XCT-16` | read secrets from SSM through the task definition |
| `P-XCT-19` | migrations run as an explicit step, never on boot |
| `P-XCT-20` | back up the database and rehearse the restore |
| `P-XCT-21` | fit three processes inside roughly 1 GB |
| `P-XCT-22` | introduce no scheduled job of any kind |
| `P-XCT-23` | add no service outside the approved list |
| `P-XCT-26` | write no Zone C artefact; give a specification instead |
| `P-XCT-27` | deliver in eight phases |
| `P-XCT-28` | escalate a reserved question, never invent an answer |
| `P-XCT-29` | never call the deployed environment production |
| `P-XCT-31` | contain no AI feature; send no customer data to a model |

**The nine walkable rows that the five persona lanes missed are now walked** — `P-XCT-01`,
`P-XCT-06`, `P-XCT-24`, `P-XCT-25`, `P-XCT-32`, `P-ACC-04`, `P-ACC-09`, `P-HLD-08` and `P-PAY-12`.
`P-HLD-13` was also picked up on the way, which is how `J-XCT-01` was found.

---

## Defects — 81 filed

`DEFECTS_FOUND.tsv` holds one row per defect, sorted worst severity first. Every row names the PRD
section it lands against, the anchor it attaches to, the seam where it bites, and its disposition.

| Severity | Count | Meaning |
|---|---|---|
| `blocks-code` | **25** | a developer cannot write the code without guessing |
| `ambiguous` | 49 | the document permits two readings |
| `cosmetic` | 7 | |

| Kind | Count |
|---|---|
| `gap` — the document is silent | 36 |
| `contradiction` — two parts of the document disagree | 32 |
| `unhandled-edge` | 13 |

| Disposition | Count |
|---|---|
| `PRD-fix` — fixable without a client ruling | 65 |
| `already-open` — the question is already an Article X row | 16 |
| — of which filed by this goal as `X.0e` | 3 |

**Thirty-two contradictions is the number to look at.** A gap is the document being silent; a
contradiction is the document giving a developer two different instructions and no way to choose.
All 32 are internal to the PRD and **none needs a client ruling to resolve.**

### ⛔ `J-XCT-01` — the never-waivable concurrency proof, as specified, cannot work

**This is the most serious finding in this document and it lands on the one gate this project calls
never waivable.**

`CONSTITUTION.md` and `SRC-002 §9.1` require `scripts/stress_seats.py` to fire **50 simultaneous
requests for one seat and assert exactly one succeeds** — then to **drop the unique constraint on
purpose, watch the script produce more than one winner, restore it, and verify the restore.** A gate
nobody has watched fail is decoration, so the drill is the point.

**`P-HLD-13` and `P-PAY-11` both fix that gate at the *hold* endpoint** — where the unique constraint
on `(showtime_id, seat_id)` is never reached, because the Redis lock decides the winner. Meanwhile
`P-XCT-01` attributes the 49 refusals **to the constraint**, and requires the red-proof drill to
observe more than one winner once it is dropped.

**Dropping the constraint changes nothing at the hold endpoint. Redis still grants exactly one lock.**
The drill therefore produces one winner, and both rows classify that outcome as a **void proof and a
stop-the-line finding** — so *the specified gate reports failure against a correct implementation.*

The two-system guarantee itself is not in doubt: a Redis lock provides the hold, and the unique
constraint plus `SELECT ... FOR UPDATE` provides the truth. What is wrong is **which endpoint the
proof fires at.** This must be settled before Phase 4, which is where the gate is built.

### The convergence — what independent lanes bought

Three lanes, walking from opposite directions and blind to each other, reached the same conclusion:
**the booking path never checks whether a film is still inside its display window.**

| Defect | Lane | Finding |
|---|---|---|
| `J-GST-02` | guest | `P-BRW-01` says the visibility predicate runs on every such query; `EP-BRW-05` says it does not apply the gates |
| `J-GST-03` | guest | `SCR-BRW-03` publishes no state for a film that has left its window, and `E2` never checks it, so the hold proceeds |
| `J-ADM-06` | admin | the seat-hold path never consults the display window — verified by search: the phrase does not occur in `E2` |
| `J-ADM-12` | admin | no combination of existing admin capabilities stops one showtime selling; unpublishing the film and withdrawing the hall both state they change nothing |

`OPEN-BRWVIS-01` is filed and asks the client what the *policy* should be. These four findings are a
different thing and **do not wait on it**: whatever is ruled, the booking surface applies no gate at
all today, and no admin action can stop a showtime selling.

### The findings that most threaten the win condition

- **`J-XCT-01`** — the concurrency proof fires at the wrong endpoint. See above.
- **`J-ENT-01`** — `P-TKT-08` tells the person at the door to compare the reference *"against the
  day's bookings by whatever means the venue uses"*, and **no endpoint, screen or export returns a
  showtime's bookings or any booking reference to anyone but the booking's own signed-in owner.** The
  emailed reference is the customer's only proof of purchase and their only way in, and it is
  unverifiable at the only place it is used. Filed as `OPEN-DOORVERIFY-01`.
- **`J-XCT-03`** — `P-XCT-32` and `P-XCT-30` assign the deployed seed run to the client, and **nothing
  in `docs/30 Deployment/` says how to run it or how `SEED_DEFAULT_PASSWORD` reaches that
  environment.** `S7.9` makes it seed-only, so it cannot ride in on the task definition's SSM
  secrets. **Phase 2 and Phase 4 both stop here, and the AWS dependency was never announced.**
- **`J-CUS-04`** — the simulated payment failure is keyed on an `Idempotency-Key` prefix, the key is
  generated once per hold, and the copy invites a retry. Every retry fails identically, so
  **`fail → retry → succeed` is unreachable from the product.**
- **`J-XCT-02`** — `P-XCT-01`'s exception fires on the unique constraint at **confirm** and publishes
  `P-HLD-14`'s **at-hold** sentence. A customer who held seats, paid, and had the transaction rolled
  back in full is told *"No seats were held. Your other choices are still selected."*
- **`J-XCT-05`** — no row states `booking.user_id`'s `ON DELETE` action. `CASCADE` **silently destroys
  paid bookings** and every takings figure derived from them.
- **`J-ENT-04`** — the queue send runs inside the confirm request with **no timeout specified
  anywhere**; `S7.9` gives Redis, Postgres and bcrypt one.
- **`J-ENT-03`** — a receipt is marked `sent` on SES *acceptance*; bounces publish to SNS and nothing
  subscribes, so **a bounce reads as a delivery** — hiding `OPEN-EMAILFAIL-01` in exactly the case it
  was filed for.
- **`J-CUS-01`** — a returning customer booking the same showtime twice in one tab is redirected to
  their first booking's confirmation page and can never reach checkout for the second hold.
- **`J-XCT-06`** — nothing ever scrolls the seat-map container programmatically. On the 375px design
  target roughly half a 20-column row is off-screen, so **arrow-key focus lands on invisible seats**
  and the pinned row gutter overlays the leftmost cells. WCAG 2.2 SC 2.4.11 at the adopted AA level,
  recorded as a deviation nowhere.
- **`J-MGR-09`** — `P-ADM-17` states flatly that a manager writes nothing, ever. The **generated**
  `contract.json` admits `manager` on five non-`GET` endpoints. The sentence is false against the
  product's own contract; the underlying question is already `OPEN-MGRBOOK-01`.

### One check that passed, recorded because a negative result is evidence

**The pricing arithmetic is sound.** The rounding rule is stated as integer half-up, it is
byte-identical in all five places it appears, and the worked example is **not** degenerate — the
Recliner line lands on exactly `33332.5`, the one value where half-up and half-even visibly disagree,
and the rule is exercised in the opposite direction elsewhere at base 24999. This was briefed to the
lane as a likely `blocks-code` risk and it was not one. The single pricing defect found is that an
endpoint block silently drops the P-row's overflow ceiling (`J-ADM-07`).

---

## The fix wave — 2026-08-22

**The journeys file defects; they do not fix them** (`GOAL_06` guardrail). The 65 defects marked
`PRD-fix` were repaired in a separate wave by nine agents, one per PRD section file, with exclusive
file ownership. Outcomes are in `DEFECTS_RESOLUTION.tsv`: **58 `fixed`, 8 `partially-fixed`, 16
`open-article-x`** — the last being the questions only the client may answer.

**Cross-file contradictions were not fixed by the two agents holding the two halves.** Each defect
had exactly one owner, who fixed its own file and emitted a patch record for the other side; those 15
records were applied centrally afterwards. The failure this avoids is specific: two agents each
editing their own side to match the other **swap the error instead of resolving it**.

It was not theoretical. One record was **refused on application** because its anchor had drifted —
E2 rewrote the passage while E3 was reading it — and E2's rewrite had kept the exact sentence the
patch existed to change, so the root cause of `J-CUS-04` would have survived the wave that was
fixing it. It was reconciled by hand instead. A second collision was caught by an agent re-reading
before finalising: E5's draft would have collapsed a two-key design E2 had just introduced.

**Four questions were reached that no agent could answer without deciding something reserved**, and
each stopped rather than decide. They are filed as `CONSTITUTION.md` Article X.0f — `OPEN-REFCHAR-01`,
`OPEN-SEATALPHA-01`, `OPEN-BULKBUY-01` and `OPEN-EMAILOWN-01`. **Two of them expire**: the reference
alphabet at the first confirmed booking (Phase 4), the row-label alphabet at the first showtime
(Phase 2).

---

## What this goal could not do

- **Nothing was executed.** There is no application code. Every seam behaviour is read from the
  specification.
- **`E8_crosscutting.md` was never read end to end**, by any lane. The cross-cutting lane read 8 of
  its 32 `P-XCT` rows in full plus five `S7` subsections; **24 rows and roughly two thirds of `S7`
  remain unread.** That population is the likeliest hiding place for an unfound defect. The sixth
  lane narrowed this gap; it did not close it, and it says so.
- **Several walks cite a neighbouring epic's restatement rather than its owning row.** Each lane names
  its own instances in its document.
- **Every occupancy and seat-map width figure divides by an assumed denominator.** Hall sizes are
  `ASSUMED`, not `RULED` (`OPEN-SCALE-02`), flagged at each point of use rather than once.
- **No accessibility testing was performed.** Walk 4 of the cross-cutting journey reads the
  specification and the design system against WCAG 2.2 AA; it does not measure a running product.

---

## Files

| File | What it is |
|---|---|
| `CUSTOMER_JOURNEY.md` | the customer's walks, plus `RECEIPT_AND_ENTRY` from the independent entry lane |
| `CROSSCUTTING_JOURNEY.md` | the nine cross-cutting floors no persona stood in, including the seat guarantee |
| `GUEST_JOURNEY.md` | the person with no account, including the exclusions walked as absence |
| `MANAGER_JOURNEY.md` | the read-only, screen-scoped manager |
| `ADMIN_JOURNEY.md` | the admin, who performs every privileged write in the product |
| `DEFECTS_FOUND.tsv` | all 81 defects, worst severity first, one row each |
| `DEFECTS_RESOLUTION.tsv` | what happened to each of the 81 — one row each, cross-checked against the register in both directions |
