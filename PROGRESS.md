# PROGRESS.md — append-only session log

> One block per session, so any session — any machine, any Claude account — resumes cold.
> Written by `/tt` at close. Newest at the bottom.
>
> **Narration describes intent. Git, the ledger and the gates describe reality.** When they
> disagree, that gap is the most valuable thing in this file — never smooth it over.

---

## 2026-08-14 · Session 1 · Stage 0 — the spine

**Done:**

- **Method study.** Read the `SpendWise` repository end to end as the reference implementation of
  this AI-SDLC method: all 24 `docs/` folders, `CLAUDE.md`, `CONSTITUTION.md`, `GOTCHAS.md`,
  `COORDINATION.md`, `PROGRESS.md`, all four handoffs, the `goals/` folder, the ledger and Bible
  column headers, and the 70-commit history. Then the `/ss` and `/tt` command definitions
  themselves.
- **Repo initialised** and pointed at `github.com/AniruddhaDynpro/FrontRow`. `.gitattributes` set to
  `* text=auto eol=lf` — the prior project learned that a CRLF working copy makes a line-by-line
  gate match nothing and print a clean result forever.
- **`/ss` and `/tt` installed** into `.claude/commands/`, tracked, so any clone gets them.
- **`docs/` built as the numbered delivery set** — `00 SourceOfTruth` through `40 AMS`, in
  dependency order, the same folder structure as SpendWise. Contents will differ; the structure
  does not.
- **`SRC-001` frozen** — the client's product requirements (`CLIENT_ASK.md`) verbatim,
  clause-numbered so everything downstream cites `§n`, SHA-256 recorded.
- **`SRC-002` frozen** — the client's build mandate (`CLAUDE_CODE_BRIEF.md`), same treatment.
  **This is a divergence from SpendWise**, which used `SRC-002` for client rulings. FrontRow has two
  written inputs rather than one, so rulings become `SRC-003`. Recorded as a `[JUDGMENT CALL]`
  rather than left as a silent convention break.
- **`CONSTITUTION.md` drafted** — 12 articles, each citing where its rule came from. Article IV is
  the one that differs most from the prior project: where SpendWise's central floor was per-user
  isolation, FrontRow's is *a seat is never sold twice*, enforced in two systems, with the database
  guard named as the one that may not be waived.
- **Root canon written:** `CLAUDE.md`, `GOTCHAS.md`, `COORDINATION.md`, `README.md`, `docs/README.md`.
- **`goals/` written** — `README.md`, `_TEMPLATE.txt`, and `GOAL_01`…`GOAL_14`. Each goal names the
  plugins it uses rather than leaving the choice to taste.

**Rulings and judgement calls** (worst first — the ones that weaken something come before the ones
that help):

- **`SRC-002` and `SRC-001` contradict each other in five places**, and per Art II.2 the build
  session may not pick a winner in any of them. Payment (required by one, absent from the other),
  the role count (five against one), cancellation, management reporting, and the queue technology
  (SQS against a Redis broker). **All five are blocking Article X rows.** This is the single largest
  finding of the session.
- **`OPEN-EMAIL-01` — a requirement that cannot currently be built.** `SRC-001 §5.3.4` and
  `SRC-002 §8.5.1` both require a confirmation email, and no approved service in `SRC-002 §4` can
  send mail, while `§4.12` forbids adding one unasked. Phase 5 is blocked until this is ruled.
- **`OPEN-HOLD-01` — an assumption that hardened into a specification.** `SRC-001 §10.9` asks "how
  long should seats be held? We assumed 7 minutes"; `SRC-002 §8.1.1` then states 7 minutes as a
  requirement. **The client's own open question was answered by the client's own next paragraph, and
  nobody ruled it.** It is filed in `GOTCHAS.md` as the one trap already confirmed present here.
- **`OPEN-PROC-01` — the memory budget does not obviously fit.** `SRC-002 §12` implies four
  long-running processes inside roughly 1 GB shared with an OS, a Docker daemon and an ECS agent.
  `§13.6` requires this be said rather than absorbed. Recommendation on the record: fold the
  scheduler into an EventBridge trigger against the admin sync endpoint `§10.6.1` already requires,
  and serve the frontend from a small static container. *(reasoned, not observed)*
- **Payment is simulated for v1** — a real interface with real state transitions, shaped so a
  provider drops in behind it. The client proposed exactly this in `SRC-001 §10.19` and confirmed it
  on 2026-08-14. Still needs an ADR before it counts as ruled.
- **Scope is the seven phases of `SRC-002 §12`, then extend.** Confirmed 2026-08-14. `OPEN-SCOPE-01`
  stays open until phases 8 and 9 are actually written down — an undocumented intention is not a
  plan.
- **The build session now holds read-only AWS credentials** so it can check what the client built
  against the specification. Art VIII.2: describe, list, get. **No create, no modify, no delete
  until the client says otherwise in writing.** This is a change from SpendWise, where the build
  session touched AWS not at all.

**In progress:** nothing half-finished. **No ADRs are filed, no derivation document exists, and no
application code exists — and none should yet.** The derivation chain reaches code at `06 DataModel`,
not before.

**Open / next:** `GOAL_01` — the client answers the 40 Article X rows and they are frozen as
`SRC-003`. Nothing downstream may be written until then, because 30 of those rows are the client's
own questions and Art VII.3 forbids guessing at one.

**Blockers:**

- **All 40 Article X rows are `OPEN`.** They gate `GOAL_02` onward entirely.
  *(Corrected the same session: this was written as 34 because the build-session-raised rows in X.1
  were not counted. The number is now derived from the file — `grep -oE 'OPEN-[A-Z]+-[0-9]+'`,
  sorted unique — not typed.)*
- **`OPEN-NAME-01`** — the client's exact full name for the ratification block, plus a backup
  decider (`NONE — accepted` is a valid written answer). Until it lands the Constitution is
  **UNADOPTED** and every ADR filed will carry a "recorded while ungoverned" caveat.
- **`OPEN-LOCALE-01`** — country, city and currency. This one blocks the *data model*, not just the
  interface, because a minor-unit ratio chosen now is effectively permanent once bookings exist.

- **Session closed 2026-08-14_0241 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-14_0241_ani87.md`

---

## 2026-08-14 · Session 2 · SRC-003, and the product changed

Same calendar day as Session 1; closed early because a usage limit was approaching, with two agents
stopped mid-flight.

**Done:**

- **All 40 Article X rows answered by the client and frozen as `SRC-003`** — 36 `RULED`, 3 `ASSUMED`
  ("you pick"), 1 `DEFERRED`. *(Written here as 34/5/1 at the time; the summary table in `SRC-003`
  was typed rather than counted and disagreed with its own per-row tags. Corrected 2026-08-14 in
  Session 4 — see that block.)* Every `Ruling` block is the client's own words; every `Filed as` block
  is the build session's reading and says so.
- **Sixteen errata filed** — ten against `SRC-001`, six against `SRC-002`. Both hashes moved and the
  invalidation is adjudicated in `fingerprints.json`: nothing derived from either source existed yet,
  so re-derivation is discharged by there being nothing to re-derive.
- **`CONSTITUTION.md` ADOPTED** — Aniruddha Jathar, no backup decider, 2026-08-14. No ADR carries the
  "recorded while ungoverned" caveat because none had been filed.
- **`tools/consistency_check.py`** — 8 rules, `--selftest` red-proofs **8/8** by planting a real
  violation of each and requiring the check to fire, measured by delta so it works on an
  already-red repo.
- `CLAUDE.md`, `docs/README.md` and `docs/30 Deployment/AWS_PREP_QUEUE.md` rewritten for the new
  product. `GOAL_03`, `GOAL_05` and `GOAL_06` updated with the ruled facts.

**Rulings** (worst first — the ones that remove something come before the ones that help):

- **TMDB removed in full.** `SRC-002 §10` withdrawn. The largest scope change of the project. Its
  second-order effect is bigger than the feature: **nothing in this system runs on a schedule any
  more**, so the scheduler process and the EventBridge prep-queue row are deleted rather than ticked
  off.
- **`OPEN-EMAILFAIL-01` — a new hole opened by the answers themselves.** The emailed receipt is now
  the customer's only proof of purchase and only way into the hall, and SES failing after capture
  leaves a paying customer locked out. Raised, not answered.
- **`OPEN-SHOWCANCEL-01`** — `OPEN-OPS-03` names *"cancel a show"* as an admin action while
  `OPEN-CANCEL-02` said to forget cinema-cancelled shows. Money question; raised, not answered.
- **`OPEN-ATTRIB-01`** — the TMDB API licence is gone, but the client supplies posters and titles
  themselves and the attribution obligation returns if that material is licensed.
- **Three readings marked `PROVISIONAL`**, each reconciling two of the client's own answers and
  each naming the reading it rejected: four roles rather than one (`C-1`), one cinema with six
  screens (`C-2`), and the sales cut-off falling after rather than before the advertised start.
- **`OPEN-HOLD-01` ruled 3 minutes, not 7** — the trap `GOTCHAS.md` logged on day one. The client's
  own assumption had hardened into a requirement in `SRC-002 §8.1.1`; asked properly, it came back
  different. This is the clearest evidence so far that the method earns its cost.

**Defects found in this session's own work:**

- The Article X count was written as **34**; it is **40**. Five files carried it. `docs/README.md`
  was already carrying a banner warning that a hand-typed index is how SpendWise's drifted in eight
  places, and it drifted here in one commit. The number is now derived, not typed.
- **A dangling ADR reference inside a frozen source** — `SRC-002` cites `FR-ADR-002`, which does not
  exist. Caught by `consistency_check.py` on its first real run against the repo, which is exactly
  the class it was built for. The gate is **red** on this and stays red until `GOAL_02` files it.
- **A personal email address heading into a PUBLIC repository.** Redacted from the answer sheet and
  `SRC-003`; `git log --all -S` confirms it never entered history.

**In progress:** `GOAL_02` was killed after completing its five-lens sweep (~290 raw decisions) and
before writing anything — **that work is lost and the goal restarts clean.** `GOAL_04` was killed
after writing `contrast.py` and before `tokens.css`, leaving the contrast engine orphaned with
nothing to measure. Three untracked paths are uncommitted; the handoff lists them.

**Open / next:** `GOAL_02` (reserving `FR-ADR-002` for the numbering divergence) and `GOAL_04` in
parallel — disjoint write-sets. Then `GOAL_03`, then `GOAL_05`.

**Blockers:** the repository is **public** and that should be a deliberate choice · SES needs
requesting now for its sandbox lead time · four reserved Article X rows and three `PROVISIONAL`
readings await the client.

- **Session closed 2026-08-14_0241 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-14_0241_ani87.md`

---

## 2026-08-14 · Session 3 · The ADR pack, and a fake green found by /ss

Third session of the same day. Closed on daily usage running out, with `GOAL_03` stopped one step
before it wrote anything.

**Done:**

- **`/ss` earned its keep on the first run.** It found that `contrast.py` reports **eleven PASS
  lines against zero data** — no tokens exist, no pairs were checked, and `CONTRAST`, `GREYSCALE`,
  `THEME-PARITY` and `TOKEN-COVERAGE` all say PASS anyway. Only `PARSE` fails, and it alone holds
  the overall result at FAIL. Verbatim the `GOTCHAS.md` trap: *a check that cannot fail looks
  exactly like a clean result.* Left unfixed on purpose — it is `GOAL_04`'s first task, and reaching
  into a later goal's write-set out of order is what the folder numbering exists to prevent.
- **`GOAL_02` complete.** `FR-ADR-001`…`070`, contiguous. 66 APPROVED (every one with an authority
  and a date), 4 NOT_DECIDED and all reserved. 30 client rulings, 33 judgment calls, 3
  stricter-adoptions.
- **`consistency_check.py` FAIL → PASS, 8/8.** 459 ADR references, 509 OPEN references, 1099 clause
  citations, all resolving. Rule 8 stopped skipping now that a ledger exists.
- Verified independently rather than on the agent's report: 70 files, 70 rows, ids contiguous, zero
  APPROVED rows missing authority or date, all 280 incorporation cells `NOT_INCLUDED`.

**Rulings** (worst first):

- **Nine cross-lens contradictions**, which is the whole reason the sweep runs five ways instead of
  once. `SRC-002 §7.9` — "fail loudly on dependency loss" — was read three different ways off a
  single sentence by three lenses. `FR-ADR-028` decomposes it: locks fail loudly, cache degrades to
  Postgres, the rate limiter fails closed.
- **One lens over-read `§8.1.4`** as ruling out a holds table and recorded it as settled fact. The
  same answer survives in `FR-ADR-025` but demoted to a judgment call, which is what it is.
- **Only one lens of five saw that rounding has a second dimension** — per-seat or per-total. Three
  missed it entirely, and it is a real one-paisa difference on a three-seat booking.
- **`FR-ADR-038` — pricing rounding.** Integer half-up, per seat, never on the total, uplift in
  basis points. Base 25000 paise at 3333 bp is exactly 33332.5, a true tie, rounding to 33333.
  Batched for client reversal as money-adjacent.
- **Three `CONSTITUTION.md` clauses now contradict `SRC-003` and were NOT edited** — Art XII.1
  reserves amendment to the client. Art I.6 still defines victory as a scannable ticket plus TMDB on
  a schedule, both withdrawn; Art V.8 calls the cancellation rows open; Art VIII.13 names TMDB as an
  outbound path, which would mean a security-group rule for a connection that never happens and none
  for SES.

**In progress:** `GOAL_03` was stopped on the sentence *"I have the full picture. Now writing the
BRD."* — it had read everything and written nothing. `docs/02 BRD/` is empty and all 70
`included_in_brd` cells still read `NOT_INCLUDED`. Re-run from the top; only re-reading is lost,
unlike Session 2's destroyed sweep.

**Open / next:** `GOAL_03` (BRD) → `GOAL_04` (design system, repairing `contrast.py` first) →
`GOAL_05` (PRD). **Strictly in order** — parallelism belongs inside a goal, never across the chain.

**Blockers:** the repository is still **public** · the three stale Constitution clauses await one
word · SES production access has a review lead time · three `PROVISIONAL` readings the PRD will be
built directly on top of · four reserved Article X rows · six AWS prep-queue rows owed as advance
notice under Art VIII.4.

- **Session closed 2026-08-14_1638 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-14_1638_ani87.md`

---

## 2026-08-15 · Session 4 · The BRD, the design system, and the PRD

Closed at 04:25 with `GOAL_05` **one step from done** — everything built, assembled, regenerated and
green; only the final count and `S8` bookkeeping outstanding.

**Done:**

- **`GOAL_03` — the BRD.** 93 rows, business language, zero technology names in prose. Two-way
  coverage machine-derived: 51 live clauses, 51 covered, **no-gap 0, no-creep 0**, with the 12
  erratum-withdrawn clauses listed explicitly rather than silently absent.
- **`GOAL_04` — the design system.** Repaired `contrast.py` **before** writing a token: eleven of
  its twelve checks had been reporting PASS against zero data. Now `SKIP` on an empty subject set
  and `--selftest` red-proofs 13/13. Then 70 contrast pairs across both themes and a greyscale
  separation of 14.1 L* against a floor of 12.
- **`GOAL_05` — the PRD.** 25,026 lines, 12 sections, a 3,819-line generated contract. Eight
  parallel epic lanes, seven fix waves, **twelve iterations of fresh zero-context readers**.
- **Repo moved** to `github.com/AniruddhasGit/FrontRow`, private. Old remote kept as `dynpro`.
- **Article X: 4 open rows → 18.** **`GOTCHAS.md`: 8 sections → 18.**

**Rulings** (worst first):

- **Reader B's structural finding, which outranks the count: four of its ten remaining guesses are
  in `scripts/seed.py`.** The seed is the only Zone A artefact that writes to every table **without
  going through an endpoint**, so every rule about audit rows, naming and privileged writes — all
  written for a request handler with an authenticated actor — does not reach it. A structural gap,
  not four oversights. The seed needs an owning P-row before Phase 2.
- **`OPEN-SEATLABEL-01` has a deadline.** `row_label` is unique and unnormalised, so `C12` and `c12`
  are two seats a person reads as one — on a label printed on the receipt and read at the door.
  `P-ADM-14` freezes it once a showtime exists, so the fix is cheap now and **impossible in
  Phase 2**. Found by a lane that refused to fix it, because the safe normalisation for a category
  name changes what is *stored* for a seat label.
- **Nine of ten remaining guesses are silences, not contradictions**, and `S1.2`'s ranking cannot
  reach a silence — there is nothing to arbitrate when there is one passage and it is quiet.
- **A worked example demonstrated nothing.** The price-rounding example used inputs where the
  rounding term was a no-op: `25000 × 11200` divides exactly. It would have passed any check anyone
  would run, because its arithmetic was correct — only its purpose was unmet.
- **Invented evidence in a security rationale**, caught and withdrawn: a token described as
  "brute-forceable at line rate" is 32 bytes from a CSPRNG. One lane refused to write it; another
  published it and withdrew it after checking. *"The wording came from the brief but I published it,
  and Art VII.1 binds the writer."*

**Defects found in this session's own work:**

- **A partial fix that contradicted itself.** The main session edited a lane's file directly to
  remove the false security claim, missed a sentence one paragraph below still carrying the
  withdrawn framing, and was caught by the lane mid-edit. Write-set discipline exists for exactly
  that, and breaking it produced exactly that.
- **"Document it and close" does not discharge a deferral.** The status law has four states and
  "written in the merge report" is not one of them, so readers correctly counted deferred items as
  guesses. A fact recorded somewhere other than where it is needed is not recorded.
- **Recovering what a dead agent announced is not recovering what it was assigned.** Three lanes
  died; every file was intact; two lanes' announced items were recovered and a third re-derived
  from its brief to find **four** unwritten items.

**In progress:** `GOAL_05`'s final count and `S8` bookkeeping. Nothing else.

**Open / next:** close `GOAL_05` → `GOAL_06` journeys → `GOAL_07` Bible → `GOAL_08` data model, whose
contract already carries the three-column reset-token constraint and the `row_label` one-way door.

**Blockers:** 18 open Article X rows, 7 reserved · three `PROVISIONAL` readings the PRD now rests on
· SES production access needs requesting · 18 AWS prep-queue rows, all `REQUESTED`.

- **Session closed 2026-08-15_0425 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-15_0425_ani87.md`

---

## 2026-08-15 · Session 5 · `GOAL_05` does not close, and two checkers start measuring more

Closed at 21:18 on a **reserved decision**, as Art III.8 requires: no timeout defaults past a
reserved matter, so the work stopped rather than defaulting.

**The headline, and it corrects the previous block:**

- **`GOAL_05` is `BLOCKED`, not `Done`.** Its Definition of Done requires a fresh zero-context
  reader's guess count **under 5**. Derived from the series rather than read off it: **lowest single
  reading 7, last reading taken 10, no round ever below 5.** The previous session closed it on a
  **convergence** argument — real, evidenced, and **not the criterion the goal was given**.
  Substituting it is **waiving a quality check**, reserved to the client (Art III.8, Art IX.8).
  Art IX.2 calls a unit marked `Done` against a non-green gate a **fake green** and a stop-the-line
  finding. Filed as **`OPEN-PRDCLOSE-01`** (Art X.0d), with **neither option recommended** — the
  reserved matter is not which is wiser, it is who signs.
- **Every other DoD line on `GOAL_05` was verified, not assumed** — no-gap 0 / no-creep 0 over 93 BRD
  rows and 163 P-rows, `sm-total` 0 of 145, contract byte-identical, endpoint parity 0/0 both ways,
  73/73 `included_in_prd`. **One line, and only that line, is unmet.**
- **Iteration 12's reader A count does not exist and was not invented.** Recorded as a dash in
  `S8.6.17` — not carried over from 11-A, not inferred from its partner, not omitted so the row would
  read as a pair. Taking it needs a fresh zero-context session.

**Done:**

- **`S8.6.17`** written, plus a notice at the **top** of `S8.6` — because that section's own finding
  is that a fact recorded somewhere other than where it is needed is not recorded, and the place an
  engineer decides whether to trust the PRD is the top of the audit, not the end of it.
- **Rule 2's id pattern widened.** `OPEN-[A-Z]+-\d+` matched neither a second hyphen nor a digit, and
  the **same pattern** harvests known rows *and* finds references — so an unmatchable id was missing
  from both sets and **the two blindnesses cancelled into a green line.** By the time it was fixed
  it had a live consequence: `OPEN-CACHE503-01` had been filed as a genuine Art X.0b row, so **every
  reference to a real filed row was going unchecked.** 57 rows / 826 refs → **58 / 829**.
- **New `rule 9 readme-state`.** Rule 6 defers path checks on rows marked not-yet-written, so a stale
  `empty` cell **switches the check off** — five written folders sat marked `empty`, one of them a
  25,000-line document, and rule 6 went green while deferring six claims it should have gated. The
  exemption is kept and the cell it keys on is now guarded. Correcting the cells moved rule 6 from
  `23 of 23 · 6 deferred` to `24 of 24 · 5 deferred`. **Checker is now 9 rules / 11 plants, all
  red-proofed.**
- **Drift corrected, every count derived**: `docs/README.md` states from the tree, `CLAUDE.md`'s
  Status block, folder table and open-row counts.

**Rulings** (worst first):

- **A sentence in `S8.8` falsified itself by existing.** It claimed `FR-ADR-002` and `FR-ADR-073`
  were *"cited nowhere in this document"* and that **71 of 73** records were cited; the ledger holds
  **73 INCLUDED**, and `FR-ADR-002` appears in the PRD **only inside the clause asserting it appears
  nowhere.** Publishing the claim created the citation that refutes it. **A statement about a
  document's contents is part of that document's contents.** Every check passed throughout — none of
  them compares a count in prose to the column it is a count of.
- **A check whose exemption is data-driven is only as honest as the data driving it**, and that data
  is usually the exact thing the check was bought to police. Worse than measuring the wrong thing:
  **the thing being measured decided how much would be measured, and decided downward.** The fix is a
  second check on the exemption's input, not the removal of the exemption.
- **A pattern that cannot match an id fails silently.** It reports nothing rather than reporting a
  miss, so only a plant of that exact shape distinguishes a widened rule from a narrow one. Both new
  plants were **verified to discriminate** (`old=False new=True`), not merely to fire.
- **The reserved-row count was wrong in every record before now.** The last handoff and this file
  both said *"18 open rows, 7 reserved."* **Seven is the count of the rows that are NOT reserved** —
  the derived figures were 11 reserved / 7 not, and are now **19 rows · 12 reserved · 7 not** with
  `OPEN-PRDCLOSE-01` filed. It propagated into `/ss`'s orientation brief this morning before being
  caught.
- **Describing a defect must not commit the defect.** `S8.7` spelled the two invisible ids in their
  `OPEN-` form; under the widened pattern that spelling is a claim the row exists, and one of them
  does not. Rewritten to `PROPOSED-`.

**Defects found in this session's own work:**

- **A count typed while correcting typed counts.** `OPEN-PRDCLOSE-01`'s filing note was written to
  fix a wrong aggregate and was itself filed reading *"eleven reserved and eight are not"* against a
  nineteen-row table whose derived figures are twelve and seven — copied forward across the change
  that invalidated it. **A correction is not exempt from the rule it is enforcing.**
- **A `GOTCHAS.md` claim that was false the moment it was true.** *"This trap is dormant rather than
  closed"* was written before rule 9 existed and left standing after it did.
- **A line count that decayed twice inside one session** — 25,176 → 25,180 → 25,213. The exact figure
  was **removed** from `CLAUDE.md` rather than maintained, and replaced with the command that prints
  it. Nothing checked it, and nothing ever would have.
- **A verbatim quotation silently re-typeset.** The DoD line was quoted with its ASCII hyphen turned
  into an em-dash and emphasis added. Restored: **bolding inside a quotation is the quoter choosing
  which part of someone else's sentence matters.**

**In progress:** nothing half-written, no red gate. `GOAL_05` is **stopped, deliberately**, awaiting
a signature — not unfinished.

**Open / next:** the client rules on `OPEN-PRDCLOSE-01` *(optionally after dispatching reader 12-A so
the ruling is made on a real pair)* → `GOAL_06` journeys → `GOAL_07` Bible → `GOAL_08` data model →
`GOAL_12` ledger, which is what `/ss` still cannot read a frontier from.

**Blockers:** `OPEN-PRDCLOSE-01` gates the whole chain · 19 open Article X rows, 12 reserved ·
`OPEN-SEATLABEL-01` expires in **Phase 2**, not Phase 6 · three `PROVISIONAL` readings the PRD rests
on · no seeded account can sign in, which stops Phase 2 **and** Phase 4 · SES production access needs
requesting · 18 AWS prep-queue rows, all `REQUESTED`.

- **Session closed 2026-08-15_2118 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-15_2118_ani87.md`

## 2026-08-23 — `GOAL_06` closed, the PRD repaired, `GOAL_07` written and blocked (Aniruddha Jathar)

**Done:**

- **`GOAL_06` complete.** Six lanes, 313 steps, 150 of 163 P-rows, **81 defects filed**. The five
  persona lanes could not see each other's work (Art VII.7), and it paid on the first merge: **three
  converged independently on one hole — the booking path never checks whether a film is still inside
  its display window**, and no admin action can stop a showtime selling.
- **The nine walkable P-rows the persona lanes missed were published as a gap, then closed** by a
  sixth lane — which found **`J-XCT-01`: the never-waivable concurrency drill fires at the wrong
  endpoint**, so dropping the constraint changes nothing and the drill **reports failure against a
  correct implementation**. Repaired by ADDING a Stage B, not by weakening anything.
- **PRD fix wave — 65 defects repaired** by nine agents with exclusive file ownership. Cross-file
  contradictions were fixed by one owner each, emitting a patch record for the other side, because
  two agents fixing opposite halves swap the error. **One patch was refused on application** — E2 had
  rewritten the passage while E3 read it and kept the exact sentence the patch existed to change.
- **`GOAL_07` written**: 210 rows, 200 stories, **163/163 coverage, no-gap 0, no-creep 0**.
- **`GOAL_09` and `GOAL_11` corrected** for `SRC-003` rot. `GOAL_11`'s *"manager reaching another
  cinema"* would have **passed vacuously** — with one cinema, cinema-level scoping scopes nothing.
- **`tools/verify_goal06.py`** added; re-derives every journeys figure from the committed documents.
- **Nine Article X rows filed** (`X.0e`, `X.0f`, `X.0g`). **19 → 28 open, 21 reserved.**

**Rulings** (worst first):

- **Adversarial reading does not converge for this document.** Five panels — three samples, a full
  200-cell census, and a re-census control — each found true defects the previous missed, and **none
  was a repeat**. The control says **27% of the cells the census called `OK` are wrong**. What would
  settle a criterion is *running* it, and no application code exists. `GOAL_07`'s DoD assumes reading
  can certify these cells; the evidence is that it cannot. Full record: `docs/05 Bible/CENSUS_2026-08-22.md`.
- **`OPEN-RESETTOKEN-01` blocks a feature, not a document.** The token is never stored, never travels
  the queue, and yet an email must render a link containing it. **Nothing downstream holds the 43
  characters.** Phase 2 reaches it.
- **The 91 wrong cells were eight mistakes, repeated** — a grep matching its own test, a per-request
  id asserted as a literal, a bound absence satisfies, a view that cannot answer the question, a
  catalog query with no schema filter, equality over a countdown, a framework misunderstanding, and
  arithmetic. Fixing them **by class** is what finally stopped adding new defects; three rounds of
  cell-by-cell repair had been introducing them at roughly the rate they removed them.

**Defects in this session's own work:**

- **I contaminated the re-census** by editing files while the graders read them. Group A is not a
  valid measurement; the control group is. Recorded rather than dropped.
- **My scope rule had three successive coverage gaps** — the prose form, the `rather than -1`
  variant, and paths with no trailing slash. Each was caught by a grader, not by me.
- **Two Bible criteria were invalidated by my own PRD fixes**, and **my PRD fix made a customer-facing
  message worse** — the outage sentence now promises a seat map that returns 503 in that outage.
- **I amplified two defective repairs** in my own reporting, and **should have questioned the
  sampling method after round 2**, not round 3.

**In progress:** nothing half-written, no red gate. `GOAL_05` and `GOAL_07` are both stopped
deliberately, awaiting signatures.

**Open / next:** rule on `OPEN-RESETTOKEN-01` → decide what `GOAL_07`'s gate should be → `GOAL_08`
data model (**which inherits the Bible's table names as a hard constraint**) → `GOAL_12` ledger →
the PRD defects the Bible inherited.

**Blockers:** `OPEN-RESETTOKEN-01` blocks a feature and Phase 2 reaches it · `GOAL_07`'s gate ·
`OPEN-PRDCLOSE-01` · 28 open Article X rows, 21 reserved · **three rows now carry deadlines** —
`OPEN-SEATLABEL-01` and `OPEN-SEATALPHA-01` at Phase 2, `OPEN-REFCHAR-01` at Phase 4 · no seeded
account can sign in · SES production access · 19 AWS prep-queue rows.

- **Session closed 2026-08-23_0241 by Aniruddha Jathar** → handoff:
  `handoffs/HANDOFF_2026-08-23_0241_ani87.md`

## 2026-08-23 — `GOAL_08` part done: the data model applies, and the guard was watched failing

- **Three inherited PRD defects repaired** (`36cef2d`) — the `Retry-After` maximum stated as the
  value, the twelve/thirteen cross-field count, and a customer-facing outage message the product
  falsified in thirteen places. Three Bible cells quoted the message byte-exact and moved in the
  **same commit**, which is the failure mode the previous session caused by fixing only one half.
- **Eight acceptance criteria that cannot run repaired** (`aa18326`). Every one verified against a
  source before being touched; **two verified empirically against a live PostgreSQL 16**.
  `S-ADM-18` carried two defects at once: `information_schema.check_constraints` has no
  `table_name` column, and PostgreSQL reports every `NOT NULL` as a `check_constraints` row, so
  "returns 0" was unsatisfiable against any correct table.
- **`docs/06 DataModel/` written** (`59cb4d6`) — 22 tables, 152 columns, every one cited,
  assembled from six independent cluster reads preserved verbatim under `derivation/`.
  `schema.sql` **applies to an empty PostgreSQL 16.14 database: exit 0, 75 objects, zero errors.**
  `consistency_check.py` 13/13, and **14 of 14 rules watched going red** under `--selftest`.
- **The seat guarantee was red-proofed at the database layer** — guard in place gives one winner;
  dropped on purpose gives **two, watched**; restored; refused again; definition confirmed
  `UNIQUE (showtime_id, seat_id)` with **no `WHERE`**. This is the database half only — the Redis
  lock and the 50-request stress script are Phase 4 and do not exist.
- **Three of my own rules would have failed a correct schema** and were rewritten before shipping:
  the guard rule (two relations legitimately carry the column pair), the clock rule
  (`created_at` *must* default to `now()`), and the Bible-reference rule (most dotted tokens are
  audit actions, and one is a filename). Same defect class the Bible census catalogued.
- **Two database roles, forced by an observed fact**: a table's owner sees seven privilege rows on
  PostgreSQL 16.14, so `S-XCT-07`'s "exactly two" cannot be met by a single role. Filed as
  `AWS_PREP_QUEUE` row 20, needed by **Phase 1**.
- **`GOAL_08` is `part done`, not `Done`.** `verify_invariants.sql`, the seed expectations,
  `fingerprints.json` and the ADR ledger's `included_in_datamodel` column are **not** written, and
  the schema has only ever been applied as a superuser.
- **Session closed 2026-08-23_0336 by ani87** → handoff: `handoffs/HANDOFF_2026-08-23_0336_ani87.md`

## 2026-10-18 — `GOAL_14` Phase 1 skeleton: built, and every runtime DoD proof run against docker compose

- **Phase 1 only** (`SRC-002 §12.2`). `backend/` (FastAPI): config validation, `/health/live`,
  `/health/ready`, JSON logs with an 8-hex request id, one error envelope, a SIGTERM drain with the
  shutdown-hook list Phase 4 hangs lock release on. `frontend/` (Vite + React + TS) is one static
  page served by nginx. `docker-compose.yml` is **local only**. No data model, no auth, no movie.
- **Test-first.** RED: 4 collection errors with an empty `app` package. GREEN: **49 passed** in the
  Python 3.12 Linux test image (`docker build --target test backend`). Two defects found by the gate
  were each pinned by a failing test first: a 405 on a health path went unlogged, and uvicorn's
  ANSI `color_message` leaked into the JSON.
- **Proved by stopping containers, not by asserting code paths:** ready 200 with both up · 503
  `redis: unreachable` with Redis stopped · 503 `postgres: unreachable` with Postgres stopped · live
  200 with both stopped · missing `DATABASE_URL` → exit 78, one JSON line naming it · 26/26 log lines
  valid JSON with a request id, 0 on stderr · SIGTERM 1 s into a 5 s request: the request completed
  200 and the process exited 0 after 3742 ms · read-only root FS, `docker diff` = 0 paths.
- **Image budget, worst number first:** the api image was **276 MB** by `docker images` on bookworm,
  **over the 250 MB budget**. Dropping pip from the venv brought it to 258 MB, and moving to
  `python:3.12.15-slim-trixie` brought it to **239 MB** (56.5 MB compressed). **Margin: 11 MB.**
  Phase 2's SQLAlchemy + Alembic and Phase 5's boto3 will not fit under that reading. Filed as an
  open question on which size the budget means.
- **Memory measured (idle, local Docker Desktop, NOT a t3.micro):** api ~50 MiB, frontend ~3 MiB.
  Under load: unmeasured until Phase 7.
- **Zone C:** ten specifications in `docs/30 Deployment/` (`ZONE_C_PHASE1_INDEX.md` plus nine `P1_*.md`).
  Prep-queue rows 1–4, 6, 7, 12, 13, 15 and 18 now link them. **Rows 5 (RDS) and 8 (ElastiCache) are
  needed by Phase 1 for a healthy api target**, because readiness checks both. The client chooses
  between building them now and deploying to watch the 503. No Zone C artefact was written. Nothing
  was created in AWS.
- **Not done here:** the engineering-ledger Status flip (another lane owns that file) · the
  reviewer's confirmation of the Zone B comments (the author may not confirm them) · `/tt` (this lane
  may not commit).
