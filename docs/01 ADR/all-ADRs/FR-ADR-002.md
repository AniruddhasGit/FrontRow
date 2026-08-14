# `SRC-003` is the client's rulings, diverging from the prior project's numbering

```
ADR id ............ FR-ADR-002
Pack .............. PACK-GOV
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §13.5
Constitution ...... frontrow-constitution@0.1.0
```

> **This id is reserved and may not be reallocated.** `SRC-002` cites `FR-ADR-002` by name in its
> numbering note, and `SRC-002` is frozen and SHA-256 hashed. Moving this decision to another id
> would leave a dangling reference inside a file that cannot be edited.

## Context

This project runs the AI-SDLC method proved on SpendWise. On that project the frozen source set was
two files: `SRC-001` for the client's requirements and `SRC-002` for the client's *rulings* on the
open questions.

FrontRow arrived as two separate written inputs rather than one. `CLIENT_ASK.md` is the client
speaking as the cinema operator about what the product must do. `CLAUDE_CODE_BRIEF.md` is the same
person speaking as the developer about how it must be built, what it may be built from, and who
builds which part. Both are frozen inputs of equal standing and neither is a ruling on the other.

That leaves the rulings without a slot. Filing them as `SRC-002` would have collided with the build
mandate; folding the build mandate into `SRC-001` would have destroyed the distinction that
`CONSTITUTION.md` Art II.2 depends on — that where the two disagree, neither silently wins.

`SRC-002 §13.5` requires any decision the client did not specify to be recorded with its reason and
the alternative rejected. A silent renumbering against the prior project's convention is exactly the
kind of drift that rule exists to prevent.

## Decision

Three frozen sources, in dependency order:

- **`SRC-001`** — the product requirement, from `CLIENT_ASK.md`. Cited as `SRC-001 §n`.
- **`SRC-002`** — the build mandate, from `CLAUDE_CODE_BRIEF.md`. Cited as `SRC-002 §n`.
- **`SRC-003`** — the client's rulings on the open questions. Cited as `SRC-003 <ROW-ID>`, where the
  row id is the `OPEN-XXX-nn` the question was raised under, or `C-n` for a reconciliation.

Errata are cited as `SRC-001 §E E-n` and `SRC-002 §E E-n`.

**The divergence is recorded, not hidden.** A reader who knows SpendWise and expects `SRC-002` to
hold rulings finds this record instead of a silent surprise.

## Alternatives rejected

**Keep the prior project's numbering and merge the build mandate into `SRC-001`.** Rejected because
`CONSTITUTION.md` Art II.2 turns on being able to tell the two apart. Five known conflicts between
them — payment, the role count, cancellation, reporting and the queue technology — are only visible
as conflicts because the two documents are separately addressable. Merging them would have converted
five escalations into five silent resolutions.

**Keep the prior numbering and file the rulings as `SRC-002`, renaming the build mandate.** Rejected
because the build mandate was frozen and hashed first. Renaming a frozen source invalidates every
citation already written against it, which is the failure Art II.5 exists to catch.

**File the rulings as an appendix to `SRC-001`.** Rejected because the rulings correct both sources.
Ten errata land on `SRC-001` and six on `SRC-002`. An appendix to one source that governs the other
is a citation shape nobody can follow.

## Source

`SRC-002 §13.5` — "When you make a decision I did not specify, record it in `docs/decisions.md` with
the reason and the alternative you rejected." The location moved to this folder under `FR-ADR-008`;
the obligation is the same one.

The numbering note in `SRC-002` that names this id is build-session text inside a frozen file, not
client text, and says so where it stands.

## Consequences

`FR-ADR-002` is permanently allocated to this decision. It is never reused and never renumbered,
because `SRC-002` cannot be edited to follow it.

`tools/consistency_check.py` rule 1 requires every `FR-ADR-###` mentioned anywhere in `docs/`,
`CLAUDE.md` or `CONSTITUTION.md` to resolve to both a file and a ledger row. Before this record
existed the checker exited 1 on exactly this reference. Filing it closes that failure.

Any fourth frozen source is `SRC-004` and needs its own record explaining what it is, because the set
is no longer self-describing by convention alone.
