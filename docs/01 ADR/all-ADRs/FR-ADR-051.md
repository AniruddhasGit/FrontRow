# Accessibility: WCAG 2.2 AA as the target, with every contrast figure computed and recorded

```
ADR id ............ FR-ADR-051
Pack .............. PACK-UX
Decision type ..... STRICTER_ADOPTION
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §5.2.2; SRC-001 §6.1; SRC-003 OPEN-SEAT-02; SRC-003 OPEN-SCALE-02; SRC-002 §2.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

No frozen source names an accessibility standard. `SRC-001 §5.2.2` requires seat states to be
*clearly* distinguished, and `§6.1` requires the site to work well on a phone. That is the whole of the
input.

`SRC-003 OPEN-SEAT-02` is adjacent and must not be confused with this. The client ruled out
**accessible-seat marking** — a product feature about wheelchair spaces — on the grounds that this is a
demonstration project. That says nothing about whether the *interface* is usable by a person with a
disability, and reading it as a licence to skip interface accessibility would be reading a ruling
wider than it was given.

The reason this needs a record rather than a style preference is that the design system is written
next, and every contrast decision it makes is either computed or claimed. `CONSTITUTION.md` Art VII.1
forbids invented evidence, and a contrast ratio nobody calculated is invented evidence.

## Decision

**Target: WCAG 2.2 Level AA.** Adopted as the build session's own standard under Art III.9. Nobody
asked for it; adopting a stricter option needs no signature (Art III.10).

**Every contrast ratio in the design system is computed and recorded, never asserted.** The token file
carries, for every foreground-on-background pair actually used, the computed ratio and the threshold
it is being checked against — 4.5:1 for body text, 3:1 for large text and for non-text interface
components. A colour pair with no recorded figure has not been checked, and a design review may not
pass it.

**Seat states carry a non-colour cue** (`FR-ADR-045`). This is where the standard has teeth on the most
important screen: available, held-by-me, held-by-other and sold are distinguished by shape or border
treatment as well as colour, so `SRC-001 §5.2.2`'s "clearly distinguished" holds for a colour-blind
customer.

**Every seat has an accessible name stating its identity, its category and its state** — for example
"Row C seat 12, Premium, available". A grid of unlabelled buttons is unusable without sight.

**Keyboard operation:** every interactive element is reachable and operable by keyboard, focus order
follows the visual order, and the focus indicator is visible against every background it can appear
on. Grid navigation within the seat map uses arrow keys, with the map as a single tab stop rather than
220 of them — tabbing through 220 seats to reach the checkout button is technically conformant and
unusable.

**Forms:** every input has a programmatically associated label, errors are associated with their
field, and an error is announced rather than only coloured red.

**Motion and timing:** the hold countdown (`FR-ADR-047`) is a time limit, and WCAG's timing criterion
normally requires it to be adjustable. **It is not adjustable here**, because the limit exists to
release a scarce resource to other customers and extending it is refused by `FR-ADR-027`. That is a
known deviation from the AA criterion and it is recorded as one rather than papered over — the
mitigation is that the limit is clearly displayed from the start, warned at 60 seconds, and the
customer's selection is restored on expiry so nothing is lost but the seats.

**What is explicitly not in scope:** accessible-seat marking as a product feature
(`OPEN-SEAT-02`), a screen-reader-optimised alternative to the seat map, and formal conformance
testing or an accessibility statement. Those are not built and are not claimed.

**No conformance claim is published.** The target is what the work is measured against; a claim would
need testing this project has not done, and Art VII.1 forbids claiming it.

## Alternatives rejected

**Set no target and handle accessibility case by case.** Rejected. Without a target the design review
has nothing to check against, and "looks fine" becomes the criterion.

**Target AAA.** Rejected. The 7:1 contrast requirement would constrain the palette severely for a
demonstration project, and AAA is not achievable for all content by its own admission.

**Read `OPEN-SEAT-02` as ruling out interface accessibility too.** Rejected above — it is a ruling
about a seat attribute, not about the interface.

**Make the hold countdown adjustable to satisfy the timing criterion.** Rejected. It contradicts
`FR-ADR-027` and would let one customer hold seats indefinitely. The deviation is recorded instead.

**Claim WCAG 2.2 AA conformance in a published statement.** Rejected under Art VII.1. Untested is
untested.

**Give each of 220 seats its own tab stop.** Rejected above.

## Source

`SRC-001 §5.2.2` (clearly distinguished) · `§6.1` (works well on a phone) ·
`SRC-003 OPEN-SEAT-02` (accessible *seats* are out of scope — the interface is a separate matter) ·
`OPEN-SCALE-02` `ASSUMED` (220 seats on a small screen) ·
`SRC-002 §2.2` (say the literal thing — which applies to interface copy as much as to explanation).

The standard and the computed-not-claimed rule are the build session's under Art III.9, adopted as a
stricter option under Art III.10.

## Consequences

`docs/05 B DesignSystem/` must ship a token file where every colour pair carries a computed ratio.
That is a mechanical check a review can perform, which is the point — the alternative is a reviewer
squinting at a swatch.

The seat map is the hardest surface to make keyboard and screen-reader operable, and it is the one
that matters most. Arrow-key grid navigation with one tab stop is the decision that makes it possible;
implementing it well is Phase 3 work and should be treated as a feature, not a polish pass.

**The timing deviation is a real, recorded gap.** It belongs in the architecture folder's list of
deliberate gaps alongside the others, so it is a known trade rather than an oversight found later.

Contrast figures constrain the palette before it is chosen, which is why this record exists before the
design system rather than after it.
