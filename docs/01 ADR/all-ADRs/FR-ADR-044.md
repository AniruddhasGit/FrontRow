# CSS Modules with a plain-CSS token layer, and no component library

```
ADR id ............ FR-ADR-044
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §4.1; SRC-002 §6.1.2; SRC-002 §13.1; SRC-002 §5.4.2; SRC-001 §6.1; SRC-001 §6.4
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §4.1` fixes the frontend as React + Vite + TypeScript. `§6.1.2` puts all frontend code and
styling in Zone A. Neither says how it is styled.

`§13.1` is the constraint that shapes the answer: "Ask me before adding any dependency that is not
obviously necessary." A component library is a dependency, and a large one. Tailwind is a dependency
with a build-step integration. Both would need the client's permission before they entered the design,
and neither has been asked for.

So the real question is which approach is defensible **without** asking — and whether it is worth
spending one of the client's decisions on a styling library at all.

## Decision

**CSS Modules, which ship with Vite, over a plain-CSS custom-property token layer. No component
library, no CSS-in-JS runtime, no utility framework.**

**Two layers, and the split matters:**

**1. Tokens — one global stylesheet of CSS custom properties on `:root`.** Colour, spacing, type
scale, radius, shadow, and the seat-state palette. Plain CSS, no preprocessor. This file is
`docs/05 B DesignSystem/`'s output made real, and it is the single place a value is defined.

**2. Components — one `.module.css` per component**, consuming those properties. Vite hashes the class
names, so a class defined in one component cannot collide with or leak into another. That is the
property that makes a growing stylesheet survive without a naming convention nobody enforces.

**Why not ask for a component library.** `§4.12` and `§13.1` mean asking costs the client a decision.
This product has a small component inventory — a seat map, a movie card, a form, a table, a banner —
and its most important component, the seat map, would be hand-built under any library. A component
library would supply the parts that are cheap and none of the part that is hard.

**Why not Tailwind.** It is a real dependency with a build integration and a class vocabulary that
takes over the markup. It is a reasonable choice for a larger interface and it would need permission
under `§13.1` for a benefit this interface's size does not realise.

**Why not CSS-in-JS.** It adds a runtime to the bundle. `§5.4.2` targets a final image under 250 MB
and the static frontend is budgeted at roughly 15 MB (`FR-ADR-064`); a styling runtime spends that
budget on something plain CSS does for free. It also moves style computation into render.

**Consequences for accessibility, which is not a styling afterthought:** contrast figures are
**computed and recorded**, never asserted (`FR-ADR-051`). CSS Modules make that checkable because the
values live in one token file rather than being scattered through utility classes.

**Responsive by construction.** `SRC-001 §6.1` says a website that works well on a phone is enough and
`FR-ADR-016` sets a 220-seat hall on a 375-pixel-wide screen as the design target. Layout uses
flexbox and grid with relative units; the seat map scrolls inside its own container so the page body
never scrolls horizontally.

**One language, English.** `SRC-001 §6.4` excludes a multi-language interface, so no locale switcher
and no translation layer. Strings live in the components. `§6.6` says the client may ask later, so
strings are not built into styling or into image assets, which is where a later translation gets
stuck.

## Alternatives rejected

**A component library — MUI, Chakra, Radix, shadcn.** Rejected above: needs permission under `§13.1`,
supplies the easy parts, does not supply the seat map, and adds bundle weight against a 15 MB budget.

**Tailwind CSS.** Rejected above.

**CSS-in-JS — styled-components, Emotion.** Rejected above.

**Plain global CSS with a BEM naming convention.** Rejected. BEM is a convention, and a convention is
enforced by whoever remembers it. CSS Modules make the same guarantee mechanically, at zero cost,
using something Vite already does.

**Sass or another preprocessor.** Rejected. CSS custom properties, nesting and `@layer` cover what a
preprocessor was needed for, and it is one more build dependency under `§13.1`.

**Ask the client for permission to add a library anyway.** Rejected as a poor use of a reserved
decision. If the interface later proves this wrong, asking then is a cheap and well-evidenced
question.

## Source

`SRC-002 §4.1` (React + Vite + TypeScript) · `§6.1.2` (frontend styling is Zone A) ·
`§13.1` (ask before adding a dependency) · `§5.4.2` (image size) ·
`SRC-001 §6.1` (works well on a phone) · `§6.4` (no multi-language interface).

The styling approach is the build session's under Art III.9. The client may reverse it, and adding a
library later would be their decision under `§13.1` rather than a reversal of this one.

## Consequences

The component inventory is written by hand, which is more work up front and no dependency to keep
current. For an interface this size that trade is favourable; for a larger one it would not be.

**Every colour pair in the token file gets a computed contrast ratio recorded next to it**, not a
claim. `FR-ADR-051` makes that binding.

The seat map's states must not be distinguished by colour alone (`SRC-001 §5.2.2` requires available,
held and sold to be clearly distinguished). `FR-ADR-045` carries the non-colour cue.

The static frontend container serves a build output with no runtime beyond React itself, which is what
keeps it near the 15 MB budget. *(reasoned from typical figures, not observed.)*
