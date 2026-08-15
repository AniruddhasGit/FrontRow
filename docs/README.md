# docs/ — the FrontRow delivery document set

<!-- HAND-MAINTAINED, and that is a known weakness. On SpendWise this index drifted in eight
     places while being the first thing a session read, and was replaced by a generator
     (tools/generate_docs_readme.py). The same generator is owed here once docs/10 exists —
     the State column and every count must be computed from the repo tree and the ledger,
     not typed. Until then, treat the State column as a claim, not a fact. -->

Numbered in **dependency order**. Each folder is derived from the ones above it and **cites them**.
Nothing appears out of thin air: a statement without a source carries an `ASSUMED` flag and can never
become a `MUST`.

```
00 SourceOfTruth ──► 02 BRD ──► 03 PRD ──► 05 Bible ──► 06 DataModel ──► code
       │                                                      ▲
       └──► 01 ADR ────────────────────────────────────────────┘
            every ruling, and proof it landed in each document above
```

**Dependency order is not generation order.** Two folders are written out of numeric sequence on
purpose: `05 B DesignSystem` before `03 PRD`, because the PRD's screens bind to its tokens by name;
and `11 Journeys` before `05 Bible`, because journeys find the seams a per-screen specification
misses. `goals/README.md` carries the real execution order.

| # | Folder | What it is | State |
|---|---|---|---|
| 00 | **SourceOfTruth** | Three frozen, hashed sources. `SRC-001` the product requirements (**10 errata**), `SRC-002` the build mandate (**6 errata**), `SRC-003` the client's rulings on all 40 Article X rows. Never edited; errata are appended, never struck. | **written** |
| 01 | **ADR** | Decision records + `ADR_DECISION_RELEASE_LEDGER.tsv`. Fail-closed. `FR-ADR-nnn`. | **written** |
| 02 | **BRD** | Business requirements — what and why. No technology. | **written** |
| 03 | **PRD** | Every screen, rule, error and permission, plus the API contract. **The code is written from this.** | **written** |
| 05 | **Bible** | Epics, stories, and binary acceptance criteria. The scope arbiter. | empty |
| 05 B | **DesignSystem** | Tokens and real CSS. Every contrast figure computed, not claimed. Where the seat map is designed. | **written** |
| 06 | **DataModel** | A **package, not a document**: `datamodel.json` is the spec of record; `schema.sql` and `TRACEABILITY.tsv` are generated from it. Holds the unique constraint the whole product rests on. | empty |
| 07 | **Architecture** | `for_llm/` to orient a cold session · `for_humans/` to decide from, including the accepted weaknesses. | empty |
| 08 | **SIT** | Positive cases — exactly one per acceptance criterion, each citing the story it proves. | empty |
| 09 | **NegativeTesting** | The cases that try to break it. Weighted hard at one thing: **two customers and one seat.** | empty |
| 10 | **EngineeringLedger** | Derived from the Bible — one row per unit of work, with `Milestone` and `Status`. **`/ss` reads this to report the frontier.** | empty |
| 11 | **Journeys** | Persona journeys, each walk naming the seam it crosses. | empty |
| 12 | **DesignReview** | The pre-code audit: fresh agents attack every document above before a line is written. | empty |
| 13 | **Fixes for Design Review** | What the audit found, and its repair. | empty |
| 14 | **Project_Plan** | Milestones and the cutover plan. | empty |
| 30 | **Deployment** | The client's AWS prep queue, and one specification per Zone C item. | **written** |
| 15 **ChangeRequest** · 20 **UAT** · 35 **Hypercare** · 40 **AMS** | Lifecycle. | empty |

**The folder set is fixed. Its contents are not.** A folder may hold more or fewer documents than
SpendWise's equivalent did — the project is different — but no folder is added, removed or
renumbered (`CONSTITUTION.md` Art XI.3).

## The four rules that make this work

**1. Provenance on every line.** Every requirement downstream cites `SRC-001 §n`, `SRC-002 §n`, a
client ruling, or an `APPROVED` ADR. You can trace any sentence back to something the client
actually said.

**2. Status law.** `RULED` (decided, cited) · `PROVISIONAL` (written, ruling outstanding) ·
`OPEN` (**escalate, never invent**) · `ASSUMED` (inference, never a constraint). An agent that hits
`OPEN` and fills in something plausible has committed the cardinal sin.

**3. Fail-closed decisions.** Every ADR starts `NOT_DECIDED` + `HOLD_PENDING_DECISION` +
`NOT_RELEASED`. **Silence never means approval.** Accepted decisions are immutable — a reversal is a
new superseding record, never an edit. A supersession is itself a claim, and it gets checked.

**4. Incorporation is tracked, not assumed.** The ledger's `included_in_brd` / `_prd` / `_bible` /
`_datamodel` columns prove a decision actually *landed* in each document rather than being decided
and forgotten. They are **derived from the citations present in each target**, never asserted.

## Fingerprints

`00 SourceOfTruth/fingerprints.json` holds a SHA-256 per frozen source, and
`fingerprints.sha256` lets you check them with `sha256sum -c`.
**If a hash changes, every artifact derived from it is invalid and must be re-derived** — never
silently reused.

A hash comparison is the *weaker* guarantee: it proves a file was not edited, but it cannot see
content a specification never contained. Where a document is marked `GENERATED`, the stronger check
regenerates it and compares content.

## Where the open questions live

`CONSTITUTION.md` **Article X**, and since 2026-08-14 the answers live in `SRC-003`.

**All 40 original rows were ruled on 2026-08-14** — 36 `RULED`, 3 `ASSUMED` (the client said "you
pick" on hall sizes, peak concurrency and seat category names), 1 `DEFERRED`. **Four rows are open now**, all reserved: `OPEN-TLS-01` carried forward, plus
`OPEN-ATTRIB-01`, `OPEN-SHOWCANCEL-01` and `OPEN-EMAILFAIL-01`, which the rulings themselves raised.

**Three rulings are `PROVISIONAL`** because two of the client's own answers had to be reconciled —
the role set, one cinema versus several, and whether the sales cut-off is before or after the
advertised start. Each records the reading it rejected. One message reverses any of them.

Count them from the file, not from this sentence — this index claimed 34 for one commit because the
number was typed rather than counted, which is the exact drift the banner at the top warns about.

Five of them are **source conflicts** — places where `SRC-001` and `SRC-002` contradict each other.
Per Art II.2 the build session may not pick a winner in any of them.

Until a named human signs the ratification block (`OPEN-NAME-01`), the Constitution is **UNADOPTED**
and every ADR filed carries a "recorded while ungoverned" caveat.

## Reading rules

- For **decision status**, trust the ledger. For **document versions**, trust the files on disk.
  For **paths**, trust the repo tree — never a path quoted in prose.
- Authority on conflict: raw `SRC-001` → raw `SRC-002` → a client ruling → an `APPROVED` ADR → PRD →
  BRD → Bible → everything else. **Stricter always wins.** Where `SRC-001` and `SRC-002` disagree,
  neither wins — that is an Article X row.
- **This index included.** It is hand-maintained today, which is exactly how the prior project's
  index drifted in eight places. Generate it as soon as there is something to generate it from.
