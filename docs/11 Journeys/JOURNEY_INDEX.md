# 11 Journeys — index

```
Produced by ....... GOAL_06 (goals/GOAL_06_journeys.txt)
Written ........... 2026-08-22
Derived from ...... docs/03 PRD/sections/ (the section files, not the generated assembly)
                    SRC-001 + §E · SRC-002 + §E · SRC-003 · docs/01 ADR/ · docs/02 BRD/
Authority ......... CONSTITUTION.md Art II.1. A journey never outranks the PRD; where a
                    journey and the PRD disagree, the journey is reporting a defect in the
                    PRD and DEFECTS_FOUND.tsv is where it is filed.
```

> **A journey is a walk, not a feature list.** Its job is to find what a per-screen specification
> cannot see: the seams between screens. On this product the seams are where the money is — a hold
> expiring while the customer is on the payment screen is not a bug in the seat map and not a bug in
> checkout. It lives between them.

> **Nothing here was observed.** No application code exists in this repository yet. Every statement
> in every walk is read from the specification, and every claim about AWS behaviour is **reasoned,
> not observed**, and is labelled that way at each point of use.

---

## How this was produced, and why it was produced that way

**Five lanes walked the product independently and could not see each other's work.** Each read the
PRD from its own persona's entry point, filed its own defects, and returned before any merge
happened. That isolation is the deliverable, not a scheduling convenience: `CONSTITUTION.md`
Art VII.7 says the writer never verifies its own work, and a single author walking five personas in
sequence grades every walk with the context that wrote the previous one.

**It paid for itself on the first merge.** Three lanes that could not see each other converged on the
same hole — see *The convergence* below. A single writer would have had to notice it three times,
and would more likely have rationalised it once.

**Each lane also re-entered its own walks from awkward starting states** rather than walking the
happy path once. The customer lane reports that a happy-path pass alone would have found **four of
its twelve** defects; three of its top five came only from re-entry — a returning customer rather
than a first visit, the retry rather than the failure, coming back rather than leaving.

---

## The documents

| File | Lane(s) | Lines | Steps | Defects |
|---|---|---|---|---|
| `CUSTOMER_JOURNEY.md` | customer (`J-CUS`) + receipt and entry (`J-ENT`) | 510 | 93 | 24 |
| `ADMIN_JOURNEY.md` | admin (`J-ADM`) | 398 | 53 | 16 |
| `MANAGER_JOURNEY.md` | manager (`J-MGR`) | 270 | 45 | 14 |
| `GUEST_JOURNEY.md` | guest (`J-GST`) | 210 | 51 | 10 |
| `DEFECTS_FOUND.tsv` | all five, merged, worst severity first | — | — | **64** |
| | | | **242** | |

**There is no `STAFF_JOURNEY.md`.** `SRC-003` removed the cinema-staff role and the door scanner, so
the receipt-and-entry walk lives inside `CUSTOMER_JOURNEY.md` as the `RECEIPT_AND_ENTRY` section. It
was written by a separate lane that had not seen the customer walks, and its defect ids are `J-ENT`.

### Seams crossed, across all 242 steps

| Seam type | Steps |
|---|---|
| `system` — to Redis, Postgres, S3, the queue, SES, the simulated payment provider | 146 |
| `page` — one surface to another | 51 |
| `time` — a TTL, a sales cut-off, a display window, a token expiring | 35 |
| `process` — API to worker, into asynchronous work | 9 |
| `page` then `system` in one action — one step, recorded as the hybrid it is rather than filed under whichever half read better | 1 |

**Zero steps carry an empty seam or a seam of "none",** and that is checked mechanically rather than
asserted. Two lanes returned `process` = 0 and both explained it rather than leaving it to be
noticed: a guest never reaches asynchronous work, because everything behind the hold requires an
account; and nothing an admin does is asynchronous, because every admin write is one request and one
transaction.

---

## P-row coverage — 140 of 163 touched, 23 untouched

Both counts are computed from the step tables by script, not counted by hand. Re-derive every
figure in this document with `py tools/verify_goal06.py`; red-proof the checks themselves with
`py tools/verify_goal06.py --selftest`. It reads the committed documents only - the lane-scoped
working files the five agents wrote are not inputs, so nothing here rests on a scratch directory.

| | |
|---|---|
| P-rows in `docs/03 PRD/sections/` | **163** |
| touched by at least one journey step | **140** |
| **untouched** | **23** |

Per lane, before de-duplication: customer 51 · guest 48 · admin 33 · manager 21 · entry 20.

### The 23 untouched rows, and why

**Fourteen are not walkable by any persona.** They are build, process and infrastructure constraints
— true statements about how the system is made, with no user standing anywhere in them. A journey
cannot walk them and a journey that claimed to would be padding.

| Row | Subject |
|---|---|
| `P-HLD-13` | prove the guarantee with fifty simultaneous requests — a build gate |
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

**Nine were walkable and were not walked. That is a coverage gap in this goal, not a justification.**
Stated worst first, because three of them are load-bearing:

| Row | Subject | Why it matters that no walk touched it |
|---|---|---|
| `P-XCT-01` | **enforce the seat guarantee in two systems and never waive the database half** | the product's central invariant. The customer lane walked the hold and the confirm and cited `P-HLD` and `P-PAY` rows, but no walk cites the row that states the guarantee itself. |
| `P-XCT-32` | **give every seeded account a password it can actually sign in with** | already known-and-unbuilt, and it stops Phase 2 *and* Phase 4. No persona walk starts from "cannot log in at all", so no lane reached it. |
| `P-XCT-25` | **render the largest hall's seat map on a 375-pixel phone** | the seat map is the product's hardest surface and a phone is where a customer uses it. A genuine journey concern that no lane was pointed at. |
| `P-XCT-24` | WCAG 2.2 AA as a target, with the one deviation recorded | accessibility of the booking path, unwalked |
| `P-XCT-06` | credential storage and the session cookie | walked in effect by the login steps, but not cited |
| `P-ACC-04` | no email-verification gate in v1 — an accepted weakness | the guest lane was scoped to registration and return, and did not walk verification |
| `P-ACC-09` | every booking belongs to one registered customer | asserted throughout, cited nowhere |
| `P-HLD-08` | let a customer give seats back | the customer lane reports that none of its ten walks required a release |
| `P-PAY-12` | give the payment path no reverse | the customer lane reports there is no path to walk, since no reverse exists |

---

## Defects — 64 filed

`DEFECTS_FOUND.tsv` holds one row per defect, sorted worst severity first. Every row names the PRD
section it lands against, the anchor it attaches to, the seam where it bites, and its disposition.

| Severity | Count | Meaning |
|---|---|---|
| `blocks-code` | **18** | a developer cannot write the code without guessing |
| `ambiguous` | 41 | the document permits two readings |
| `cosmetic` | 5 | |

| Kind | Count |
|---|---|
| `gap` — the document is silent | 27 |
| `contradiction` — two parts of the document disagree | 25 |
| `unhandled-edge` | 12 |

| Disposition | Count |
|---|---|
| `PRD-fix` — the PRD can fix it without a client ruling | 48 |
| `already-open` — the question is already an Article X row | 13 |
| `new-Art-X-row` — a question the build session may not answer | 3 |

**Twenty-five contradictions is the number to look at.** A gap is the document being silent; a
contradiction is the document giving a developer two different instructions and no way to choose. All
25 are internal to the PRD and none needs a client ruling to resolve.

### The convergence — what independent lanes bought

Three lanes, walking from opposite directions and blind to each other, reached the same conclusion:
**the booking path never checks whether a film is still inside its display window.**

| Defect | Lane | Finding |
|---|---|---|
| `J-GST-02` | guest | `P-BRW-01` says the visibility predicate runs on every such query; `EP-BRW-05` says it does not apply the gates |
| `J-GST-03` | guest | `SCR-BRW-03` publishes no state for a film that has left its window, and `E2` never checks it, so the hold proceeds |
| `J-ADM-06` | admin | the seat-hold path never consults the display window — verified by search: the phrase does not occur in `E2` |
| `J-ADM-12` | admin | no combination of existing admin capabilities stops one showtime selling; unpublishing the film and withdrawing the hall both state they change nothing |

`OPEN-BRWVIS-01` is already filed and asks the client what the *policy* should be. These four findings
are a different thing and do not wait on it: **whatever the client rules, the booking surface applies
no gate at all today**, and no admin action can stop a showtime selling.

### The findings that most threaten the win condition

- **`J-ENT-01`** — `P-TKT-08` tells the person at the door to compare the reference *"against the
  day's bookings by whatever means the venue uses"*, and **no endpoint, screen or export returns a
  showtime's bookings or any booking reference to anyone but the booking's own signed-in owner.** The
  emailed reference is the customer's only proof of purchase and their only way in, and it is
  unverifiable at the only place it is used.
- **`J-CUS-04`** — the simulated payment failure is keyed on an `Idempotency-Key` prefix, the key is
  generated once per hold, and the failure copy invites a retry. Every retry fails identically, so
  **`fail → retry → succeed` is unreachable from the product.**
- **`J-ENT-04`** — the queue send runs inside the confirm request with **no timeout specified
  anywhere** (`S7.9` gives Redis, Postgres and bcrypt a timeout and gives SQS none), and no passage
  says whether the confirm response is emitted before or after it.
- **`J-ENT-03`** — a receipt is marked `sent` on SES *acceptance*, while `P-TKT-11` claims that field
  answers "did this customer get their receipt". Bounces publish to SNS and nothing subscribes, so a
  bounce reads as a delivery — which makes `OPEN-EMAILFAIL-01` invisible in exactly the case it was
  filed for.
- **`J-CUS-01`** — a returning customer booking the same showtime twice in one tab is redirected to
  their first booking's confirmation page and can never reach checkout for the second hold.
- **`J-MGR-09`** — `P-ADM-17` states flatly that a manager writes nothing, ever. The **generated**
  `contract.json` admits `manager` on five non-`GET` endpoints. The sentence is false against the
  product's own contract. The underlying question is already `OPEN-MGRBOOK-01`, so the lane recorded
  it rather than deciding it.

### One check that passed, recorded because a negative result is evidence

**The pricing arithmetic is sound.** The rounding rule is stated as integer half-up, it is
byte-identical in all five places it appears, and the worked example is **not** degenerate — the
Recliner line lands on exactly `33332.5`, the one value where half-up and half-even visibly disagree,
and the rule is exercised in the opposite direction elsewhere at base 24999. This was briefed to the
lane as a likely `blocks-code` risk and it was not one. The single pricing defect found is that an
endpoint block silently drops the P-row's overflow ceiling (`J-ADM-07`).

---

## What this goal could not do

- **Nothing was executed.** There is no application code. Every seam behaviour is read from the
  specification.
- **`E8_crosscutting.md` was grepped, not read end to end,** by every lane, on instruction — it is
  ~400 KB and holds 65 P-rows. A cross-cutting floor outside each lane's greps could bite a walk
  without having been seen. This is the most likely place an unfound defect is hiding, and it is the
  same population as the nine unwalked rows above.
- **Each lane read its own sections and not its neighbours'**, which is what made the convergence
  meaningful and also means several walks cite a neighbouring epic's behaviour from one row rather
  than from that epic's own specification. Each lane names its own instances in its `WHAT I COULD NOT
  DO` note.
- **Every occupancy figure divides by an assumed denominator.** Hall sizes are `ASSUMED`, not `RULED`
  (`OPEN-SCALE-02`), and the manager walk flags the assumption at each point of use rather than once.

---

## Files

| File | What it is |
|---|---|
| `CUSTOMER_JOURNEY.md` | the customer's walks, plus `RECEIPT_AND_ENTRY` from the independent entry lane |
| `GUEST_JOURNEY.md` | the person with no account, including the exclusions walked as absence |
| `MANAGER_JOURNEY.md` | the read-only, screen-scoped manager |
| `ADMIN_JOURNEY.md` | the admin, who performs every privileged write in the product |
| `DEFECTS_FOUND.tsv` | all 64 defects, worst severity first, one row each |
