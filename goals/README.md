# goals/ — the unit of work

One goal file = one thing you want built. You write the goal; the session builds it; you stop
whenever you like and `/tt` records exactly where it stopped.

## The loop, every session

```
/ss                    orient — reads the newest handoff, PROGRESS, CLAUDE.md, GOTCHAS,
                       reconciles them against git, and recommends ONE restart point
      ↓
write a goal           copy _TEMPLATE.txt → goals/GOAL_<thing>.txt, or just say it in chat
      ↓
build                  the session works the goal until its Definition of Done is met
      ↓                (stop whenever you want — mid-story is fine, that is what handoffs are for)
/tt                    writes handoffs/HANDOFF_<stamp>_<you>.md, appends PROGRESS.md,
                       commits and pushes to GitHub
```

Next session — **any machine, any Claude account** — starts with `/ss` and is fully oriented from
the repo alone. Nothing lives in a chat history.

## The execution order — run these one at a time

Thirteen goals take FrontRow from a frozen requirements document to a ledger the build loop runs
off. **Each one depends on the ones above it**, so they are executed in this order and the full
document is read before the next begins.

| # | Goal file | Produces | Why it sits here |
|---|---|---|---|
| 1 | `GOAL_01_source-of-truth.txt` | `00 SourceOfTruth/SRC-003` | The client has answered none of their own 30 questions, and 4 more were raised while drafting the Constitution. **34 `OPEN` rows block everything.** Nothing downstream may guess at one. |
| 2 | `GOAL_02_adr-completion.txt` | `01 ADR/` | Find every decision the BRD and PRD will need. Rule what is rulable; raise the rest. The ledger starts empty. |
| 3 | `GOAL_03_brd.txt` | `02 BRD/` | What and why, in business language. No technology. |
| 4 | `GOAL_04_design-system.txt` | `05 B DesignSystem/` | Before the PRD, because the PRD's UX section binds to it. **The seat map is a design problem before it is a code problem.** |
| 5 | `GOAL_05_prd.txt` | `03 PRD/` | **The document the code is written from.** The largest artifact here. |
| 6 | `GOAL_06_journeys.txt` | `11 Journeys/` | Finds what a per-screen spec misses: the seams between screens. On this product the seams are where the money is — hold expiring during checkout, a seat taken while you were choosing. |
| 7 | `GOAL_07_bible.txt` | `05 Bible/` | The scope arbiter. After this, no scope exists beyond an `AcceptanceCriteria` cell. |
| 8 | `GOAL_08_datamodel.txt` | `06 DataModel/` | A package, not a document. Real SQL, including the unique constraint the whole product rests on. The last artifact before code. |
| 9 | `GOAL_09_architecture.txt` | `07 Architecture/` | Two audiences: `for_llm/` to orient a session, `for_humans/` to decide from. |
| 10 | `GOAL_10_sit.txt` | `08 SIT/` | Positive cases, written before the code exists. |
| 11 | `GOAL_11_negative-testing.txt` | `09 NegativeTesting/` | The cases that try to break it. Weighted hard at one thing: **two customers and one seat.** |
| 12 | `GOAL_12_engineering-ledger.txt` | `10 EngineeringLedger/` | What `/ss` reads to report the frontier. Makes cold resumption real. |
| 13 | `GOAL_13_consolidated-exit-gate.txt` | `12 DesignReview/` | **The gate before code.** Do the eight documents agree with each other, and can a stranger build from them? |

Then `GOAL_14` onward is code, one per phase of `SRC-002 §12`, sequenced by the ledger.

Every goal is set to **Opus 5 · xhigh effort · ultracode · maximum parallelism**, and every one
carries a Definition of Done whose lines are binary and name the command that proves them.

Several close on a **fresh zero-context session** grading the output — a session that never saw the
work being made. That is deliberate: the writer never verifies its own work, and where no second
human exists, a session with no inherited context is the substitute.

Two goals are designed to be **failed on the first attempt**: `GOAL_05` (the PRD) does not close
until a fresh session reports fewer than 5 places it would have to guess, and `GOAL_06` (journeys)
treats "found zero defects" as a suspicious result requiring explanation rather than a good one.

## Plugins — named per goal, not left to taste

Each goal file carries a `PLUGINS & SKILLS` block. Two apply everywhere:

- **`superpowers:verification-before-completion`** — run before any Definition-of-Done line is
  ticked. This is the mechanical form of "never fake a green".
- **`superpowers:dispatching-parallel-agents`** — whenever the work fans out across epics, lanes or
  documents.

The ones that matter most on specific goals:

| Goal | Plugin | Why |
|---|---|---|
| `GOAL_04`, and every frontend build goal | **`frontend-design`** | This is a consumer product a stranger will judge in four seconds. The seat map, the showtime picker and the checkout flow carry the whole impression. |
| `GOAL_05`, `GOAL_09` | `superpowers:writing-plans` | Large structured artifacts with a reviewer prompt attached. |
| `GOAL_11`, `GOAL_13` | `superpowers:dispatching-parallel-agents`, `superpowers:requesting-code-review` | Adversarial work is worth more from several independent attackers than one thorough one. |
| every code goal | `superpowers:test-driven-development` | The Definition of Done starts with a failing test written from the acceptance criterion. This is that rule, mechanised. |
| every code goal | `superpowers:systematic-debugging` | Root cause before fix. A patched symptom on the seat-locking path is how a double-booking ships. |
| code goals with disjoint write-sets | `superpowers:using-git-worktrees` | Parallel lanes that never touch the same file. |
| before any merge | `/code-review`, `/security-review` | The built-in review gates. |

A skill listed in a goal and then not used is a deviation, and it belongs in the handoff.

## The two layers of checking

**Every goal runs the consistency check** as a Definition-of-Done line — the cheap, mechanical layer.
It answers one question: *does every cross-reference actually resolve?* Dangling ADR ids, dangling
`OPEN-` ids, an erratum claimed but never filed, a prep-queue row claimed but never added. That last
class is the **"I reported an action I did not perform"** breach, and on the prior project a 40-line
script caught four of them that an expensive adversarial agent had spent real effort finding.

It ships `--selftest`, which **plants a real violation of each rule and requires the check to fire** —
by delta, so it still red-proofs on a repo that is already red. A check nobody has watched fail is
decoration.

**`GOAL_13` is the expensive layer**, and it exists because the cheap one is blind to the thing that
actually bites: contradictions *between* documents that each resolve perfectly well on their own.
Plus the uncoached vertical slice — a fresh agent handed the frozen documents and nothing else, whose
every question is a defect in the documents rather than a failing of the agent.

## Writing a good goal

The template asks for six things. Two of them are what make it work:

**The write-set.** The exact files this goal may touch. Two goals whose write-sets overlap must never
run at the same time — that is how parallel work stays safe, and grouping "by topic" is not good
enough. If the work needs a file outside the list, the session stops and asks rather than widening
quietly.

**A binary Definition of Done.** Every line either passes or fails, and names the command that proves
it. "The seat map works" is not a DoD. "`py scripts/stress_seats.py --seat A-12 --n 50` returns
exactly one 200 and 49 409s, three runs in a row" is.

## The shortcut

If you don't want to write the goal yourself, paste this and let the session write it for you:

> Build me a goal file for: `<the task>`. Use the template in `goals/_TEMPLATE.txt`, read
> `CLAUDE.md` and `CONSTITUTION.md` first, and make every Definition-of-Done line binary.

Then read it, correct it, and run it. Reading a goal takes a minute; a wrong goal costs an evening.

## Naming

`GOAL_<nn>_<short-slug>.txt`. Keep finished ones. They are the record of what was actually asked
for, which is not always what the backlog said.
