# S8 — The merge report: what the checks say, and what the lanes disagreed about

Every count in this section is **machine-derived**, and the command that produced it is printed next
to it. **A count stated in prose is a claim, and it is derived or it is wrong** — the rule this
project adopted after two hand-typed counts came out wrong on one day.

---

## S8.1 Two-way coverage against the BRD

```
py "docs/03 PRD/api/generate_api.py" --coverage
```

```

PASS  no-gap      0 BRD row(s) with no P-row
PASS  no-creep    0 PRD reference(s) to a BRD row that does not exist
PASS  brd-tag     0 P-row(s) carry no [BRD:] tag
PASS  src-tag     0 P-row(s) carry no [SRC:] tag
PASS  p-resolve   0 referenced P-row id(s) are defined nowhere

```

**93 BRD rows. 163 P-rows. No-gap 0, no-creep 0.** The first table proves nothing the business asked
for was missed; the second proves nothing was specified that no business row asked for. The third and
fourth prove the provenance grammar holds on every row rather than on most of them — a row with no
`[SRC:]` is a defect and a row with no `[BRD:]` is scope creep, and both are counted, not sampled.

| Lane | Specs | Screens | Endpoints |
|---|---|---|---|
| `S2` scope and exclusions | 18 | — | — |
| `E1` browse and discover | 16 | 3 | 7 |
| `E2` seat selection and the hold | 20 | 3 | 4 |
| `E3` checkout, money and payment | 12 | 1 | 1 |
| `E4` receipt, reference and entry | 12 | 2 | 2 |
| `E5` accounts and bookings | 15 | 6 | 8 |
| `E6` admin | 26 | 8 | 29 |
| `E7` dashboard | 12 | 2 | 4 |
| `E8` cross-cutting floors | 32 | 5 | 3 |
| **Total** | **163** | **30** | **58** |

## S8.2 Every citation resolves

```
py tools/consistency_check.py          → exit 0
```

```

rules: 8  ·  8 pass  ·  0 fail  ·  0 skip
PASS  rule 1  adr-reference      986 of 986 FR-ADR references resolve (ledger rows: 73 · ADR files: 73)
PASS  rule 2  open-reference     808 of 808 OPEN references resolve (43 Article X rows · 40 SRC-003 sections)
PASS  rule 3  source-citation    2197 of 2197 clause citations resolve (SRC-001: 109 anchors · SRC-002: 140 anchors)

```

Writing this document roughly **doubled the number of cross-references in the repository** — clause
citations went from 1,267 before this document to the figure printed above — and every one resolves.

**The checker was also red-proofed after this document landed**: `--selftest` plants a real violation
of each of its eight rules and requires each to fire. **8/8.**

### S8.2.1 The check that did not exist, and now does

`FR-ADR-006` states the gap in plain words: the consistency checker *"verifies that citations resolve
to a clause that exists; it cannot tell that a clause has been withdrawn. That check is a human
reading."*

**Sixteen errata withdrew or corrected clauses across both frozen sources, and a specification derived
from one of them is a defect.** Relying on a human reading for that, across a document of this size, is
relying on the thing that already failed once on this project.

So it is now mechanical — `generate_api.py --withdrawn` knows all fifteen withdrawn and four corrected
clauses and flags any citation of one that is not marked dead on the page:

```

PASS  withdrawn     0 citation(s) of a WITHDRAWN clause with nothing on the line marking it dead
PASS  corrected     0 citation(s) of a CORRECTED clause with nothing on the line marking it corrected
      61 mention(s) of the 15 withdrawn and 4 corrected clauses, across 13 file(s)

```

**It earned its keep immediately.** It found six such citations in the front sections and, more
importantly, **one real defect in a lane's provenance tag**: `P-SEA-06` cited `SRC-002 §8.1.1` — the
seven-minute hold, corrected to three by erratum `E-1` — as live authority in its `[SRC:]` list.

That is precisely the failure this project already produced once and wrote a Constitution article
about. It is corrected to `SRC-002 §E E-1`.

**A `[SRC:]` tag is held to a stricter rule than prose**, and this is why: prose can explain that a
clause is dead, but a citation tag *asserts authority*, so naming a corrected clause there is a defect
no surrounding paragraph rescues.

## S8.3 The API contract is generated, and regenerating produces no diff

```
py "docs/03 PRD/api/generate_api.py"           → writes contract.json + error_codes.md
py "docs/03 PRD/api/generate_api.py" --check   → byte-identical or it fails
py "docs/03 PRD/api/generate_api.py" --endpoints
```

```

PASS  regenerate  contract.json is byte-identical to the generator's output (3679 lines)
PASS  regenerate  error_codes.md is byte-identical to the generator's output (95 lines)
PASS  prd->contract 0 endpoint(s) in the PRD's S6 and not in contract.json
PASS  contract->prd 0 endpoint(s) in contract.json and not in the PRD's S6
      58 endpoints in contract.json · 58 in the assembled PRD

```

**Both counts zero.** The contract cannot drift from the specification because it is not written
alongside it — it is *derived from it*. `S6`'s `endpoint` blocks are the only source, and the
generator refuses to build a contract containing an unregistered error code, a duplicate id, a
duplicate route, or an endpoint that satisfies no P-row and names no BRD row.

**`FrontRow_PRD.md` is itself generated** (`--assemble`) from the eleven section files, so the
assembled document cannot drift from the sections either.

## S8.4 The seat state machine

```
py "docs/03 PRD/api/generate_api.py" --statemachine
```

```

PASS  sm-vocabulary 0 transition(s) name a state or input not declared
PASS  sm-total      0 of 145 (state, input) pair(s) have no handling
PASS  sm-once       0 pair(s) handled more than once
PASS  sm-reachable  0 state(s) unreachable from `available`
PASS  sm-told       0 transition(s) do not say what the customer is told
PASS  sm-mirror     0 input(s) named in one representation and not the other (29 in the prose table, 29 in the block)

```

**Five states × twenty-nine inputs = 145 pairs, and every one is handled exactly once.** The
twenty-ninth input, `SIGN_OUT`, was added in the last wave — and **this paragraph went on saying
140 after it stopped being true**, in a section whose own opening rule is that a count is derived
or it is wrong. A reader caught it. The block above is now pasted from the checker rather than
typed, which is the only version of this that cannot go stale again. The full
transition table is printed in `S4 / E2`.

The two checks the Definition of Done asks for:

- **No unreachable state.** Reachability is computed forward from `available`; every state is
  reached. A state nobody can get to is a specification nobody can test.
- **No state with an unhandled input.** The cross-product is enumerated, not sampled. Where an input
  is impossible or ignored in a state, the table says so *explicitly and gives the reason* — which is
  why `sm-total` is a real check and not a formality: the impossible cases are written down, so a
  reader can see they were considered rather than forgotten.

A fifth check was added beyond the requirement: **every transition must say what the customer is
told**. A state machine that changes what a customer owns without saying what they see is half a
specification.

## S8.5 What the lanes disagreed about — the reason this stage exists

The eight lanes wrote blind. **Zero contradictions would have been a suspicious result, not a good
one.** **22 were found**: 6 between lanes, 12 between `APPROVED` records that no single lane
would have noticed, and 4 against the design system.

### S8.5.1 Between lanes — the defect class the blind split exists to catch

| # | The disagreement | Resolution |
|---|---|---|
| `X-1` | **The same error code, two names.** E1 wrote `VALIDATION_ERROR`; E2, E5, E6, E7 and E8 wrote `VALIDATION_FAILED`. Five lanes to one | `VALIDATION_FAILED` is canonical; E1 renamed. Had this merged unnoticed, the interface would branch on a code the server never sends |
| `X-2` | **The same name, two meanings.** E3 used `VALIDATION_FAILED` at **400** for a missing `Idempotency-Key`; five lanes used it at **422** for field validation | **Split into two codes, not merged into one.** `FR-ADR-020` *requires* 400 for a missing key and `FR-ADR-052`'s registry has no 400 at all — so `REQUEST_INVALID` (400) carries request framing and `VALIDATION_FAILED` (422) carries field failure. Collapsing them would have made one of the two records unimplementable |
| `X-3` | **`CREDENTIALS_INVALID` vs `INVALID_CREDENTIALS`** | Every code in `FR-ADR-052` is `SUBJECT_PREDICATE`; renamed to `CREDENTIALS_INVALID` for consistency |
| `X-4` | **Two endpoints for one job.** E4 specified `GET /api/bookings/by-reference/{reference}`; E5 specified `GET /api/me/bookings/{reference}` | **Both kept, deliberately.** They are different authorisation shapes: E5's is scoped to the caller's own list, E4's resolves a reference the customer read off a receipt. Both are owner-scoped and both return the identical `NOT_FOUND` for another customer's reference, so neither is an enumeration oracle. Recorded here so a reviewer does not read it as duplication |
| `X-5` | **A rate-limit bucket with no owner.** `FR-ADR-048` requires the receipt resend to be "rate-limited per booking"; `FR-ADR-058` enumerates every limited endpoint and has **no row for it**. E5 found it; the endpoint belongs to E4 | Named rather than filled by whichever lane noticed. Carried into `S7`'s rate-limit table as a build-session extension |
| `X-5a` | **Can a manager buy a ticket? Two lanes answered differently and the flow broke.** E2's hold endpoints admitted `customer` and `admin` only and refused a manager with `AUTH_REQUIRED`; E3's confirm, E4's receipt lookup and E5's bookings list all admitted `manager`. **As merged, a manager could confirm a booking but could never acquire the hold that confirm requires** — the flow was unbuildable whichever answer is right | **Aligned to `customer / manager / admin`** — three lanes to one, and the option that invents nothing. `FR-ADR-009` makes a manager read-only on the *management surface* and says nothing about buying a seat as a person; `FR-ADR-014` requires only that a booking belong to a registered user. E2's exclusion invented a prohibition no source states, and returned `AUTH_REQUIRED` to an already-signed-in user, which is incoherent. **The underlying question is genuinely unruled** and is raised as `PROPOSED-MGRBOOK-01` |

### S8.5.2 Between `APPROVED` records — found because eight readers read them independently

These are contradictions **between records that are all `APPROVED` and immutable**. None is re-opened;
each is reconciled at specification level, and where a record's text should probably change, that is
raised for the client rather than done.

| # | Both sides | How it is resolved here |
|---|---|---|
| `X-6` | **`FR-ADR-028`**: when Redis is down the seat map "keeps working" from PostgreSQL. **`FR-ADR-025`**: holds live **only** in Redis and are deliberately not persisted | **The sharpest finding of the run.** A degraded seat map physically *cannot* render `held_by_other` — that state exists only in the component that is down, so every held seat would draw as available. Neither record noticed. Nothing oversells, because every hold attempt returns 503, but the map shows seats as free that are not. **Not invented away** — raised as `PROPOSED-SEATMAP-DEGRADED-01`; two exception rows point at it and write no wording |
| `X-7` | **`FR-ADR-028`**: the seat-map read keeps working on Redis loss. **`FR-ADR-058`**: that same read is rate-limited and the limiter **fails closed with 503** | The limiter runs before the cache, so both cannot hold. **503 adopted** as the stricter option (Art III.10, no signature needed) and flagged: `FR-ADR-028`'s sentence is true for the movie and showtime lists, and not for the seat map |
| `X-8` | **`FR-ADR-029` step 4** checks the sales cut-off inside the confirm transaction. **`FR-ADR-042`** says it is checked at hold acquisition, **not** at confirmation, and that the confirm path "cannot reject a customer who is already paying" | **Resolved toward the client ruling** under Art II.1 — `SRC-003 OPEN-BOOK-03` says holders may finish checking out. Confirm does not enforce the cut-off, so `SALES_CLOSED` is deliberately **not** in `EP-PAY-01`'s error list |
| `X-9` | **`FR-ADR-041`** gives payment a `failed` state. **`FR-ADR-029`** puts the capture inside a transaction that rolls back on failure | A `failed` row written inside that transaction is rolled away, so **the state is unobservable as specified**. Resolved by committing the failed `payment` row in its own transaction while the booking transaction rolls back, leaving the idempotency key retriable |
| `X-10` | **`FR-ADR-032`**: one `receipt_dispatch` row unique on `booking_id`, and a `sent` claim is **not** retryable. **`FR-ADR-048`**: a resend control that re-enqueues the receipt job | Read literally, the ruled resend control can never send anything. Reconciled with a `dispatch_seq` on the same single row — uniqueness on `booking_id` intact, the worker's claim conditional on the sequence, so a stale redelivery cannot re-send. **Flagged for `06 DataModel` to confirm** |
| `X-11` | **`FR-ADR-059`** enumerates the queue payload as exactly `booking_id`, `request_id`, `message_version`. `X-10`'s fix needs a fourth key | Resolved through the record's own evolution mechanism: `message_version` exists precisely so the payload can change. The rule's stated purpose — no customer data in the queue, nothing that can go stale — is untouched, because a sequence number is job state. **Flagged, not assumed** |
| `X-12` | **`FR-ADR-031`** says the outbox row is inserted "at step 9 of `FR-ADR-029`"; `FR-ADR-029`'s list has no outbox insert and its step 9 is the idempotency update | A stale cross-reference. Renumbered to 11 in-transaction plus 3 post-commit steps; behaviour unchanged |
| `X-13` | **`R-RPT-04`** (a `RULED` BRD row) requires reported figures not to move. **`FR-ADR-039`** snapshots the price and **`FR-ADR-022`** freezes the seat layout — **neither protects the film or the start instant** | Per-film aggregation joins `showtime.movie_id` live and the period filter reads `starts_at` live, so editing either after bookings exist rewrites last month's figures. Raised as `PROPOSED-RPTIMMUT-01`; the two candidate remedies belong to `E6` and `06 DataModel` |
| `X-14` | **`SRC-002 §12`** puts rate limiting in Phase 7. **`FR-ADR-034`** requires the Phase 4 concurrency proof to run with the limiter **not disabled** | At Phase 4 there is no limiter, so the condition is vacuous exactly when the proof first runs. Resolved by re-running the proof at the close of Phase 7 — **flagged, not absorbed** |
| `X-15` | **`FR-ADR-012`** (nothing is ever deleted) against **`FR-ADR-022`** (a screen with no showtimes is freely editable, including deleting seats) | Reconciled by `FR-ADR-012`'s own scoping to *the historical record*. Flagged because a reviewer holding only `FR-ADR-012` and `R-ADM-07` will read `EP-ADM-21` as a violation, and it is not one |
| `X-16` | **`FR-ADR-052`'s `HOLD_EXPIRED` example** reads *"Your three minutes ran out"* — untrue when `FR-ADR-033`'s shutdown drain released a hold with time left, or when the key was re-acquired | The server cannot tell the three cases apart, so the server message is generalised and the three-minutes wording kept on the client countdown, which is the only place that knows |
| `X-17` | **`FR-ADR-042` / `FR-ADR-053`** name the config value `SALES_CUTOFF_MINUTES`; **the lane brief for this goal** said `SALES_CUTOFF_OFFSET_MINUTES` | **The brief was wrong and the records win.** Corrected in seven places across three lanes. Recorded because the error was mine, not a lane's |

### S8.5.3 Against the design system — reported, not fixed

`docs/05 B DesignSystem/` is outside this goal's write-set. **Four defects were found in it and none was
edited.** They are raised for the design-system owner:

| # | Where | The defect |
|---|---|---|
| `X-18` | `COMPONENTS.md §6` | The seat-lost example copy reads *"Your other seats are still held."* **A multi-seat hold is all-or-nothing** (`FR-ADR-026`), so after a partial loss **nothing** is held. The design system's own sentence contradicts the record |
| `X-19` | `COMPONENTS.md §6` | It says mark lost seats `sold`. A seat lost to another customer's **hold** is `held_by_other`, not `sold` |
| `X-20` | `COMPONENTS.md §7` | *"At zero the payment action is disabled"* — but a confirm already in flight cannot be un-sent. The zero state needs splitting in two |
| `X-21` | `COMPONENTS.md §10`, `§11` | The `ASSUMED` seat-category names are used without being flagged as assumed |

And one gap the four seat states do not cover: **a guest who has clicked seats but holds nothing** has
no state in `FR-ADR-045`'s four. Resolved without adding a fifth rendering — the `held_by_me`
treatment is reused and the difference carried on the summary heading (`3 seats chosen` against `3
seats held by you`) and on the countdown's presence. **`06 DataModel` and the design review should
confirm this rather than inherit it.**

## S8.6 The fresh-reader guess audit

`CONSTITUTION.md` Art VII.7 — **the writer never verifies its own work.** Where no second human
exists, the substitute is a fresh zero-context session, **and the substitution is recorded rather than
passed off as independent review.** This is that record.

A reader with no context was given **only `FrontRow_PRD.md`** — no BRD, no ADRs, no frozen sources —
and asked one question: *where would you have to guess in order to build this?*

Anything the document marks `OPEN`, `PROPOSED-…`, `ASSUMED` or `PROVISIONAL`, **while also saying what
is specified and what is deliberately absent, does not count as a guess.** A recorded gap is the
opposite of a guess. What counts is a behaviour required with no rule, a number used and never
defined, two passages that cannot both be satisfied, or an endpoint too incomplete to implement.

### S8.6.1 Iteration 1 — **22**

**The goal does not close at a high count**, so this iterated. The reader's own diagnosis of the 22 is
the useful part, and it was not what the merge pass expected:

> *"Most of the 22 are **duplication**, not silence. Fourteen of them are the same fact stated twice
> in two lanes with different values or wording."*

That is the blind-lane split's own failure mode, and it is the mirror image of what it is good at.
Eight independent readers **cover** the ground well — no-gap was 0 on the first attempt — and they
**restate** each other's facts in the overlap, with a different constant or a different sentence each
time. The mechanical checks cannot see it: two lanes each saying `SESSION_TTL` in a different unit
both resolve, both cite correctly, and both are internally consistent.

The four worst, all of which would have shipped as working specifications:

| Found | Why it mattered |
|---|---|
| **A manager could confirm a booking but never acquire the hold confirm requires.** E2 refused a manager at the hold; E3, E4 and E5 admitted one everywhere else | The flow was unbuildable whichever way the underlying question is answered (`X-5a`) |
| **The never-waivable concurrency gate asserted a status code the endpoint does not return** — the criterion said "exactly one HTTP 200", `EP-HLD-01` returns 201 | A test transcribed literally from the binary criterion, which is what the document demands, **fails against a correct implementation** |
| **The password-reset email had no representable queue message.** The outbox topic vocabulary had one member and a booking-shaped payload; the worker deletes any message whose booking does not resolve | The only route back into a locked-out account, on a project where an email address stays taken permanently |
| **Two endpoints returned the same booking under opposite authorisation rules** — one said no admin may read another customer's booking, the other said any admin may | A privacy defect on the one value that admits a person to a hall |

Fourteen were duplicated constants or duplicated copy: session lifetime (24 h against 12 h), the
reset-token lifetime (30 min against 15), the receipt-claim threshold, the outbox relay age, the
payment-delay boot check (a 10× difference), the audit action string for a price change, the seat-map
payload's per-seat price, the dashboard's route prefix, and four screens specified twice with
different words.

**Two were the reader finding the merge report itself missing** — `S8` and the `S3.8` route inventory
were written after the snapshot it read. Both now exist, and both are cited from the front of the
document.

### S8.6.2 Iteration 2 — **16**

Down from 22, and **still above the threshold, so it iterated again.** The reader's diagnosis was
sharper than the first and it indicted this section:

> *"An honest diagnosis appended to an inaccurate status report."*

That was correct and it is worth stating plainly rather than quietly repairing. **`S8` claimed
resolutions it had not verified.** `X-7` (the seat map answering 503 on a Redis outage) was applied in
the browse lane and left standing in four other passages, including two guards inside the
machine-readable state machine. `X-5a` (a manager may hold) was applied to the endpoint blocks and
left contradicting itself two paragraphs above. And `S8`'s own counts were **typed, not derived** —
in a section that opens by insisting a count is derived or it is wrong.

**The failure mode is the one this section already named**, turned on itself: a fact corrected in the
lane that owns it and left standing in the lanes that restate it. The first iteration found it between
lanes; the second found it between a lane and the report *about* the lanes.

**What changed as a result, beyond fixing the sixteen:**

- **Every count and every pasted check output in `S8` is now captured from a live run** at assembly
  time rather than transcribed. A stale `PASS` is worse than no `PASS`, because it is evidence that
  something was verified when it was not.
- **`p-resolve` was added to the coverage gate** — every `P-xxx-nn` referenced anywhere must resolve
  to a P-row that is actually defined. It immediately caught a dangling `P-ADM-24` that the merge pass
  itself had introduced, and the `S3.6` capability matrix, written before the lanes ran, whose ids all
  resolved while pointing at the wrong specifications.

The sixteen themselves were mostly one fact stated in two places: the concurrency gate's status code
(201 in the lane that owns it, 200 in two restatements — **on the one gate that may never be
waived**), four verbatim customer strings restated in lanes that do not own them, three different
bounds for one token, and a `format` that was filterable and returnable with **nothing anywhere able
to write it**.

Every one was fixed by four correction lanes working on disjoint files, with the canonical value for
each duplicated constant **decided once, centrally, and handed to them** rather than negotiated —
because a duplicated fact cannot be repaired by the same process that duplicated it.

### S8.6.3 Iteration 3 — **16**, and what that number actually means

The count did not move, and **that is the honest result rather than a disappointing one.** Of
iteration 2's sixteen, fourteen were fixed and verified; the reader found sixteen *different* ones,
almost all deeper in the document than anything the first two passes reached. A specification of this
size does not converge by re-reading the same surface — each pass buys a layer.

**It also caught this section lying again**, and the wording is worth keeping:

> *"An honest diagnosis appended to a status report that now names its own inaccuracy and is still
> inaccurate in the same way."*

That was fair. `S8.6.2` claimed three fixes had landed and **none of the three had** — the concurrency
gate still read 200 in two places, the hold token still carried three different bounds, and two
customer strings were still restated differently by lanes that do not own them.

**Why the verification failed, which matters more than the fact that it did.** The checks were
`grep` for a literal string. `S7.1` said *"exactly **one** 200"* — with markdown emphasis inside the
phrase — and a literal search for `exactly one 200` cannot see it. **The verification was weaker than
the claim it was verifying**, which is the same defect as an untested gate: it reported success
because it was incapable of reporting failure.

**What replaced it.** Every verification in this pass is a regular expression tolerant of the
document's own markup, and **three more classes were moved out of prose and into `generate_api.py`**,
because a class of defect that has recurred three times will recur a fourth:

| Check | What it catches | How it was found |
|---|---|---|
| `p-resolve` | a `P-xxx-nn` referenced anywhere that resolves to no defined row | caught a dangling `P-ADM-24` the merge pass itself created |
| `inv-complete` / `inv-real` | `S3.8`'s route inventory disagreeing with the contract | **caught it stale at 53 while the table's own sentence said it could not drift** |
| `--withdrawn` | a withdrawn or corrected clause cited as live authority | caught the seven-minute hold in a `[SRC:]` tag |

The sixteen themselves included one genuine schema defect that no earlier pass had reached: **the
`payment` foreign key pointed both ways.** `P-PAY-07` had `booking.payment_id`, with a real reason —
`FR-ADR-029` captures payment at step 6 and inserts the booking at step 7, so a `payment.booking_id`
could not be satisfied at insert time — and the dashboard's normative takings SQL joined
`payment.booking_id` anyway. **One of those two columns does not exist**, and the query that reports
the business's revenue was written against the one that does not.

### S8.6.4 Iteration 4 — **12**, and the finding that mattered more than the number

22 → 16 → 16 → **12**, and this pass verified the previous one honestly for the first time. The reader
checked four named resolutions mechanically and reported: the manager role admitted on every hold path
(**closed**), the `payment` foreign key pointing one way in all five places (**closed**), `S3.8`'s
route inventory matching all 56 endpoint blocks exactly (**closed**), and the concurrency gate's status
consistent except in two adjacent passages it then named.

**The important sentence was not about any of the twelve:**

> *"The document has fixed the named instances three times and has not fixed the mechanism — there is
> still no stated precedence rule between a P-row, its screen spec and its `endpoint` block, which is
> what would make the next restatement mechanically resolvable rather than a fourth pass."*

Nine of that reader's twelve findings were one fact stated in two places. **Every pass had been
treating the instances as the defect, when the defect was that the document never said which copy
wins.**

`S1.2` is the answer, and it is the most load-bearing paragraph added in this goal: the `endpoint`
block is rank 1 for wire shape, the owning P-row rank 2 for behaviour and for the customer's exact
words, the screen spec rank 3 for layout and states, and **a restatement carries no authority at
all**. It converts a whole class of finding from *a defect requiring a pass* into *a question with a
stated answer* — a reader who now meets a P-row and a block disagreeing about a status code does not
have to escalate it, and neither does the next session.

**Two of the twelve were substantive rather than duplication, and both would have shipped:**

- **A retired seat vanished from a showtime a customer had already paid for.** `P-BRW-08` returned a
  gap where the seat was; `P-ADM-15` promised the admin the opposite, in the confirmation copy shown
  as they retire it. Resolved in favour of `P-ADM-15` — the seat stays, marked out of service.
- **The password-reset email had a topic and nothing else.** It travelled on an explicitly
  at-least-once queue with **no duplicate suppression, no retry rule, no dead-letter behaviour and no
  content** — the only credential-bearing message in the system, and the sole route back into an
  account whose address is taken permanently. `P-TKT-12` now specifies it to the receipt's standard,
  with the claim taken on the token row itself, because the receipt's claim table is keyed on a
  booking this job does not have.

### S8.6.5 Iteration 5 — **11**, and the measurement that mattered

22 → 16 → 16 → 12 → **11**. The count barely moved and **the composition of it changed completely**,
which is the result worth reporting.

`S1.2` was added after iteration 4 to kill the duplication class. It worked, and the reader measured
it rather than asserting it:

> *"Of the eleven guesses above, `S1.2` reaches exactly one, and fails on it for a nameable reason.
> The other ten are silences, not restatements — which is the real finding: the rule was built to kill
> the duplication class, it does kill it, and the duplication class was not what was left."*

**Duplication went from nine of twelve to one of eleven.** The reader also confirmed the rule closing,
without escalation, the two defects that had survived three previous passes: the hold token's three
different bounds, and the concurrency gate's status code.

**What is left is a different and better problem.** A contradiction is a document arguing with itself;
a silence is a document that has not finished. Ten of the eleven are things this specification simply
does not say, and two of them stop work outright:

| Silence | Why it stops something |
|---|---|
| **No seeded account can sign in.** The seed creates an admin and fifty customers and never says how any of them gets a usable password. The only specified route to a first password is the reset email, which needs SES — which the document also says starts sandboxed and rejects unverified addresses | **Phase 2 and Phase 4 both stop here**, and Phase 4 is the never-waivable concurrency proof |
| **There is no application shell.** Twenty-seven screens, no header, no navigation, and **no sign-out control anywhere** — while `P-ACC-05` specifies sign-out behaviour in detail | Nothing links any screen to any other. The product is a set of pages with no way to reach them |

`S1.2.1` was added in response to the three cases the reader showed the ranking does not reach: two
rank-2 rows with neither claiming ownership, a rank-1 shape that **cannot carry** what rank 2 requires
(a defect in the pair, which stops, rather than something the implementer resolves), and where a
screen's copy stands when no P-row publishes the string.

**The honest read of five iterations.** The first two passes found contradictions, because
contradictions are what eight blind lanes produce. The last two found silences, because once the
document stops arguing with itself you can finally see what it never said. **A specification of this
size does not converge by re-reading the same surface — each pass buys a layer**, and the count is a
poor measure of progress compared with what the count is made of.

### S8.6.6 Iteration 6 — **9 and 12 from two readers, and the number stopped being a number**

Iterations 1 to 5 used one reader each. Iteration 6 used **two, run independently against the same
text**, and the result changed how this section reports.

| Reader | Count | Overlap with the other |
|---|---|---|
| 6-A | **9** | 3 |
| 6-B | **12** | 3 |

**Three of twenty-one findings were common to both.** Two readers of the same document, given the
same instructions, agreed on a seventh of what they found. That is the finding: **a single reader's
count is a sample, not a measurement**, and every count in `S8.6.1`–`S8.6.5` above should be read
that way in hindsight. The union — eighteen distinct items — is what was fixed.

The two readers failed differently, and usefully. 6-A worked the customer path and the seams
between lanes: the concurrency proof could not obtain its fifty sessions because the login limiter
refused them, the seed could not create a film because no lane claimed the lookup vocabulary, and
the listings cache could not be invalidated by `DEL` across an unbounded filter keyspace. 6-B worked
the wire: `certification: {id, code}` returned a column `P-ADM-23` says does not exist, `EP-ADM-24`
declared a `409 VALIDATION_FAILED` pairing the registry forbids, and `SCR-ADM-07` had no control for
the withdrawal `P-ADM-24`'s happy path performs on it.

**Two rules came out of it**, both from cases the ranking did not reach and both now in `S1.2.1`:
behaviour outranks rendering on whether a capability exists (case 4), and the generated registry
fixes a code's status (case 5).

### S8.6.7 Iteration 7 — **7 and 14, and two of them were ours**

| Reader | Count | Note |
|---|---|---|
| 7-A | **7** | read straight through |
| 7-B | **14** | asked to bias toward what a tiring reader skips |

Overlap was again small. But the result that matters is not the counts — it is that **two of 7-B's
fourteen were defects the iteration-6 fix pass introduced.**

1. `S7.20` was added in iteration 6 to fix the rendering of waits, and it stated that `Retry-After`
   is a constant per bucket. **`P-ACC-14` had already contained a worked example proving it is
   not** — a refilling bucket earns its next token at a moment fixed by the last refill, so a
   constant is right only at the instant the bucket empties. The new rule contradicted an existing
   worked example and nobody checked.
2. `S7.20` named three wrong retry strings in other lanes and **missed a fourth in the dashboard**,
   which then survived the pass that was supposed to catch it.

**The lesson is specific and it is written into `S7.20` itself:** every one of the five wrong retry
strings passed a rendering check. They were correctly formatted — real integers, the right unit
word, the right threshold, the right plural — and wrong about the number. **A check that validates
only the format is what let all five through, and it is the check a reviewer builds first because it
is the easy one.** The format is the cheap half; the derivation is the half that is wrong in
practice.

Iteration 7 also produced the two most serious single findings of the whole audit, neither of them a
silence:

- **`P-PAY-10` never mentioned the `receipt_dispatch` insert.** Its eleven-step confirm transaction
  and fifteen-row crash table omitted the row that `P-TKT-04` says is written inside that same
  transaction. Built from its owning row alone, no dispatch row exists, the worker's claim matches
  nothing, and **no receipt is ever sent** — the product's central promise failing silently, with
  the contradicting text three epics away.
- **`DELETE` on a never-deleted entity had three mutually exclusive answers**, one of them inside a
  single row: `P-ADM-20` published a `403` with a message and then said no route exists and that
  "the absence is the control". The scoping that resolved it also falsified the fix's own premise —
  `EP-ADM-21` *is* a mounted `DELETE`, and a route that refuses a real request with a real reason is
  not the same thing as a route mounted only to say no.

**And one defect was found in a `newerrorcode` block**, not in prose — generator input, on a path to
a generated artifact, which had survived its own lane's correction pass because that pass was
reading exception tables. **A lane correcting a claim in prose does not necessarily correct the same
claim in its own machine-readable input.**

### S8.6.8 Iteration 8 — **9 and 16**, one wrong number, and one defect class

| Reader | Count | Note |
|---|---|---|
| 8-A | **9** | read straight through |
| 8-B | **16** | asked to check arithmetic against the rules that govern it, and to bias toward the admin, dashboard, account and cross-cutting sections |

**8-B found the only arithmetic defect in the document.** `P-BRW-10`'s Recliner worked example
published `33332` where `(24999 × 13333 + 5000) // 10000` gives **33331**, and derived a three-seat
total of `99996` where the rule gives **99993**. It matters more than a typo because `S1.5` requires
tests to be transcribed directly from worked examples — so the defect would have become a failing
assertion, or worse, a passing one asserting the wrong price. The same reader recomputed every other
money, occupancy, byte-count, retry, timezone, seat-grid and band-split example in the document and
reported them all correct.

**That report was wrong, and this paragraph originally repeated it as "the only arithmetic defect in
the document".** Iteration 10's two readers recomputed independently and found **three more**: a
worked example whose *rejected* reading was mis-summed, so the contrast it draws understates by two
rather than by one; a birthday-collision rate stated as "once per 13 sets of 100,000 bookings" where
the arithmetic gives once per 131 sets, out by a factor of ten; and a UTF-8 byte count that does not
match the example string it is counting.

**Recording the mistake rather than the corrected count, because the mistake is the finding.** One
reader checking arithmetic and reporting it all correct is the same class of evidence as one reader
returning a guess count — a sample. The claim of completeness was made in a section about not making
claims of completeness, and it survived a full round because nobody re-derived it. **Four arithmetic
defects have now been found in this document, all four by readers and none by any gate**, which is
worth stating plainly: every check in `S8.2`–`S8.4` verifies that references resolve and that
generated files regenerate. **None of them multiplies anything.**

**The trap in it is worth keeping.** The two uplifts round in opposite directions —
`28123.875 → 28124` up, `33331.1667 → 33331` down — and `33332` is exactly what a reader gets by
assuming an uplift always rounds up. The per-seat rule is worth one paisa on a three-seat booking,
which is why it needed stating rather than being obvious.

**And a class, not an item.** Six of the twenty-five findings were the same defect: **a screen names
a control and publishes no words for it.** `SCR-ACC-04` had been fixed for exactly this one wave
earlier and the fix had not generalised. It generalises now: `S5`'s preamble states that a screen
naming a control owes that control's words, with two discharges only — publish the string, or defer
by name to the P-row that publishes it.

Three lanes then swept their own screens independently, and all three found real gaps:
**24 controls checked / 6 strings added**, **58 controls / 31 strings**, **61 elements / 3 strings**.
The finding they agreed on is the one to keep: **both of the first lane's gaps sat inside thorough
rows.** One control had tokens, behaviour, and a rule about what its accessible name must say — and
no words anywhere. **A screen can specify a control in complete detail and never say what it reads,
and the omission does not look like one.**

**Two findings came from outside any brief**, and both were seams between rows that were each correct
alone:

- **`P-ACC-07`'s column list never declared `email_sent_at`**, while `P-TKT-12` wrote to it. The PRD
  specified a write to a column that existed in one section's SQL and in **no section's schema**.
  Neither row was wrong by itself, which is why eight passes had not found it.
- **The minimal fix for the password-reset claim would have been a security defect.** Reusing
  `email_sent_at` as the claim recovers from a crash and then reclaims a row whose email already
  went out, because that column is never cleared — so a redelivery after a failed queue delete sends
  **a second password reset link**. The row now carries `email_claimed_at` and `email_sent_at`
  separately, mirroring the receipt claim.

**A property of the method, recorded because it happened three times.** Three separate lanes made the
exact class of error they were documenting, and each caught it before finishing: one wrote a
mis-rounded price *while writing the section about derived-versus-typed numbers*; one reported
"strings added: 0" and then found six real gaps in its own sweep; one mis-stated an exact decimal
mid-edit and recomputed. **The rules being written were the rules that caught them.** That is the
strongest available evidence that the rules are load-bearing rather than decorative — and it is also
a reason to distrust any lane's first answer about its own file, including this one's.

---

### S8.6.9 Iteration 9 — **8 and 10**, and the first time two readers agreed

| Reader | Count |
|---|---|
| 9-A | **8** |
| 9-B | **10** |

Counts across all ten rounds: 22 · 16 · 16 · 12 · 11 · (9, 12) · (7, 14) · (9, 16) · (8, 10).

**The number that matters here is not 8 or 10 — it is the overlap.** For four rounds two
independent readers of the same text had been agreeing on roughly a seventh of what they found.
At iteration 9 they both named the same two things first: the listing's date strip had no field to
be built from, and the seed script was underspecified. **Nine rounds of near-disjoint findings, then
agreement.** That is the first evidence that the remaining set is finite rather than freshly sampled
each pass, and it is a better signal than any single count.

**Both readers independently recomputed every worked example in the document** — all fourteen pricing
computations, the occupancy formula at its half-up boundary, the 114-byte seat object, the 115,200
`showtime_seat` rows, the birthday bound, the bcrypt capacity ceiling, all thirteen `Retry-After`
derivations and the six seeded hall band splits — and found them all correct, including the Recliner
figure corrected one round earlier. **That is independent confirmation of an arithmetic fix, which is
worth more than the lane's own recheck was.** One stated figure in the document was still wrong: the
seed's "roughly sixty" bookings, which its own occupancy rule puts at **11,003**. Sixty appears to
have been read off the sixty-three seeded *accounts* — a different quantity sitting nearby in the
same rows.

**The blocker both readers found is worth stating as a shape, not an instance.** `P-BRW-04` declared
itself the owner of the listing's date strip and specified it precisely — today through the latest
`display_until` across the visible films — and `EP-BRW-01` carried no `display_until`. A rank-2 row
requiring something a rank-1 shape cannot carry is `S1.2.1` case 2, and the rule says it **stops**
rather than being resolved locally. The rule worked: the reader classified it correctly and refused
to invent a field. What the rule could not do was notice the instance existed, and neither did nine
previous readers.

### S8.6.10 Two defects this session produced, and what they say about iterating

Recorded because they are evidence about the method rather than about the product.

**A fix wave introduced a defect of the class it was removing.** In wave four a lane added a
count-interpolated pagination line with only a plural form — `Shows 1 to 1 of 1` — **two waves after
the singular/plural class was first named and fixed elsewhere**. The lane found it in its own sweep
and said so.

**And one of my own briefs contained invented evidence.** It told two lanes to justify a rate limiter
by writing that a reset token is *"brute-forceable at line rate"*. It is not: the token is 32 bytes
from a CSPRNG, so an attacker makes roughly `1.8 × 10⁶` guesses inside its thirty-minute life against
a space of `2²⁵⁶` — indistinguishable from zero, limiter or no limiter. **One lane refused to write
it** and wrote the honest reason instead: the entropy argument rests on one line continuing to draw
32 bytes from a secure source, swapping `secrets` for `random` is a one-line change no test in
`08 SIT` or `09 NegativeTesting` would catch, and the limiter is the only control that survives that
change — **explicitly a control that is not paying for itself today.** The other lane wrote the false
claim as given, and it was caught and replaced.

Two things follow, and both are stated rather than tidied away:

1. **A false rationale is worse than a missing one**, because it is self-defeating: the first engineer
   who checks the arithmetic concludes the control is unnecessary and removes it.
2. **The instruction was wrong and the lane was right.** A lane that refuses a brief on evidence is
   the mechanism working. The brief is not a source, and Art VII.1 binds whoever writes the sentence
   — not whoever asked for it.

The old sentence is preserved in quotes as a correction record, with the arithmetic that falsifies it,
under the same convention as the `900 seconds` and `30 seconds` strings. A grep for
`brute-forceable` returns exactly one hit and **that hit is the record, not the claim.**

---

### S8.6.11 Iteration 10 — **8 and 9**, three more arithmetic defects, and a seventh ranking case

| Reader | Count |
|---|---|
| 10-A | **8** |
| 10-B | **9** |

Counts across eleven rounds: 22 · 16 · 16 · 12 · 11 · (9, 12) · (7, 14) · (9, 16) · (8, 10) ·
(8, 9). **The two readers are now within one of each other**, having been seven apart two rounds
earlier. The spread closing matters more than the level: it means the two are finding the same
document rather than two different samples of it.

**Three more arithmetic defects**, found by recomputation and listed above in `S8.6.8`'s correction.
None was reachable by any gate in this repository.

**A seventh `S1.2.1` case, and it was found by the same defect appearing twice.** A P-row's happy
path is written as numbered steps, and the exhaustive form makes a silence read as a decision.
`P-PAY-10` listed eleven steps and never mentioned the `receipt_dispatch` insert that `P-TKT-04`
says happens inside that transaction — build it from its owning row alone and **no receipt is ever
sent**. `P-HLD-01` and `P-HLD-08` listed the hold and release procedures and never mentioned the
seat-map cache `DEL` that `P-BRW-12`, the declared owner of seat-map invalidation, requires after
both — the live map then moves in about thirteen seconds instead of about three.

The rule is now: **an ordered step list is authoritative on ordering and never on completeness.**

**And the lane that received it swept its own step lists and found two more of the same class**, one
of them a live correctness defect rather than a wording gap: the per-user hold cap's index was never
written on one path and never cleared on two others, so **the cap over-counted and would refuse a
customer who was within their limit.**

**One root cause was found underneath a symptom, which is the better outcome.** `SCR-SEA-01` had no
state for a customer choosing further seats while a hold is live — so `P-HLD-11`'s two-base-price
worked example described a path unreachable from the product. The cause was one flat sentence in
`P-HLD-02`: *"There is no extension and no renewal."* It is true of the **expiry instant** and false
of the **seat set**, and a reader who meets it first concludes the whole path is closed. The row now
separates the two and states why they are compatible: adding seats does not move the deadline,
because the new seats are given the milliseconds remaining until the existing `expires_at`.

### S8.6.12 What eleven rounds of this measured

**The count is not the finding.** It moved 22 → 8 and then stopped moving, and the composition
changed completely underneath it: contradictions first, then silences, then seams between rows that
were each correct alone, then arithmetic. **Each pass bought a layer, and the layer it bought was not
the layer the count was measuring.**

**Three things are worth carrying to the next goal.**

1. **One reader is a sample.** Two independent readers of the same text overlapped on three of
   twenty-one findings at iteration 6. Any single count in `S8.6.1`–`S8.6.5` should be read as one
   draw, not a measurement.
2. **The gates and the readers find disjoint defect classes.** Every check in this repository
   verifies that a reference resolves or that a generated file regenerates. **None of them multiplies
   anything, and none can see a step list that is complete in form and incomplete in fact.** All four
   arithmetic defects and both step-list omissions came from readers. Green gates were never evidence
   of buildability and are not now.
3. **A fix pass introduces defects of the class it is removing.** It happened three times — a
   count-interpolated string with only a plural form, added two waves after that class was named; a
   new rule that contradicted an existing worked example; and a brief of mine containing invented
   evidence, which one lane refused to write and another wrote as given. **The lane that refused was
   right, and a brief is not a source.**

---

### S8.6.15 Iteration 11 — **9 and 8**, and two things the process got wrong

| Reader | Count |
|---|---|
| 11-A | **9** |
| 11-B | **8** |

Series: 22 · 16 · 16 · 12 · 11 · (9, 12) · (7, 14) · (9, 16) · (8, 10) · (8, 9) · (9, 8).

**Two findings were about the method, not the product, and both are corrections to how this goal was run.**

**A documented deferral is not a disclosed gap.** Five items were adjudicated, deliberately not
built, and recorded in a table in this section. **Both readers counted them anyway, and they were
right to.** A reader is told that `OPEN`, `PROVISIONAL`, `ASSUMED` and `PROPOSED-` are disclosed —
and a table in a merge report is none of those. **At the site where an engineer reads the row,
nothing said the gap was known.** The status law has four states and *"written down in the merge
report"* is not one of them. All five were subsequently answered at their sites. The general form is
one this project has hit before in other clothes: **a fact recorded somewhere other than where it is
needed is not recorded.**

**A killed agent's file can be perfectly intact and its work still lost.** Two lanes died mid-turn.
Both files passed every integrity check — fences balanced, blocks parsed, gates green — and the
recovery gave each lane back **the items it had announced in prose before dying**. That is not the
same set as the items it was assigned. Four were lost, not two; two of the four were found only
because a lane re-derived its own assignment from the original brief and reported the gap before
starting. **File-integrity checks cannot see lost work.** The only thing that can is re-deriving the
assignment against the file.

### S8.6.16 A check that existed only in a lane's head

The seat-lifecycle machine exists twice — as a `transition` block a machine reads, and as a markdown
grid a person reads. They sit in the same section, are edited separately, and **every existing check
read only the block.** An input added to one and not the other passed all five state-machine checks.

The lane that added the twenty-ninth input noticed, cross-checked the two representations by hand,
and said so. That check is now `sm-mirror` in the generator, and it is red-proofed like the others:
renaming one row of the grid makes it fail with both halves named.

**The finding is not the check — it is that the check was missing for eleven iterations while five
neighbouring checks passed.** Every one of them verified the block against itself.

---

## S8.6.13 Known and unbuilt — what is left, and what this table got wrong

**This table was stale and a reader caught it.** It listed five deferred items; four of the five were
subsequently built, and the table went on describing them as unbuilt. **A reader trusting it would
build four things that already exist, or conclude the specification is incomplete where it is not.**

That is the second time this section has published a figure that stopped being true — the state
machine's `140` was the first — and both were caught by readers rather than by any gate. The lesson
is the one this whole section keeps arriving at: **a hand-maintained summary of machine-checkable
facts decays silently, and the decay is invisible to every check that reads the facts rather than the
summary.**

**What is actually left is two items**, both genuinely open:

**A documented unbuilt item is not a defect. An undocumented one is.** These five were named by
iteration 10's readers, adjudicated, assigned, and **deliberately not built**, because the fix waves
had reached the point of producing defects of the class they were removing and the convergence
signal had already fired. Each is recorded with what it would change, so the next session inherits a
list rather than a rediscovery.

| Item | What is unstated today | What building it would change |
|---|---|---|
| **An invalid `format_id` has no published sentence** | `P-ADM-07` precondition 6 states the rule, its nine-row exception table has no row for it, and `SCR-ADM-03` publishes no error string | Words an admin reads. The status and code resolve by rank 1, so this is a copy gap only — but every other required select on that surface has a published sentence |
| **Seat `row_label` is unique and unnormalised** | `(screen_id, row_label, seat_number)` is unique, and `row_label` goes through no normalisation — so `C12` and `c12` are **two seats a person reads as one** | **This one reaches further than the others and is the reason it is listed rather than buried.** A seat label is printed on the receipt and read at the door, so two seats a person cannot tell apart is a person in the wrong seat. It was **deliberately not fixed with the category-name rule**, and the reasons are why it needs its own adjudication rather than the same one: the normalisation would have to be **upper**-case, not `lower(trim())`, because row labels are conventionally uppercase — so it changes **what is stored**, not only what collides — and `P-ADM-14` **freezes `row_label` once a showtime exists**, so a normalisation applied later cannot correct a row already stored. That makes it a one-way door on existing data. **And the door has a deadline, not only a direction**: normalising `row_label` is cheap on a hall with no showtimes and impossible on one that has them, so the cost rises the moment the first showtime is created on the first hall — **Phase 2, not Phase 6** |

**Two of iteration 10's admin items were built rather than deferred**, because their consequences
reach a rendered surface: name uniqueness normalising to `lower(trim(name))` everywhere — without
which two categories a person reads as one name put **two legend rows on every seat map**, and a
legend is the primary non-colour carrier of price band — and the currency symbol, without which one
admin screen prints `Rs 281.25` while the seat map behind it prints `₹281.25` for the same
computation.

### S8.6.14 A method finding worth more than most of the fixes

**A table assembled by reading for a shape claims a completeness it never had. A derived one does
not.**

Two instances, both from the same lane, both measured rather than asserted:

- Told to fix every place a submitted property is described as *"ignored"*, scanning for the word
  returns **20 lines, 13 of them unrelated — and misses three real sites, because none of the three
  contains the word.** All three were in one family, each phrased differently. Deriving the set from
  what the rule is *about* — every row declaring that a submitted property is not accepted — returns
  **seven**, and is closed under the policy.
- Told that two endpoints lacked a path-parameter `422`, parsing every block and taking
  `request.path_params` showed **one already had it and the other has no path parameter at all**,
  while the two real gaps were endpoints the brief never named.

The same lane then wrote its completeness check as a derivation rather than an eyeball: parse every
block, assert each body-carrying one declares the status and carries the code, assert no surviving
claim that a property is ignored. **That check can fail. A reader's confidence cannot.**

### One correction produced two answers that look identical and are not

Worth recording because `S1.5` transcribes worked examples directly into tests, and this is how a
real test gets deleted as redundant.

`P-ADM-11`'s corrected example now yields **1** twice — once for the rejected narrow reading, once
for the reversed cut-off direction — and **the two ones arrive by different routes.** The rejected
reading loses two showtimes because it tests the **start instant** instead of the cut-off. The
reversed direction loses the same two because **the cut-off itself moved ahead of them**. Same total,
different cause, and **only one of the two is a defect**.

Without that written at the site, two tests asserting `1` read as duplicates, somebody removes one,
and the surviving test no longer covers the thing it was written for. **Two tests that agree on a
number are not necessarily testing the same thing** — which is a general property of transcribing
examples into assertions, not a fact about this row.

---

## S8.7 Article X rows this document proposes — **not filed, and not decided**

Fourteen questions surfaced that no source answers. **None is written into `CONSTITUTION.md`: raising an
Article X row is the client's, and `CONSTITUTION.md` is outside this goal's write-set.** They carry a
`PROPOSED-` prefix precisely so they cannot be mistaken for filed rows, and every one of them is a
place this document **refused to invent an answer**.

| Proposed row | The question | Class |
|---|---|---|
| `PROPOSED-SEATMAP-DEGRADED-01` | What the seat map shows for a **held** seat while Redis is unreachable. Holds exist only in Redis, so a degraded map cannot know about them (`X-6`) | product |
| `PROPOSED-RPTIMMUT-01` | A showtime's film or start time edited after bookings exist rewrites reported history, which `R-RPT-04` forbids (`X-13`) | reserved: reporting integrity |
| `PROPOSED-RPTSCOPE-01` | A manager-to-screen assignment has no validity period, so a manager assigned today reads that hall's entire financial history and one removed loses last month's | reserved: access to financial data |
| `PROPOSED-TURNAROUND-01` | The minimum gap between two showtimes in one hall. **No source states a figure and none is invented** — this is the exact shape of the seven-minute failure | product |
| `PROPOSED-PRICEBOUND-01` | An upper bound on a base price and on a category uplift. A mistyped ₹25,000 for ₹250 is currently accepted | reserved: money |
| `PROPOSED-ADMINRATE-01` | Rate limits for admin endpoints. `FR-ADR-058`'s table lists none, and the poster upload writes to a 5 GB allowance with no deletion path | product |
| `PROPOSED-FORMAT-01` | What a "format" is and which formats exist. `SRC-001 §5.1.3` requires the filter; no record defines the values, and they are admin-supplied content | product |
| `PROPOSED-SORT-01` | Which sort orders a customer may choose. A customer-chosen sort is required; none is enumerated | product |
| `PROPOSED-BRWVIS-01` | A showtime whose film left its display window or was unpublished, with unsold seats — does it keep selling? | product |
| `PROPOSED-ADMINCOUNT-01` | How a second admin account is created. No endpoint was invented and no role selector exists | reserved: access control |
| `PROPOSED-SEATBATCH-01` | Whether a seat-layout generator exists, given that a mistyped seat label becomes permanent once a showtime is created | product |
| `PROPOSED-SEATMAP-DEGRADED-01` | *(answered in effect by `X-7`, and kept)* Should a seat map be served that cannot show holds? The rate limiter's fail-closed behaviour makes the endpoint answer 503 before the question arises — **but the question itself was never decided, and it returns the moment that limiter changes** | product |
| `PROPOSED-CACHE503-01` | *(answered by `X-7`, and kept)* The `FR-ADR-028` / `FR-ADR-058` conflict itself: two `APPROVED` records disagreeing about one endpoint. Resolved here as the stricter option, and recorded because a build session may not re-open an immutable record | build session, escalated |
| `PROPOSED-CINEMA-01` | **How a second venue is created.** One cinema exists and the seed inserts it; the admin may edit its name and zone but **cannot create another**, because a second venue turns the customer cinema filter back on and reopens manager scoping — a scope change reserved to the client. Fail-closed: no endpoint, no control, not even a disabled one | reserved: scope |
| `PROPOSED-MGRBOOK-01` | **May a manager buy a ticket** — and specifically, may they buy a seat in a hall whose takings they report on? Two lanes read it opposite ways (`X-5a`). No source addresses it, and the conflict-of-interest question nobody has asked is the reason it is raised rather than settled | reserved: access control |

**Two of these exposed a blind spot in the repository's own consistency checker**, and it is recorded
because it is the kind of hole that looks like a pass. Rule 2 matches an id with the pattern
`OPEN-[A-Z]+-\d+`, which **cannot match a two-hyphen name** — `OPEN-SEATMAP-DEGRADED-01` and
`OPEN-CACHE503-01` were invented by lanes, referenced in the document, filed nowhere, and **sailed
through a green rule 2** because the regex never saw them. Both are renamed to `PROPOSED-` here, so
every `OPEN-` id in this document is a genuinely filed Article X row. **The checker is outside this
goal's write-set and is not amended**; the widening of that pattern is raised for whoever owns
`tools/`.

**The four real `OPEN` rows are untouched and undecided**: `OPEN-EMAILFAIL-01`, `OPEN-SHOWCANCEL-01`,
`OPEN-ATTRIB-01`, `OPEN-TLS-01`. **No sentence anywhere in this document tells a customer whose
receipt definitively failed what has happened to them**, and that absence is deliberate, checked, and
stated on the screen specification itself so nobody fills it in later.

## S8.8 What this document could not fix, and did not

- **Three `CONSTITUTION.md` clauses are stale** — Art I.6 (the win condition still describes a
  scannable ticket and a scheduled import), Art V.8 (refunds described as open when both were ruled),
  Art VIII.13 (the outbound list still names the withdrawn movie source). Amending the Constitution is
  reserved to the client (Art XII.1). **Raised, not edited.** The corrected win condition is in `S2.1`
  and the corrected outbound list in `S7`.
- **`FR-ADR-027` contains a stale count** — it says *"Five figures on this project are still
  `ASSUMED`"* and then names three. It is a residue of the corrected 36/3/1 miscount. `APPROVED`
  records are immutable (Art III.3), so it is reported here and not touched.
- **Four design-system defects** (`S8.5.3`), outside the write-set.
- **`FR-ADR-002` and `FR-ADR-073` are cited nowhere in this document**, and that is correct rather
  than an omission: the first records a document-numbering divergence and the second is a
  design-system theme decision. **71 of 73 records are cited**, and `included_in_prd` was flipped for
  exactly those 71 — **derived from the citations actually present, never asserted.**
