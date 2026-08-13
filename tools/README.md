# `tools/` — the mechanical checks

Standard library Python only. No dependency file, no network, no credentials, no shelling out.
Everything here runs on Windows under `py`, and on anything else under `python3`.

```
py tools/consistency_check.py             run every rule against the repo
py tools/consistency_check.py --selftest  plant a real violation of each rule, prove each fires
py tools/consistency_check.py --root .    check a different checkout
```

---

## `consistency_check.py`

The **cheap mechanical layer** of the two layers `CONSTITUTION.md` Art IX.6 requires, and the
Definition-of-Done line every file in `goals/` names. It answers exactly one question:

> **Does every cross-reference actually resolve?**

That is all it answers. It cannot see two documents that each read perfectly well alone and
contradict each other — that is the expensive layer, `docs/12 DesignReview/` and `GOAL_13`. A green
run here is not a claim that the documents are right; it is a claim that nothing in them points at
something that is not there.

The class of defect it exists for is **"I reported an action I did not perform"**: an ADR id filed
in prose and never filed on disk, an erratum announced and never written, a prep-queue row claimed
and never given a Status. On the prior project a small script caught four of those after an
expensive adversarial agent had already spent real effort finding them.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | every rule passed, or skipped cleanly |
| `1` | at least one rule failed — a real unresolved cross-reference |
| `2` | the tool itself errored. Not a finding about the repository |

### The eight rules

Each is independently reportable: its own status line, its own count, its own detail block.

| # | Key | What it proves |
|---|---|---|
| 1 | `adr-reference` | every `FR-ADR-###` in `docs/`, `CLAUDE.md` or `CONSTITUTION.md` has **both** a file in `docs/01 ADR/all-ADRs/` **and** a row in `ADR_DECISION_RELEASE_LEDGER.tsv` |
| 2 | `open-reference` | every `OPEN-XXX-nn` mentioned anywhere is **either** a table row in `CONSTITUTION.md` Article X **or** a section heading in `SRC-003` |
| 3 | `source-citation` | every `SRC-001 §n` / `SRC-002 §n` citation lands on a clause anchor that the source actually defines |
| 4 | `erratum-crossref` | `SRC-003`'s errata tables and the target sources' `§E` sections agree — **both directions**, and on the clause each erratum corrects. Also checks the errata counts `fingerprints.json` records |
| 5 | `fingerprint` | every frozen source hashes to its recorded `sha256` (computed in-process), its recorded byte count matches, and `fingerprints.sha256` agrees with `fingerprints.json` |
| 6 | `readme-paths` | every folder and every path the `docs/README.md` table quotes exists in the repo tree |
| 7 | `prep-queue-status` | every row of `docs/30 Deployment/AWS_PREP_QUEUE.md` carries a non-empty Status |
| 8 | `ledger-header` | the ledger's header row matches the order `docs/01 ADR/README.md` documents, **anchored on header names, never on positions** |

### What is out of scope, and why

`tools/` is skipped because this file carries planted violations as string literals — scanning it
would make the checker fail on its own selftest fixtures. `handoffs/` and `PROGRESS.md` are skipped
because they are narrative: their job is to record what happened *including defects*, and a handoff
that writes "claims `FR-ADR-994` is filed" is reporting a defect, not committing one. Flagging those
would punish exactly the honesty Art VII requires.

### SKIP is a first-class outcome

Most of `docs/` is still empty. A rule whose subject does not exist yet prints a `SKIP` line with
the reason and does not gate, so the tool is useful **today** rather than only at the end.

Two deliberate refinements of that idea:

- **Rule 1 does not skip on an empty ledger.** Its subject is the *reference*, not the ledger. If a
  document names `FR-ADR-002` and no ledger exists, that reference is dangling — which is the
  finding, not an excuse to stay quiet.
- **Rule 6 defers, per row, on the table's own `State` cell.** A row the index marks `empty` is
  describing a folder that has not been written; the paths in it are a plan, not a claim about what
  exists. Those are counted and reported on the summary line, never gated. The row starts being
  gated the moment its `State` flips to `written`.

### Rule 8 expects the column order to be documented in a readable shape

`docs/01 ADR/README.md` must carry the ledger's column order in one of three forms — the first that
yields three or more names wins:

1. a fenced block of tab-separated or newline-separated column names;
2. a markdown table with a `Column` (or `Column name`, or `Field`) header — its cells, in row order;
3. a numbered or bulleted list of backticked names.

The current README uses form 2, and the check reads all twenty columns from it. Failures are
reported by **name**: a column the README documents and the ledger lacks, a column the ledger
carries and the README does not, or the first pair of shared columns whose relative order differs.
One inserted column therefore reports as one finding, not as every column after it.

---

## `--selftest` is the point of the file

```
py tools/consistency_check.py --selftest
```

For **every** rule it copies the repo to a scratch directory, plants a **real** violation of that
rule, re-runs the whole checker, and requires *that rule's* failure count to **rise**. It prints
`n/n checks red-proofed`.

It measures by **delta**, never against a clean baseline. A checker that can only be red-proofed on
a green repository is a checker you cannot trust on the day you need it — which is precisely the day
something is red. The baseline is measured and printed, not demanded.

Where a rule's subject does not exist yet, the plant **builds** the fixture and then violates it, so
no rule is exempt from red-proofing for being early. Rule 8's plant is adaptive: it swaps two of the
columns the real README documents once that README exists, and only synthesises an order when it
does not.

**A check nobody has watched fail is decoration.** Run `--selftest` before trusting a green.

### Adding a rule

1. Write `rule_N_<key>(root, corpus) -> Rule`, set `r.unit` and `r.checked`, call `r.fail(...)` per
   finding or `r.skip(reason)` when the subject is absent, and append it to `RULES`.
2. Write a `_plant_N(work_root) -> bool` that makes a **real** violation of it and returns `False`
   if the mutation was a no-op, and append `(N, description, _plant_N)` to `PLANTS`.
3. Run `--selftest`. If the new rule does not go from *n* to *n+1*, it does not ship.
