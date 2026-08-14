# The mandate's flat `docs/` filenames map onto the numbered folder set

```
ADR id ............ FR-ADR-008
Pack .............. PACK-GOV
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §11; SRC-002 §6.4; SRC-002 §13.5; SRC-002 §2.4; SRC-002 §12.8
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §11` sketches a repository layout with four flat files under `docs/`: `architecture.md`,
`decisions.md`, `deployment-tasks.md` and `runbook.md`. Other clauses cite those paths by name —
`§6.4` says the Zone C specifications go in `docs/deployment-tasks.md`, `§13.5` says every unspecified
decision is recorded in `docs/decisions.md`.

This repository does not have those files. It runs the AI-SDLC method's numbered folder set, where
`docs/` holds thirteen-plus numbered folders in dependency order and `CONSTITUTION.md` Art XI.3 fixes
that set — no folder is added, removed or renumbered.

Both are the client's instructions. Left unrecorded, a future session reads `§13.5`, finds no
`docs/decisions.md`, and either creates one — producing a second decision register competing with the
ledger — or silently ignores a clause of a frozen source.

## Decision

**The numbered folder set is the layout. The mandate's four filenames are read as naming a
deliverable, not a path.** Each maps to a location:

| `SRC-002 §11` path | Where it actually lives | Why |
|---|---|---|
| `docs/decisions.md` (`§13.5`) | `docs/01 ADR/` — one record per decision plus `ADR_DECISION_RELEASE_LEDGER.tsv` | The ledger is the decision authority of record under Art III.1 and carries decision *and release* state, which a flat markdown file cannot |
| `docs/deployment-tasks.md` (`§6.4`) | `docs/30 Deployment/` — one specification per Zone C item, plus `AWS_PREP_QUEUE.md` | `§6.4` requires four things per item; one file per item keeps them separately citable |
| `docs/architecture.md` | `docs/07 Architecture/` — `for_llm/` and `for_humans/` | `§2.1` and `§2.4` ask for explanation aimed at a human reader; a session-orientation document is a different audience |
| `docs/runbook.md` (`§12.8`) | `docs/35 Hypercare/` | It is the document for operating the system after it is running, which is what that folder holds. Delivered in Phase 7, as `§12.8` requires |

**The obligation in each clause is unchanged.** `§13.5` still binds: every decision the client did not
specify is recorded with its reason and the alternative rejected. Only the filename moved.

`SRC-002 §2.4`'s per-phase explanation file — what was built, why, and what breaks in production if
the deployment is wrong — is written at the close of every phase and is not one of the four above. It
is a separate deliverable and it keeps its own place in the phase's folder.

The `backend/`, `frontend/`, `scripts/` and `docker-compose.yml` parts of `§11` are **not** remapped.
That is the application layout and it is followed exactly.

## Alternatives rejected

**Create the four flat files as `SRC-002 §11` writes them.** Rejected because `docs/decisions.md`
would become a second decision register alongside the ledger, and two registers that drift by one row
invalidate both. Art XI.1 says trust the ledger; a competing file makes that instruction ambiguous.

**Create the flat files as stubs that point at the real locations.** Rejected as four files whose only
content is a redirect. A reader who follows one has learned nothing the repository tree would not have
told them, and each is one more thing to keep current.

**Renumber or add a folder so the names line up.** Rejected under Art XI.3, which fixes the folder
set.

**Treat the mismatch as too small to record.** Rejected under `§13.5` itself. This *is* a decision the
client did not specify, and the whole point of that clause is that small unrecorded divergences are
the ones nobody can reconstruct later.

## Source

`SRC-002 §11` (the sketched layout) · `§6.4` (`deployment-tasks.md`) · `§13.5` (`decisions.md`) ·
`§2.4` (per-phase explanation) · `§12.8` (the runbook, Phase 7).

## Consequences

Any downstream document citing `docs/decisions.md` or `docs/deployment-tasks.md` as a live path is
citing something that does not exist. Art XI.1 already says to trust the repository tree over a path
quoted in prose; this record is why that rule earns its place here.

`tools/consistency_check.py` rule 6 verifies path claims made in README files against the tree, which
catches the reverse mistake — a document claiming a path that was never created.
