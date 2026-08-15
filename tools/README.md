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

### The nine rules

Each is independently reportable: its own status line, its own count, its own detail block.

| # | Key | What it proves |
|---|---|---|
| 1 | `adr-reference` | every `FR-ADR-###` in `docs/`, `CLAUDE.md` or `CONSTITUTION.md` has **both** a file in `docs/01 ADR/all-ADRs/` **and** a row in `ADR_DECISION_RELEASE_LEDGER.tsv` |
| 2 | `open-reference` | every `OPEN-XXX-nn` mentioned anywhere is **either** a table row in `CONSTITUTION.md` Article X **or** a section heading in `SRC-003`. The id pattern is `OPEN-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+` — **widened 2026-08-15**, see below |
| 3 | `source-citation` | every `SRC-001 §n` / `SRC-002 §n` citation lands on a clause anchor that the source actually defines |
| 4 | `erratum-crossref` | `SRC-003`'s errata tables and the target sources' `§E` sections agree — **both directions**, and on the clause each erratum corrects. Also checks the errata counts `fingerprints.json` records |
| 5 | `fingerprint` | every frozen source hashes to its recorded `sha256` (computed in-process), its recorded byte count matches, and `fingerprints.sha256` agrees with `fingerprints.json` |
| 6 | `readme-paths` | every folder and every path the `docs/README.md` table quotes exists in the repo tree |
| 7 | `prep-queue-status` | every row of `docs/30 Deployment/AWS_PREP_QUEUE.md` carries a non-empty Status |
| 8 | `ledger-header` | the ledger's header row matches the order `docs/01 ADR/README.md` documents, **anchored on header names, never on positions** |
| 9 | `readme-state` | every `State` cell in the `docs/README.md` folder table agrees with the tree: a folder marked `written` has a file, one marked `empty` has nothing but `.gitkeep`. **This is the guard on the cell rule 6 defers on** |

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

  > **And that exemption failed exactly the way an exemption fails, on 2026-08-15.** Five written
  > folders — `01 ADR`, `02 BRD`, `03 PRD`, `05 B DesignSystem`, `30 Deployment`, one of them a
  > 25,000-line document — were still marked `empty`. Rule 6 passed green while deferring six
  > claims it should have been gating, and **said so on its own summary line**, which nobody read:
  > *"23 of 23 path claims resolve · 6 path claim(s) in rows the table itself marks
  > not-yet-written, deferred."*
  >
  > **The document's staleness was setting the check's coverage.** The more wrong the table got, the
  > less rule 6 checked, and the less it checked the more reliably it went green. That is worse than
  > measuring the wrong thing: the thing being measured was deciding how much would be measured, and
  > deciding downward.
  >
  > **Rule 9 is the fix, and the exemption stays.** Removing the deferral would make an honest table
  > fail on folders genuinely not yet written, which is the behaviour it exists for. So rule 9 guards
  > the cell the deferral keys on instead. **Neither rule is sufficient alone** — rule 6 without
  > rule 9 can be switched off by a stale cell, and rule 9 without rule 6 is bookkeeping nobody
  > reads. Correcting the five cells moved rule 6 from `23 of 23 · 6 deferred` to
  > `24 of 24 · 5 deferred`: one claim left the exemption and passed.
  >
  > **Read the deferred count on every run.** A rising one is the alarm.

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

### Rule 2's id pattern was widened on 2026-08-15, and why that is not a tightening

The original pattern was `OPEN-[A-Z]+-\d+`. Because `[A-Z]+` matches neither a second hyphen nor a
digit, two id shapes were invisible to it: `OPEN-SEATMAP-DEGRADED-01` and `OPEN-CACHE503-01`.

**They were invisible in both directions at once**, which is why nothing went red. The same pattern
harvests the known rows out of `CONSTITUTION.md` *and* finds the references in the corpus — so an
id of an unmatchable shape was missing from both sets, and the two blindnesses cancelled into a green
line. The PRD raised it in its `S8.7` after two lanes invented ids of that shape and referenced them
with nothing filed anywhere.

**It had a live consequence by the time it was fixed.** `OPEN-CACHE503-01` had since been filed as a
genuine Article X row in `X.0b`, so every reference to a real, filed row had been going unchecked.
Widening took rule 2 from **57 rows / 826 references** to **58 rows / 829 references**.

**The general form: a rule that derives both its known set and its referenced set through one narrow
pattern cannot report the ids that pattern cannot see.** It has no vocabulary for them. That makes
widening not a tightening of an existing check but the only way the check can speak about them at
all — and it is why the two new plants use those exact shapes. A plant that fires under the old
pattern too would prove nothing about the widening.

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
no rule is exempt from red-proofing for being early. **Nine rules, eleven plants** — rule 2 carries
three, one per id shape it must be able to see. Rule 8's plant is adaptive: it swaps two of the
columns the real README documents once that README exists, and only synthesises an order when it
does not.

**A check nobody has watched fail is decoration.** Run `--selftest` before trusting a green.

### Adding a rule

1. Write `rule_N_<key>(root, corpus) -> Rule`, set `r.unit` and `r.checked`, call `r.fail(...)` per
   finding or `r.skip(reason)` when the subject is absent, and append it to `RULES`.
2. Write a `_plant_N(work_root) -> bool` that makes a **real** violation of it and returns `False`
   if the mutation was a no-op, and append `(N, description, _plant_N)` to `PLANTS`.
3. Run `--selftest`. If the new rule does not go from *n* to *n+1*, it does not ship.
