# `01 ADR/` — decision records and the fail-closed ledger

This folder is the **decision authority of record** for FrontRow (`CONSTITUTION.md` Art III.1).
Nothing downstream — the BRD, the PRD, the Bible, the data model, or a line of code — may make a
decision that should have been an ADR. If a downstream document needs an answer, it either cites an
`APPROVED` record here, or it stops.

```
docs/01 ADR/
├── README.md                        this file — the column dictionary
├── ADR_DECISION_RELEASE_LEDGER.tsv  the ledger. The count of record.
├── all-ADRs/
│   └── FR-ADR-nnn.md                one file per decision
└── _sweep/
    ├── lens-1-data-shape.md         the five lens returns, raw and unedited
    ├── lens-2-concurrency.md
    ├── lens-3-money-and-time.md
    ├── lens-4-user-visible.md
    ├── lens-5-operations.md
    └── lens-merge.md                the dedupe, and the cross-lens contradictions
```

**`_sweep/` is evidence, not documentation.** It holds what each of the five independent lenses
returned before anything was merged or adjudicated, kept unedited so the derivation of the records is
checkable rather than asserted. `lens-merge.md` is the pass that hunts for two lenses answering the
same question differently — the defect class the method exists to catch.

**For decision status, trust the ledger, never an ADR file's own header and never this README**
(Art XI.1). The ADR file carries the reasoning; the ledger carries the state.

---

## The two laws that govern every row

**Fail-closed** (Art III.1). Every record is created `NOT_DECIDED` + `HOLD_PENDING_DECISION` +
`NOT_RELEASED`. It moves to `APPROVED` only when both `decided_by` and `decision_date` are filled.
**Silence never counts as approval, retirement, or release.** A row that nobody got to is a blocked
row, not an accepted one.

**Immutable once accepted** (Art III.3). An accepted decision is never edited. A reversal is a new
record that supersedes the old one; the superseded record stays on disk unedited and is marked. A
supersession is itself a claim and gets verified (Art III.4) — a link that resolves is not the same
as a link that is true.

---

## Column dictionary

The ledger is **tab-separated** with a header row. Read it **header-anchored, never
position-anchored**: find the column by its name, never by counting from the left. A column added in
the middle must not break a reader.

No cell may contain a tab or a newline. An unknown value is an **empty cell**, never a guess, never
`N/A`, and never a plausible-looking placeholder.

| # | Column | What it holds | Legal values |
|---|---|---|---|
| 1 | `ledger_id` | Row identity, allocated in filing order, never reused. Stable even if the row is later superseded. | `LED-nnn`, zero-padded to three digits |
| 2 | `pack_id` | The lens or subject group the decision was found under. Lets a reader pull every money decision, or every concurrency decision, as one set. | see **Packs** below |
| 3 | `adr_id` | The record this row governs. One row per ADR, one ADR per row. | `FR-ADR-nnn`, zero-padded to three digits, allocated in filing order, **never reused** (Art III.2) |
| 4 | `title` | The decision in one noun phrase. Must match the `# ` heading of the ADR file. | free text, no tab |
| 5 | `decision_type` | How the decision was arrived at, which is what tells a reader whether a model was allowed to make it. | `CLIENT_RULING` · `JUDGMENT_CALL` · `STRICTER_ADOPTION` · `RESERVED` |
| 6 | `decision_owner` | Who is entitled to decide this. Not who wrote it down. | `client` · `build session` |
| 7 | `decision_status` | Whether it is decided. **The fail-closed column.** | `NOT_DECIDED` · `APPROVED` · `REJECTED` · `SUPERSEDED` |
| 8 | `decision_outcome` | What the decision was. | `HOLD_PENDING_DECISION` · `ADOPTED` · `ADOPTED_PROVISIONAL` · `WITHDRAWN` · `SUPERSEDED_BY_<adr_id>` |
| 9 | `release_decision` | Whether the content of this record is cleared to be carried into derived documents. | `NOT_RELEASED` · `RELEASE_APPROVED` · `RELEASE_WITHHELD` |
| 10 | `release_status` | Whether that release has actually happened yet. Distinct from column 9 on purpose: cleared is not the same as landed. | `NOT_RELEASED` · `RELEASED` |
| 11 | `decided_by` | The named authority behind the decision. **Required for `APPROVED`.** | `Aniruddha Jathar (SRC-003)` for a client ruling · `build session (Art III.9)` for a technical call or a stricter adoption · empty when `NOT_DECIDED` |
| 12 | `decision_date` | The date the authority in column 11 decided. **Required for `APPROVED`.** | `YYYY-MM-DD` · empty when `NOT_DECIDED` |
| 13 | `source_file` | The clause this decision derives from. **Must resolve.** | one or more of `SRC-001 §n` · `SRC-002 §n` · `SRC-001 §E E-n` · `SRC-002 §E E-n` · `SRC-003 <ROW-ID>` · `SRC-003 C-n`, separated by `; ` |
| 14 | `evidence_record` | Where the reasoning lives. | `all-ADRs/FR-ADR-nnn.md` |
| 15 | `last_updated` | When this **row** last changed. Not when the decision was taken. | `YYYY-MM-DD` |
| 16 | `notes` | One line. The caveat a reader needs before acting on the row — a provisional reading, a batched reversal, a dependency. | free text, no tab |
| 17 | `included_in_brd` | Proof the decision landed in `02 BRD`. | `NOT_INCLUDED` · `INCLUDED` · `NOT_APPLICABLE` |
| 18 | `included_in_prd` | Proof it landed in `03 PRD`. | same |
| 19 | `included_in_bible` | Proof it landed in `05 Bible`. | same |
| 20 | `included_in_datamodel` | Proof it landed in `06 DataModel`. | same |

### `decision_type`, in detail

`CLIENT_RULING` — the client decided it and the answer is in a frozen source. `decided_by` names the
client and the source row. A model transcribed it; a model did not choose it.

`JUDGMENT_CALL` — a non-reserved **technical** question, ruled by the build session under the
standing delegation in Art III.9. It binds, and **the client may reverse any of them at any time.**
Where the matter is reserved-but-reversible, Art III.9 permits deciding then batching for reversal;
those rows say so in `notes` and are surfaced to the client rather than buried.

`STRICTER_ADOPTION` — the build session chose the more restrictive of two permitted options.
Art III.10: adopting a stricter option is not a waiver and needs no signature.

`RESERVED` — money, anything irreversible or public, secrets, legal and data protection, amending the
Constitution, what the product is and what "done" means, scope changes, waiving any quality check, or
anything marked `[HUMAN]` (Art III.8). **No model decides these at any confidence.** The record
exists so the question is visible and traceable; it stays `NOT_DECIDED` until the client answers, and
the question is also carried as an Article X row. **No timeout defaults past a reserved matter** — if
the approver is unavailable, the dependent work stops.

### The four `included_in_*` columns

These are the **anti-drift mechanism** (Art III.5). A decision is not finished when it is decided; it
is finished when it can be shown to have *landed*. Flip a cell to `INCLUDED` only with the carrying
section cited in `notes`, and **derive the cell from the citations actually present in the target
document**, never by assertion. `NOT_APPLICABLE` is legal but must be justified in `notes` — a
decision that lands in no derived document at all is usually a decision that was not needed.

**Every cell currently reads `NOT_INCLUDED`, and that is correct.** `02 BRD`, `03 PRD`, `05 Bible`
and `06 DataModel` do not exist yet. A cell reading `INCLUDED` today would be a false claim about a
document nobody has written.

---

## Packs

`pack_id` records which of the five lenses surfaced the decision, plus one governance group. The
five lenses were run as independent parallel passes over the three frozen sources, and then merged
specifically to hunt for two lenses answering the same question differently.

| `pack_id` | Lens |
|---|---|
| `PACK-GOV` | Governance, provenance and the stack lock |
| `PACK-DATA` | Data shape — entities, keys, constraints, nullability, cascades |
| `PACK-CONC` | Concurrency — every place two actors touch one thing |
| `PACK-MONEY` | Money and time — currency, rounding, showtime boundaries, retention, the cut-off |
| `PACK-UX` | User-visible behaviour — what a person sees, is told, and is stopped from doing |
| `PACK-OPS` | Operations — config, health, shutdown, logging, queues, deploys, failure modes |

---

## The shape of an ADR file

Every `all-ADRs/FR-ADR-nnn.md` carries, in this order: a status block, **Context** (why this is a
question at all), **Decision** (what is ruled, in the imperative), **Alternatives rejected** (each
with the reason it lost — a rejected alternative with no reason is not a record of thinking),
**Source** (the clause it derives from), and **Consequences** (including the ones that are bad).

A record whose `decision_type` is `RESERVED` still carries all six sections. Its **Decision** section
states what is *not* decided and names who must decide it. That is the point of filing it.

---

## Rules a writer must not break

**Every `source_file` cites a clause that exists.** `SRC-001`, `SRC-002` or `SRC-003`, and it must
resolve when you go and look. A dangling citation is a defect, not a typo — it means a decision was
derived from something nobody said.

**Credentials never appear here** (Art III.6). Not in an ADR, not in the ledger, not in a note. That
includes anything identifying a person: `SRC-003 OPEN-OPS-01` carries a redaction, and nothing
downstream needs the literal string.

**The repository became private on 2026-08-14, and this rule did not move** (`FR-ADR-071`). The floor
is constitutional, not a consequence of visibility — a private repository is cloned, shared and
flipped public, each of which leaks a committed secret just as fast. Several records written earlier
that day justify the floor by citing publicity; they reach the right conclusion for a weaker reason
than they needed, and `FR-ADR-071` says so without editing them, because Art III.3 makes an
`APPROVED` record immutable.

**An unknown becomes an Article X row, never a plausible guess** (Art VII.3). An `OPEN` question
filled in with something sensible is the cardinal sin of this project.

**Status law applies to every claim in an ADR** (Art III.7): `RULED` decided with a citation ·
`PROVISIONAL` written down with a ruling outstanding · `OPEN` genuinely unruled, escalate, never
invent · `ASSUMED` inference, and it never hardens into a constraint.

**Anything said about AWS runtime behaviour is labelled `(reasoned, not observed)`** (Art VIII.3).
This build session has never watched this application run in AWS.
