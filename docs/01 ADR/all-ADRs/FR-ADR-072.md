# Token names are prefixed `--fr-` and grouped by role, not by colour

```
ADR id ............ FR-ADR-072
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §4.1; FR-ADR-044; FR-ADR-051; SRC-003 OPEN-SEAT-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`FR-ADR-044` rules CSS Modules over a custom-property token layer, and `FR-ADR-051` fixes WCAG 2.2 AA
with computed figures. **Neither names the tokens.** `GOAL_04` had to choose a convention to write
`tokens.css` at all, and Art III.9 requires the choice be logged rather than absorbed.

## Decision

**Prefix `--fr-`, and group by the role a token plays, never by the colour it holds.**

`--fr-seat-available`, not `--fr-grey-300`. `--fr-surface-inset`, not `--fr-off-white`. A name that
describes appearance goes stale the moment the appearance changes and leaves the codebase saying
`--fr-blue` about something brown.

Three consequences fall out of it and are enforced by `contrast.py`, not by review:

- **Every colour token carries a role annotation**, so the checker can derive which pairs to measure
  from the file itself rather than from a hand-written list. Check `ANNOTATED`.
- **A foreground names the ground it sits on** (`on:`), so a pair is a fact in the file, not a
  guess. Check `ON-RESOLVES`.
- **A token exempt from contrast must say why** (`@decor why:"…"`). Check `DECOR-WHY`. Three
  exemptions exist and each states its reason.

**There is deliberately no per-category colour token.** Seat categories are `ASSUMED`
(`SRC-003 OPEN-SEAT-01` — the client said "you pick"), so hardening Standard / Premium / Recliner
into three colour tokens would let an assumption become a constraint through the back door, which
Art III.7 forbids. Category is carried by band position and the legend instead.

## Consequences

- Renaming a token is a mechanical, checkable change: `TOKEN-COVERAGE` fails in both directions if
  `tokens.css` and `COMPONENTS.md` disagree, and both counts are currently 0.
- The convention is machine-enforced, so it cannot rot quietly the way a style guide does.
- A fourth seat category costs a row in a table and no token at all.

## Alternatives rejected

**Unprefixed names** (`--seat-available`). Rejected — the frontend will eventually hold third-party
CSS, and an unprefixed custom property is a collision waiting for a specific unlucky afternoon.

**Colour-scale naming** (`--fr-grey-300`). Rejected for the reason above, and because it makes the
contrast checker impossible to derive: a scale name does not say what sits on what.
