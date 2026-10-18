# FrontRow — Negative Testing: the attack plan

> **Compressed per SRC-004 R-1.** The client chose one lighter pass over `GOAL_09`–`GOAL_13`, with
> the cost stated. This goal still writes every artefact and its gate output. What the compression
> cost is listed in §6, not hidden. **Nothing in this folder has been executed**: no application
> code exists yet, so every case is a plan with an expected result, not an observed one.

| Artefact | What it holds |
|---|---|
| `SIT_NegativeCases.tsv` | 102 cases in 8 families. Each case names the defect it would catch |
| `OVERSELL_COVERAGE.tsv` | 13 code paths that can mark a seat sold, each with its severity-one cases |
| `check_negative.py` | The consistency check. `py "docs/09 NegativeTesting/check_negative.py"`. **A recorded deviation from the goal's write-set**: `GOAL_11` lists only the two TSVs, this file, `PROGRESS.md` and `handoffs/`. The check was added so the counts in this file are derived, not typed. Reversible: delete the file |
| this file | For each family: the plan, what was **not** tested and why, the findings, and the open questions |

**Sources read:** `CLAUDE.md`, `CONSTITUTION.md` Art IV–VI, `GOTCHAS.md` (concurrency, Redis, money,
web), `SRC-004`, the PRD seat state machine (`P-SEA-06`, §S8.4) and confirm transaction order
(`P-PAY-10`), `docs/03 PRD/api/contract.json`, the Bible (`docs/05 Bible/FrontRow_Bible.csv`),
`docs/06 DataModel/schema.sql` **as it stood at 2026-10-18 while another lane was still editing
`datamodel.json`**, and `docs/11 Journeys/DEFECTS_FOUND.tsv`.
The first pass was written before `docs/07 Architecture/for_llm/03_concurrency_model.md` existed,
from the PRD state machine. **The model has since landed and this plan has been diffed against it:
§2b lists every item it names and the case that answers it.** `SRC-004`'s judgment calls JC-R6-01
and JC-R6-03 and R-5's length ruling were read in the same pass.

---

## 1. The one thing: two customers and one seat

Everything else in this product can be repaired after the fact. A seat sold twice cannot be.

**The severity-one count, worst number first: 33 of 102 cases are severity one.** 66 are S2 and 3 are S3. *(This line first read 39, 47 and 4: typed, not derived, and wrong. It then read 36 of 90 before the regrade below, and 32 of 98 before the second concurrency-model diff added four cases (§2b). `check_negative.py` fails if this sentence disagrees with the case file.)*
Severity one is used only for the five harms `GOAL_11` names: a seat sold twice, a customer charged
twice, a customer charged and not given a seat, one customer seeing another customer's booking or
payment data, and a non-manager reading a cinema's revenue. **Every S1 case names its harm** as a tag
in its `Invariant` cell (`seat-never-sold-twice`, `never-charged-twice`, `never-charged-without-seat`,
`own-data-only`, `revenue-manager-only`), and `check_negative.py` fails an S1 case that names none.

**The test for S1:** the case's own scenario, with the defect present, puts one of the five harms in
reach, and the expected result asserts its absence (a database count, or the response content). Five
cases failed that test and were **regraded S1 → S2**, for a reviewer to reverse:

| Case | Why it is not one of the five harms |
|---|---|
| `NC-CON-06` | Expired hold, nobody else wants the seat. Skipping re-validation sells a seat with no hold, but nobody is sold the same seat and nobody is charged wrongly |
| `NC-CON-16` | The stress script proving its own concurrency. The scenario runs a deliberately serialised build; no harm happens inside it. It protects the proof, not a customer |
| `NC-MON-12` | Same key, different request. The defect silently does not book the second hold, or books it. Neither is a double charge for one purchase |
| `NC-DEP-07` | SQS slow inside the confirm. The customer is charged **and** given the seat; what they lose is the on-screen reference until the receipt arrives |
| `NC-DEP-08` | SES fails after capture. The booking exists and the reference is on screen (`S-TKT-04`). The goal stresses this one, and `OPEN-EMAILFAIL-01` may make it worse; it is the most reversible call in this table |

Considered and **kept at S1**: `NC-CON-17`. Its defect now includes an upsert that moves a sold seat
to another booking, which leaves the first customer charged and not given a seat. Considered and
**kept at S2**: the `LEAK` family. A leaked reset token is an account takeover, but the person who
reads a log is an operator, not another customer.

**Harm tags now mean severity one.** `NC-AUZ-13` (re-send another customer's receipt) and `NC-DAT-03`
(reference enumeration) were S2 but carried the `own-data-only` harm tag. Neither shows one customer
another's booking data: the re-send goes to the owner's own address, and an unowned reference answers
exactly like a non-existent one. What each guards is the reference not becoming an existence oracle, so
both now carry `reference-not-an-oracle` and stay S2, for a reviewer to reverse. `check_negative.py`
now fails (`harm-grade`) any S2 or S3 case that carries one of the five harm tags.

**Every path that can mark a seat sold has at least one severity-one case: 13 paths, 0 uncovered.**
The paths are worked out from three sources. `S-SCP-11` says exactly two modules may insert
`booking_seat`: the domain confirm and `scripts/seed.py`. `FR-ADR-029` gives the order of the confirm
transaction. `P-SEA-06` lists every input that ends in `sold`. So the paths are different ways into
those two inserts, plus the schema path that could take the guard away. They are not 13 separate
pieces of code.

| Path | In one line | The guard that has to hold |
|---|---|---|
| OP-01 | A normal confirm by the one live holder | Redis re-validation + `uq_booking_seat` |
| OP-02 | Two or more live holders. Redis is wrong by construction | **the constraint alone** |
| OP-03 | A hold that is no longer the caller's: expired, re-taken by someone else, or stolen | token compare + owner check |
| OP-04 | The same Idempotency-Key is replayed | `uq_idempotency_record`, which is inserted first |
| OP-05 | A new key for a hold that is already being used (two tabs, or a key minted per click) | release ordering + constraint |
| OP-06 | A hold is granted on a seat that is already sold | sold check on the hold path + constraint |
| OP-07 | A seat or showtime from outside the hold's seat set | **application validation only** (F-1, F-2) |
| OP-08 | A process dies or a dependency drops, then the confirm is retried | one transaction + replay + constraint |
| OP-09 | A manager or admin confirms through the same endpoint | no role bypass |
| OP-10 | The seed writes rows directly | the constraint alone |
| OP-11 | A third module starts writing `booking_seat` | the `S-SCP-11` origin test |
| OP-12 | A migration or restore recreates the table without the guard | `pg_constraint` asserted after every migration and restore |
| OP-13 | A unique violation is handled by exception class, not by constraint name | routing by constraint name |

**The two paths whose guard is the constraint alone (OP-02, OP-10) are the reason the red-proof
(`NC-CON-03`) cannot be waived.** With Redis healthy, the database guard never fires, so no normal
test can tell a present constraint from a missing one.

---

## 2. The families

### CONCURRENCY

**Plan.** `NC-CON-01` to `NC-CON-22`. They cover 50 simultaneous holds on one seat, ten live holders
confirming at once, and the red-proof. They also cover a hold racing a confirm, two confirms with the
same key at the same instant, a confirm after the hold expired, and a confirm on a seat someone else
now holds. Then come a release by a client that does not own the lock, a stolen hold token, the lock
TTL expiring mid-transaction, and Redis returning stale state. Last come all-or-nothing multi-seat
holds, locks with no TTL, a third module that writes the seat table, the constraint surviving a
migration round-trip, and unique violations routed by exception class. Two came from the
concurrency-model diff (§2b): a hold TTL that re-selecting or polling extends (`NC-CON-20`,
`FR-ADR-027`), and overlapping multi-seat holds sent in opposite order (`NC-CON-21`). The second diff
added `NC-CON-22`: a partial win in which one seat was already the caller's, where the release must
compare-and-delete only the seats this request's `SET NX` won.

The race that matters most is the gap between FR-ADR-029 step 2 (re-validate in Redis) and step 7
(insert). It is a time-of-check to time-of-use window, and `PAYMENT_SIMULATED_DELAY_MS` holds it open
on purpose. `NC-CON-10` stretches it until the lock expires inside the window. Each concurrency case
has to run from separate processes on separate connections, and the run has to report its own start
spread (`NC-CON-16`). A script that serialises its own requests passes against broken code.

**Not tested:**
- **Clock skew between API instances.** Lock expiry is decided by Redis's clock, not by an instance's
  clock, and FR-ADR-047 makes the client countdown display-only. So there is no instance clock left
  to skew. Written down as "we could not build a case that changes an outcome."
- **Redis Cluster slot migration or replica lag.** ElastiCache here is a single node with no replica
  (GOTCHAS Redis). The topology does not exist, so a case would test nothing.
- **More than 50 concurrent requests.** 50 is the number the source sets (`SRC-002 §9.1`). Peak
  concurrency is `OPEN-SCALE-03`, which is **ASSUMED**, so a bigger number would harden an assumption.
- **The deployed run.** `stress_seats.py` reaches the deployed environment by changing a base URL.
  That stack does not exist, so every case here is local-only. Nothing about AWS behaviour has been
  observed.

### MONEY

**Plan.** `NC-MON-01` to `NC-MON-16`. They cover a double submit, a refresh mid-payment, payment
captured and then the confirm failing, the capture failing, a price change between the seat map and
the confirm, zero or negative quantities, more than 10 seats (including a race on the cap), integer
overflow, float money, rounding at .5 and at an uneven value, card data, a reused key with a different
request, another user's key, and the simulated provider reachable without its flag. The second
concurrency-model diff added a seat re-selected into its own hold being priced once (`NC-MON-15`, S1:
priced twice, the customer pays twice for one seat) and duplicate seat ids in one body (`NC-MON-16`).

`NC-MON-10`'s worked inputs are picked so the rule is actually exercised. Banker's rounding gives 2
for 2.5 paise and half-up gives 3, so the case fails against `round()`.

**Not tested:**
- **Refunds, cancellation and partial capture.** They are out of scope (`SRC-003`), and refund
  behaviour is reserved (`OPEN-CANCEL-01/02`). A case would invent a rule.
- **A real provider's webhooks and settlement timing.** No real provider will ever be integrated
  (`OPEN-PAY-01`).
- **Currency other than INR.** It is ruled (`OPEN-LOCALE-01`) and the ratio is a one-way door. A case
  that switches it would test a change nobody may make.
- **Reasoned, not tested:** the confirm captures payment at step 6 and only then meets the constraint
  at step 7. With the simulated provider, a rollback removes the capture (`NC-MON-03`). **With a real
  provider, this order is "charged and not given a seat" every time the constraint fires.** That is a
  property of the specification, filed as F-6. It is not a case, because the provider does not exist.

### AUTHZ

**Plan.** `NC-AUZ-01` to `NC-AUZ-18`. Every cross-role case asserts both halves: a denial for the
forbidden actor, and a **non-empty, non-zero** result for the permitted one. A denial-only test passes
against a query that returns nothing for anybody (Art VI.5, VI.7). **14 cases are cross-role (12 here
plus `NC-CON-09` and `NC-MON-13`), and 0 are missing the positive half.**

Manager scope is attached to the **screen**, not the cinema. There is one cinema (`SRC-003 C-2`,
PROVISIONAL), so scoping by cinema would scope nothing. The admin write-route sweep (`NC-AUZ-06`)
reads its route list from `contract.json` when it runs, so a new route is covered without anyone
editing the test.

**Grading note, for a reviewer to reverse:** a manager reading a screen they are not assigned to
(`NC-AUZ-03`) is graded **S2**, not S1. The S1 definition names "a **non**-manager reading a cinema's
revenue." A customer or guest reading revenue is S1 (`NC-AUZ-01`, `-02`).

**Not tested:**
- **"A token for a deactivated account."** v1 has no deactivation. `users` has no active flag, and no
  endpoint deactivates an account. The nearest real case is a session that should have been revoked
  by a password reset (`NC-AUZ-10`). Adding deactivation is a scope change.
- **Staff routes, a cinema-level manager scope, and door validation.** These were deleted by `SRC-003`
  (see the goal file's 2026-08-22 corrections). There is nothing to attack.
- **`/metrics` exposure.** Access is controlled by not routing it, which is Zone C (`EP-XCT-03`). It
  cannot be tested until the client's ALB exists, so this is unverified.
- **Whether a manager may buy a ticket.** `PROPOSED-MGRBOOK-01` is unruled. `NC-AUZ-17` asserts only
  that a manager confirm gets no bypass of the seat guard. It does not assert that managers may book.

### DATA

**Plan.** `NC-DAT-01` to `NC-DAT-13`. They cover a seat from another screen, a showtime that does not
match the hold, guessing references, the same reference presented twice at the door, a booking after
the advertised start, row labels (lower case, the letter I, Unicode case folding, and any non-ASCII
character, which `SRC-004 JC-R6-03` rules out: `NC-DAT-12`), a wrong check character, the alphabet,
length and check function across generated and seeded references, the seed running against live
confirms, and the reference generator running out of its five draws after capture (`NC-DAT-13`).

`NC-DAT-05` asserts the booking is **ACCEPTED** at start + 10 minutes. Sales close 15 minutes
**after** the advertised start (`OPEN-BOOK-03`, PROVISIONAL). One message from the client reverses
this, and the case flips with it.

**Not tested:**
- **What happens at the door when one reference is presented twice.** That is `OPEN-DUPREF-01` and
  it is not ours to decide. `NC-DAT-04` only asserts that nothing was built for it without a ruling.
- **A reference length other than 8.** `SRC-004 R-5` fixes it at 8 by a `[JUDGMENT CALL]`: 7 random
  characters plus 1 check character, shown as `FR-XXXX-XXXX` (Q-4, answered). `NC-DAT-10` asserts 8.
  A 9-character reading was rejected, so no case is written for it.
- **Seat-category name collisions.** The names are `OPEN-SEAT-01`, **ASSUMED**. A case would harden
  the assumed names.

### DEPENDENCY

**Plan.** `NC-DEP-01` to `NC-DEP-18`. They cover Redis down during a hold, during a confirm, during
a seat-map read (`NC-DEP-17`, from §2b), and on the error path itself. They cover Postgres down mid-confirm and a connection lost during COMMIT. They
cover SQS being unavailable, and SQS being slow **inside** the confirm (J-ENT-04). They cover SES
failing after capture (`OPEN-EMAILFAIL-01`), and SES accepting a message that then bounces (J-ENT-03).
They cover SIGTERM mid-request with locks held, SIGKILL before and after commit, a worker redelivery,
live versus ready, migrations on boot, and stateless containers. `NC-DEP-18` (second §2b diff) is
PostgreSQL down during a hold.

**Not tested:**
- **What the customer is told when the receipt email fails.** That is `OPEN-EMAILFAIL-01`.
  `NC-DEP-08` asserts that the reference is on screen and that a retry exists. It writes no wording.
- **Bounce detection.** Nothing subscribes to SES bounces, and building that is scope.
  `NC-DEP-09` asserts that the limitation is documented and that nothing claims "delivered."
- **ElastiCache, RDS and SQS failover in AWS.** These are Zone C and nobody has observed them. Every
  dependency case runs against local containers, with toxiproxy where latency is needed.
- **The value of the SQS send timeout.** No document specifies it (J-ENT-04). `NC-DEP-07` asserts
  that a named bound exists and is respected. It does not pick a number.

### ABUSE

**Plan.** `NC-ABU-01` to `NC-ABU-04`. They cover a rate limiter keyed on the load balancer, a hold
loop that never confirms, poll flooding together with a cache stampede, and credential stuffing.

**Not tested:**
- **The real ALB `X-Forwarded-For` chain.** It is tested locally behind a proxy. The deployed
  behaviour is unverified until the client builds the ALB.
- **A defence against many accounts exhausting a hall.** Registration is free, so 20 accounts at
  10 seats each fill a 200-seat hall for as long as they keep re-holding. No defence is ruled, so it
  is filed as Q-3 rather than invented.
- **Volumetric denial of service.** That belongs to the network edge, which is Zone C.

### LEAK

**Plan.** `NC-LEK-01` to `NC-LEK-09`. They are built for `SRC-004 R-3`: the reset token rides in the
queue message only and is never logged or stored. The cases look for the token in every database
column, in every log line (including exception paths), in the queue and dead-letter retention, in the
relay path that cannot carry it, in access logs, and in a redelivery that sends two emails.
`NC-LEK-08` holds `SRC-004 JC-R6-01`: a failed reset send is **not retried**, and the token is in no
column, Redis key or log line afterwards. `NC-LEK-09` follows the `?token=` link through nginx and
the ALB, whose access logs record the query string. `NC-LEK-07` (from §2b) checks that the hold token,
which sits in a URL path, is logged as the route template only.

**The probes are built at run time.** No case in this folder carries a literal token, card number or
other credential-shaped value. `NC-MON-11` describes its card probe ("a 16-digit Luhn-valid number
the test builds") instead of quoting one, and `check_negative.py` fails on any 13-19 digit run in
this folder, written solid or with a single space or dash between digits.

**Not tested:**
- **The token in SES's own systems or in the recipient's mailbox.** It has to be there, because that
  is how the link reaches the customer. It is outside this system.
- **Deployed SQS retention and dead-letter configuration.** These are Zone C, and unverified.
  Requested of `docs/30 Deployment`.

### TEST-HYGIENE

**Plan.** `NC-TST-01` and `NC-TST-02`. They cover a test that reads the wall clock (a scan, then two
faketime runs either side of midnight Asia/Kolkata) and a test that is skipped, xfailed or deleted.

**Not tested:**
- **Whether the suite's assertions are strong enough.** Only a reviewer and a mutation run can show
  that, and neither exists yet. Recorded as a gap.

---

## 2b. Diff against `07 Architecture/for_llm/03_concurrency_model.md`

Every behaviour the model states, and the case that attacks it. **New** means the item had no case
before this diff. Done by a later session of the same workflow, not by a zero-context reviewer (§6).

| What the model says | Case | |
|---|---|---|
| The lock is `SET key token NX PX ttl`, never `SETNX` then `EXPIRE` | `NC-CON-01`, `NC-CON-13` | |
| nil → `GET`; my token → already mine, **TTL NOT extended**; never extended by re-selecting or polling (`FR-ADR-027`) | `NC-CON-20` | **new** |
| Token reuse for an existing live hold keeps its `expires_at` (`P-HLD-01` step 4) | `NC-CON-20` | **new**; the added seat's TTL is Q-5 |
| Seats are sorted ascending, so two overlapping requests produce one clean loser | `NC-CON-21` | **new** |
| Partial win → compare-and-delete what this request won; 409 names the lost seats | `NC-CON-12` | |
| Partial win where one seat was **already mine**: release only the seats this request's `SET NX` won, never the earlier one | `NC-CON-22` | **new** (second diff) |
| Body validation: 1..10 **distinct** seat ids, all in this showtime's seat set, before Redis is touched | `NC-MON-16`, `NC-MON-06`, `NC-DAT-01` | **new** (second diff): `NC-MON-16` |
| Price **only** the seats this request added; append them to the hold record | `NC-MON-15` | **new** (second diff) |
| Every key a hold writes (lock, `hold:{token}`, `holds:user:…`, instance registry) carries a TTL, so a process that dies mid-hold leaves nothing permanent (`FR-ADR-026`) | `NC-CON-13` | attack extended (second diff) to the hold record and the per-user set |
| A won seat with a `booking_seat` row is treated as lost (a sold seat leaves no key) | `NC-CON-04`, `NC-CON-14` | |
| The 10-seat cap counts `holds:user:{u}:showtime:{s}` | `NC-MON-07` | |
| Cut-off checked at hold against the injected clock, not re-checked at confirm | `NC-DAT-05` | |
| Price fixed at hold time, confirm never recomputes | `NC-MON-05` | |
| Release is the compare-and-delete Lua script; a wrong token deletes nothing | `NC-CON-08` | |
| The hold token is in a URL path, so the access log records the route template, never the raw path | `NC-LEK-07` | **new** |
| Redis unreachable at any hold or confirm step → 503, no PostgreSQL substitute | `NC-DEP-01`, `NC-DEP-02`, `NC-DEP-03` | |
| Redis down: the seat map is served from PostgreSQL, held seats show as available | `NC-DEP-17` | **new** |
| Confirm step 1: idempotency record inserted first; same / in-flight / different fingerprint | `NC-CON-05`, `NC-MON-01`, `NC-MON-12`, `NC-MON-13` | |
| Step 2 re-validation: hold exists, belongs to the user, every lock still holds this token | `NC-CON-06`, `NC-CON-07`, `NC-CON-09` | |
| Step 2 to step 7 time-of-check to time-of-use window | `NC-CON-10` | |
| Step 6 capture rolls back with the transaction | `NC-MON-03`, `NC-DEP-04`, `NC-DEP-11` | |
| Step 7 reference: **up to 5 draws** (`P-TKT-01`), after capture | `NC-DAT-13` | **new** |
| Step 7 seat violation → 409, not retried, **logged as an expected outcome with a counter, not an exception** | `NC-CON-19` | expected result extended |
| Release after commit, not before or inside | `NC-CON-04`, `NC-DEP-12` | |
| After commit: delete `hold:{token}`, remove it from the per-user and instance sets; if that fails the keys expire and the database refuses anyone else | `NC-DEP-12` | mapped (second diff) |
| Redis hands out two holds with no bug in our code: a restart that comes back empty, an eviction under a wrongly set policy, a release-path bug | `NC-CON-11` (restart, flush), `NC-CON-02` and `NC-CON-03` (eviction, modelled by `DEL`), `NC-CON-08` (release bug) | mapped (second diff) |
| `SELECT ... FOR UPDATE` is not the guard; the unique constraint is total, with no partial predicate | `NC-CON-02`, `NC-CON-18` | mapped (second diff) |
| Seat-map rebuild lock, the stampede guard | `NC-ABU-03` | mapped (second diff) |
| Confirm step 3: `SELECT ... FOR UPDATE` on the showtime serialises against an admin edit | `NC-MON-05` | mapped (second diff); the visible outcome is the snapshot price |
| Step 6 payment failure → `402`, everything rolls back | `NC-MON-04` | mapped (second diff) |
| Steps 9–11: `receipt_dispatch`, outbox row and idempotency completion inside the same transaction | `NC-DEP-05`, `NC-DEP-06` | mapped (second diff) |
| Confirm with Redis down is `503`, not "constraint only" (`FR-ADR-028`) | `NC-DEP-02` | mapped (second diff) |
| The crash window: captured at step 6, process dies before commit | `NC-DEP-11` | mapped (second diff) |
| PostgreSQL down: hold `503` at the `booking_seat` read; seat map `503` unless cached | `NC-DEP-18` | **new** (second diff); whether won locks are released at once is Q-6 |
| Fast-path relay under `QUEUE_SEND_TIMEOUT_MS`; the 201 goes out whatever happens | `NC-DEP-06`, `NC-DEP-07` | |
| SIGTERM: drain, read `instance:{id}:holds`, compare-and-delete, exit | `NC-DEP-10` | |
| Stage A: 50 **distinct** customers so the rate limit cannot decide; 49 × `409 SEAT_UNAVAILABLE`; one row **counted in PostgreSQL** | `NC-CON-01`, `NC-CON-16` | expected result extended |
| Stage B red-proof: inject the eviction by `DEL`; one row means DRILL VOID; verify the restore by catalogue | `NC-CON-02`, `NC-CON-03`, `NC-CON-18` | |

**Considered and not added:**
- **The ECS stop timeout shorter than deregistration delay plus drain.** That is Zone C. Correctness
  survives because the keys expire; the model says so itself. It belongs in `docs/30 Deployment`.
- **`READ COMMITTED` instead of `SERIALIZABLE`.** The model chose it because the constraint holds at
  every isolation level. `NC-CON-02` already runs at whatever level the code uses, so a separate case
  would test nothing more.
- **The hold token's 43-character format bound.** It is input validation, not a concurrency attack.
  The positive suite (`08 SIT`) owns it.
- **`cache:listing:generation` and the rate-limit bucket keys.** They carry no seat state.
- **`DEL cache:seatmap:{s}` after a hold, a release and a commit.** The model accepts a seat map up to
  10 s stale, and no sale is decided by the map: the hold and the constraint decide. A missing `DEL`
  is staleness inside the stated bound. The positive suite (`08 SIT`) owns it.
- **Step 8, no audit row for a customer booking.** Asserting an absent row is a positive-suite check,
  and nothing concurrent changes it.
- **The hold response carrying the whole hold.** Response shape, owned by `08 SIT`.
- **The stress script taking a base URL.** Covered by CONCURRENCY's "Not tested: the deployed run".
- **"No application test seam is needed."** A statement about how the drill is built, not a
  behaviour the application has.

---

## 3. Findings: filed, not fixed

| # | Finding | Evidence | Belongs to |
|---|---|---|---|
| F-1 | **No database guard ties a sold seat to the showtime's seat set.** `booking_seat` has foreign keys to `seat` and `showtime` separately, and none to `showtime_seat (showtime_id, seat_id)`. A seat from another screen can be sold against this showtime, and only application validation stops it (OP-07) | `schema.sql` at 2026-10-18: `fk_booking_seat__{booking_id,seat_id,showtime_id,seat_category_id}`, no composite | `06 DataModel` |
| F-2 | **No database guard says `booking_seat.showtime_id = booking.showtime_id`.** The unique constraint guards the seat row's showtime. If the two disagree, the ticket names a showtime the guard does not protect | same | `06 DataModel` |
| F-3 | **A weighted sum mod 26 cannot do what SRC-004 R-5's filing says it does.** The filing (build-session text, not client text) proposes a weighted mod-N check over the 26-character alphabet that "catches every single-character substitution and every adjacent transposition." Mod 26, catching every substitution at a position needs that weight to be odd and not 13. Catching every transposition of a pair needs the difference of the two weights to be odd too. Two odd weights always have an even difference. **The output of the run below shows 0 weight pairs that satisfy both conditions.** A quasigroup-based check such as Damm's, which works over orders other than 2 and 6, is one candidate. A sampled run of an ISO 7064 hybrid MOD 27,26 written for this check missed 140 of 43,227 transpositions (that implementation is unverified, so the figure is unverified as well). **The algorithm stays the implementing lane's `[JUDGMENT CALL]`. `NC-DAT-10` is the gate it has to pass** | the run is pasted in §5 | Phase 4 implementer |
| F-4 | **The reset link carries the token in a query string**, and the static frontend container's default access log records the request line. That puts the token in a log, against R-3. **The ALB is worse**: its access logs, when enabled, record the full request URL including the query string, and cannot be told to drop it. Only the link form (for example a URL fragment, which browsers never send) or logging switched off keeps the token out (`NC-LEK-09`). Choosing between them is not this lane's | `S-ACC-07` link form; R-3 | Zone B static container (`docs/30 Deployment`); the link form is the PRD/Bible owner's |
| F-5 | **`S-TKT-15` still says "the token value never travels in the queue."** `SRC-004 R-3` reversed that. The Bible row now contradicts a client ruling, and the ruling wins | `FrontRow_Bible.csv` S-TKT-15 | Bible owner |
| F-6 | **Capture comes before the constraint** (FR-ADR-029, steps 6 then 7). This is harmless with the simulated provider. With a real one, every constraint violation would leave a customer charged and not given a seat. The drop-in claim (Art V.5) does not hold for this order | PRD `P-PAY-10` order table | ADR owner / client, if a real provider is ever ruled in |
| F-7 | **No database guard holds `row_label` to ASCII `A`–`Z`** (`SRC-004 JC-R6-03`). `ck_seat__row_label_upper` passes any character that is its own upper case, so a Cyrillic `С` (U+0421) or a fullwidth letter can be stored by a direct insert and sit beside a Latin `C` that reads the same on the wall. Only application validation stops it (`NC-DAT-12`) | `schema.sql` at 2026-10-18: only `ck_seat__row_label_upper` on `row_label` | `06 DataModel` |

## 4. Open questions: raised, not answered

| # | Question | Why it is open |
|---|---|---|
| Q-1 | **When the fast-path send of a reset message fails, what does the customer get?** R-3 puts the token in the queue message and forbids it in any database column, including the outbox. So the outbox relay has no token and cannot send a working link | **Answered by `SRC-004 JC-R6-01`** (build-session judgment call under R-6, for the client to reverse): the send is not retried, the customer sees the same 202 sentence and asks again. Tested by `NC-LEK-08` |
| Q-2 | **Which characters may a row label contain?** EP-ADM-19 says "1..4 letters". It does not say ASCII. Python and PostgreSQL upper-case `ı` and `ß` differently | **Answered by `SRC-004 JC-R6-03`**: ASCII `A`–`Z` only. Tested by `NC-DAT-12`; the missing database guard is F-7 |
| Q-3 | **Is there any defence against many free accounts holding a hall indefinitely?** | No source or ruling addresses it. Scope and abuse policy are reserved |
| Q-4 | **Is a reference 8 characters plus a check character (9 in total), or 8 including it?** | **Answered by `SRC-004 R-5`** (a `[JUDGMENT CALL]` in the filing): 8 including it, 7 random plus 1 check, so `FR-XXXX-XXXX` is unchanged. Asserted by `NC-DAT-10` |
| Q-5 | **When a seat is added to a live hold, does its lock take the hold's remaining TTL or a fresh 180 s?** The model reuses the hold's `expires_at` (`P-HLD-01` step 4) and sets each lock with `PX <ttl_ms>`, without saying which TTL that is. A fresh 180 s lets a lock outlive the hold record it belongs to | Not stated in `03_concurrency_model.md`. `NC-CON-20` asserts only that `expires_at` does not move |
| Q-6 | **When a hold has won its Redis locks and the `booking_seat` read then fails (PostgreSQL down), are the won locks compare-and-deleted at once, or left to expire?** The failure table says only "`503` at the `booking_seat` read". Left to expire, the seats cannot be held by anyone for up to 180 s after PostgreSQL returns | Not stated in `03_concurrency_model.md`. `NC-DEP-18` asserts only that every key left behind carries a TTL |

## 5. Gate output (pasted, not typed)

The consistency check, run 2026-10-18:

```
compressed per SRC-004 R-1 - consistency check, not a quality review
INFO  severity       S1 33 of 102 - S2 66 of 102 - S3 3 of 102
PASS  plan-sev-count   plan states ('33', '102', '66', '3'), case file gives (33, 102, 66, 3)
PASS  empty-cells      0 empty cell(s) []
PASS  unique-ids       0 duplicate id(s) []
PASS  family-prefix    0 case(s) with a family/prefix mismatch []
PASS  severity-vocab   0 case(s) outside S1/S2/S3 []
PASS  crossrole-vocab  0 case(s) with CrossRole not Y/N []
PASS  s1-harm          0 S1 case(s) naming none of the five GOAL_11 harms []
PASS  harm-grade       0 non-S1 case(s) carrying an S1 harm tag []
INFO  s1-by-harm     seat-never-sold-twice 18 - never-charged-twice 7 - never-charged-without-seat 6 - own-data-only 3 - revenue-manager-only 2
PASS  no-card-digits   0 13-19 digit run(s), solid or space/dash separated, in this folder []
PASS  positive-half    0 of 14 cross-role case(s) missing a 2xx non-empty half []
PASS  positive-stray   0 non-cross-role case(s) carrying a positive half []
PASS  oversell-cover   13 path(s), 0 uncovered by a severity-one case []
PASS  oversell-refs    0 case reference(s) to an undeclared path []
PASS  oversell-sync    0 coverage row(s) whose Sev1Cases disagree with the case file []
PASS  families         8 of 8 families have cases; missing []
PASS  named-topics     18 of 18 named topics answered by a case still on topic; failing {}
PASS  plan-families    0 famil(ies) with no section in the attack plan []
PASS  plan-not-tested  0 famil(ies) whose plan section has no 'Not tested' statement []
RESULT exit 0 (0 failing check(s))
```

The `s1-by-harm` figures add up to more than 33 because a case may name two harms.
`positive-half` now needs a 2xx status **and** a non-empty or non-zero figure, so a half that names a
figure without saying the permitted actor succeeded fails. `named-topics` now matches a pattern
against each case's Attack and ExpectedResult, so a case that keeps its id and title but is rewritten
off its topic fails.

**The second round of checks, red-proofed** (2026-10-18). `CARD_RUN` now also matches 13-19 digits
written with a single space or dash between them, `harm-grade` fails a non-S1 case carrying a harm tag,
and the "lock token theft" and "manager cross-scope" topic patterns now require the refusal, the
unchanged state and the owner's success, not just the words "token" or "manager ... screen". A fresh
copy of this folder was made in the scratchpad and five defects were planted by a script: a dashed
4-4-4-4 run and a spaced 4-6-5 run, **both all zeros and built by the script, never typed**, at the
start of two title cells; `NC-AUZ-13`'s tag set back to `own-data-only`; `NC-CON-09`'s "no key is
touched" removed; `NC-AUZ-03`'s 403 replaced with "returns an empty list"; and `NC-CON-22`'s "still
returns tA" replaced with "returns 0". The old digit pattern found 0 of the two separated runs, and the old
topic patterns still matched the `NC-CON-09` and `NC-AUZ-03` plants. The new check caught all five
(PASS lines omitted; the copy was deleted afterwards):

```
compressed per SRC-004 R-1 - consistency check, not a quality review
INFO  severity       S1 33 of 102 - S2 66 of 102 - S3 3 of 102
FAIL  harm-grade       1 non-S1 case(s) carrying an S1 harm tag ['NC-AUZ-13']
INFO  s1-by-harm     seat-never-sold-twice 18 - never-charged-twice 7 - never-charged-without-seat 6 - own-data-only 3 - revenue-manager-only 2
FAIL  no-card-digits   2 13-19 digit run(s), solid or space/dash separated, in this folder ['SIT_NegativeCases.tsv:23', 'SIT_NegativeCases.tsv:39']
FAIL  named-topics     15 of 18 named topics answered by a case still on topic; failing {'lock token theft': ['NC-CON-09'], 'manager cross-scope, both halves': ['NC-AUZ-03'], 'partial win releases only what this request won': ['NC-CON-22']}
RESULT exit 1 (3 failing check(s))
```

**The new checks, red-proofed** (2026-10-18). A fresh copy of this folder was made in the scratchpad
and four defects were planted: a 16-digit run (built by the planting script, not typed) at the start
of `NC-MON-11`'s title cell, `NC-AUZ-17`'s harm tag replaced with `authorisation`, `NC-LEK-08`'s
"not retried" changed to "retried", and `NC-AUZ-11`'s "returns 200 with a non-empty" changed to
"shows a non-empty". The check caught all four (PASS lines omitted):

```
compressed per SRC-004 R-1 - consistency check, not a quality review
INFO  severity       S1 32 of 98 - S2 63 of 98 - S3 3 of 98
FAIL  s1-harm          1 S1 case(s) naming none of the five GOAL_11 harms ['NC-AUZ-17']
INFO  s1-by-harm     seat-never-sold-twice 17 - never-charged-twice 6 - never-charged-without-seat 6 - own-data-only 3 - revenue-manager-only 2
FAIL  no-card-digits   1 13-19 digit run(s) in this folder ['SIT_NegativeCases.tsv:33']
FAIL  positive-half    1 of 14 cross-role case(s) missing a 2xx non-empty half ['NC-AUZ-11']
FAIL  named-topics     16 of 17 named topics answered by a case still on topic; failing {'failed reset send not retried (SRC-004 JC-R6-01)': ['NC-LEK-08']}
RESULT exit 1 (4 failing check(s))
```

A first attempt at this red-proof did **not** fire on two of the plants. `NC-CON-09`'s positive half
still held a second 201, and `NC-LEK-08`'s title still said "not retried" while topics were matched
against the title. The second result is why `named-topics` no longer reads the title.

**The earlier red-proof**, of the first version of the check, against the 90-case file. Three defects
were planted: the stated S1 count was changed to 37, `NC-AUZ-17` (the only S1 case on OP-09) was
downgraded to S2, and `NC-CON-09`'s positive half was replaced with "denied only". The output below
shows the check catching all three (PASS lines are omitted):

```
compressed per SRC-004 R-1 - consistency check, not a quality review
INFO  severity       S1 35 of 90 - S2 52 of 90 - S3 3 of 90
FAIL  plan-sev-count   plan states ('37', '90', '51', '3'), case file gives (35, 90, 52, 3)
FAIL  positive-half    1 of 14 cross-role case(s) missing the non-empty half ['NC-CON-09']
FAIL  oversell-cover   13 path(s), 1 uncovered by a severity-one case ['OP-09']
FAIL  oversell-sync    1 coverage row(s) whose Sev1Cases disagree with the case file ['OP-09']
RESULT exit 1 (4 failing check(s))
```

The F-3 arithmetic, run 2026-10-18 (scratchpad script, not a deliverable):

```
30 26 23456789ACDEFHJKMNPQRTVWXY
units mod 26 [1, 3, 5, 7, 9, 11, 15, 17, 19, 21, 23, 25]
adjacent unit pairs with unit difference: 0
```

## 6. What compression cost: the Definition of Done, line by line

| DoD line | State |
|---|---|
| OVERSELL_COVERAGE maps every path; uncovered = 0 | **met by the check**: 13 paths, 0 uncovered. "Every path" is as complete as the three sources in §1 allow. No code exists to enumerate the paths mechanically |
| Every case names its defect; zero empty cells | **met by the check** |
| Every cross-role case has both halves; missing = 0 | **met by the check**: 14 cross-role, 0 missing a 2xx non-empty half |
| Severity-one count stated, worst first | **met**: §1 |
| Each family states what it did not test | **met by the check**, all 8 |
| A fresh zero-context session writes its own attack list from the concurrency model, and the diff is recorded | **PARTLY MET.** The concurrency model now exists, and a later session of the same workflow diffed this plan against it (§2b): 6 items had no case, 5 cases were added for them and 2 were extended. That session was told which gaps to look for, so it was **not zero-context and not independent**. A
second pass by the same workflow mapped every remaining behaviour the model states: 4 cases added
(`NC-CON-22`, `NC-MON-15`, `NC-MON-16`, `NC-DEP-18`), 1 extended (`NC-CON-13`), 5 recorded as
considered and not added, and 1 open question (Q-6). It was also told what to look for, so it is
not independent either. **The writer has still not been verified by anyone outside the workflow** (Art VII). The substitution owed is unchanged: a fresh session writes its own list from the model, and the diff goes in the handoff |
| The write-set | **One recorded deviation:** `check_negative.py` is not in `GOAL_11`'s write-set. It was added so that §1's counts and the coverage table are derived, not typed. Reversible: delete the file. Nothing outside `docs/09 NegativeTesting/` was written |
| Adversarial review of the plan (`requesting-code-review`) | **NOT MET**, for the same reason |
| The consistency check exits 0 | **met**: §5 |
| PROGRESS.md appended; handoff written | **NOT MET by this lane.** Both are outside this lane's write-set and belong to the orchestrating session's `/tt` |
