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

- **All 40 Article X rows answered by the client and frozen as `SRC-003`** — 34 `RULED`, 5 `ASSUMED`
  ("you pick"), 1 `DEFERRED`. Every `Ruling` block is the client's own words; every `Filed as` block
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
