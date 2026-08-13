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
