# Dark mode is built, though no frozen source asks for it, and deleting it stays cheap

```
ADR id ............ FR-ADR-073
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §6.1; SRC-001 §7.3; FR-ADR-051; FR-ADR-072
Constitution ...... frontrow-constitution@0.1.0
```

## Context

**No frozen source requires dark mode.** Not `SRC-001`, not `SRC-002`, not any of the 40 rulings in
`SRC-003`. `GOAL_04` built it anyway, and Art III.9 requires that be a logged decision rather than a
preference that slipped in.

Building something nobody asked for is normally scope creep, which Art III.8 reserves to the client.
This record exists to argue why it is not, and to make the argument falsifiable.

## Decision

**Ship light and dark, both first-class, every palette token defined in both.**

The reasoning is specific to this product rather than general taste: a customer opens this on a phone
(`SRC-001 §6.1`), and a meaningful share of them do it **inside a dark auditorium or a dim lobby**,
which is the one environment the product is definitionally about. A white seat map at full brightness
in a dark room is not a preference question.

**Why it is not scope creep:** the cost is bounded and measured, not open-ended. Two checks hold it
there — `THEME-PARITY` (light and dark declare exactly the same palette tokens) and `DARK-IDENTICAL`
(the two dark blocks are value-for-value identical). Both are red-proofed in `--selftest`. **35
palette tokens in each theme, and the checker fails if they diverge by one.**

**The escape hatch is real and stated:** deleting both dark blocks from `tokens.css` leaves a
complete, passing light system. No component spec branches on theme; no logic reads it. This is the
test of whether the cost was genuinely bounded, and it is written down so a future session can
exercise it rather than rediscover it.

## Consequences

- 35 extra token declarations and two extra checks. No extra component, no extra logic, no
  JavaScript.
- Every contrast figure is measured **twice**, once per theme — 70 pairs rather than 35. The
  system's worst pair, 3.68:1 against a 3.0:1 floor, is worst-of-both.
- If the client says no, removal is a deletion and a re-run of `contrast.py`, not a rewrite.

## Alternatives rejected

**Light only.** Defensible, and the honest default when nothing asks for the feature. Rejected on the
dark-auditorium argument above — but this is the alternative to reach for if the client wants the
surface reduced, and it is one deletion away.

**A user-facing theme toggle.** Rejected outright. That is a preference to persist, a control to
place, and a state to test — a real feature, and genuinely unasked-for. The system follows
`prefers-color-scheme` and stores nothing.

**Ask the client first.** Considered. Rejected because the answer would arrive after the tokens had
to exist, and because the bounded-cost argument makes it reversible — Art III.9's decide-then-batch
path is exactly for this shape of call. **It is hereby batched: one message reverses it.**
