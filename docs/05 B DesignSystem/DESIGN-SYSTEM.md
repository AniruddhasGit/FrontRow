# DESIGN-SYSTEM.md — the identity, and what each token family is for

Four files, and they are not interchangeable.

| File | What it is |
|---|---|
| `tokens.css` | **The source of record.** Real CSS custom properties the Vite build consumes. A value that is not here does not exist. |
| `contrast.py` | The only thing in this repository allowed to produce a contrast figure. |
| `CONTRAST.md` | **Generated** by `contrast.py`. Every number on it was computed. Never edit it. |
| `COMPONENTS.md` | The component specifications, written in terms of the tokens. |
| this file | Why the system looks the way it does, and when **not** to reach for a token. |

Run all three checks before believing any of it:

```
py "docs/05 B DesignSystem/contrast.py" --selftest   red-proof every check
py "docs/05 B DesignSystem/contrast.py"              regenerate CONTRAST.md
py "docs/05 B DesignSystem/contrast.py" --check      verify, write nothing
```

---

## 1. The identity: **half-light**

**An auditorium between the trailers and the film — the house lights down but not
out, and the screen already lit.**

That is the room this product sells access to, and it gives the system a rule that
is physical rather than decorative: **there are two light sources, and each one owns
a meaning.**

| Light | Hue | What it means, everywhere, without exception |
|---|---|---|
| **Screen-light** | a cold cyan | *Yours*, and *live*. Your held seats. The countdown. The focus ring. The screen bar at the top of the map. Light coming off the screen and falling on you. |
| **House-light** | a warm brass | What the *room* offers you. The primary action. The brand. Someone else's live hold — because someone else is sitting in the room, not on your screen. |

Everything else in the palette is neutral: warm bone paper in light theme, deep
blue-black ink in dark. Neutral is the default and the two hues are spent
deliberately, which is why a screen with a live hold on it reads instantly even
though almost nothing on it is coloured.

**Why this suits a cinema booking product specifically.** The decision a customer is
making is *where in a dark room will I sit, and can I still get that seat*. Both
halves of that are light problems. A design that borrows the room's own lighting
does not need to invent a visual language for "yours" versus "someone else's" — the
building already has one. And it inverts cleanly: light theme is the same room with
the house lights up, which is what the foyer looks like, and the paper ground is a
ticket stub.

### 1.1 The signature: the screen bar

At the top of every seat map is a luminous bar labelled `SCREEN`, with a gradient
falloff beneath it that fades into the seat field. It is the brightest element on
the map in dark theme and the darkest in light, and it is the thing this product
will be remembered by.

It is not ornament. It orients the map — a seat grid with no screen is an
unreadable rectangle of squares — and it explains the lightness staircase the seat
states sit on, because the whole map is arranged as light falling away from a
source.

Boldness is spent here and nowhere else. Everything around it is quiet.

### 1.2 The structural device: the stub perforation

A dashed rule, used in exactly **two** places: above the total in the price summary,
and around the booking reference. Both are tears — the line between what you chose
and what you owe, and the line around the part you carry to the door.

It appears nowhere else. A device used everywhere is a texture; a device used twice
is a signal. Ordinary dividers use `--fr-rule-quiet` and look nothing like it.

### 1.3 Typography: numbers are a separate voice

> **Superseded in part by `FR-ADR-074` (2026-11-06):** the client approved two self-hosted web fonts, Inter Tight
> (display and body) and JetBrains Mono (every number). `tokens.css` names them first in each stack, with the
> platform stacks below kept as the fallback. The treatment described here is unchanged.

There are no font files in this system. A font package is a dependency and
`SRC-002 §13.1` requires the client's permission before one is added, so the stacks
are the platform's own and the character comes from the treatment:

- **Display** — the same stack at `--fr-weight-black` with `--fr-track-tight`, used
  large and rarely. Titles and headings only.
- **Body** — regular weight, `--fr-leading-body`, capped at `--fr-measure`.
- **Mono** — and this is the decision that gives the product its voice. **Every
  number a customer reads or repeats is monospaced with tabular figures**:
  showtimes, row letters, seat numbers, prices, the countdown, the booking
  reference.

That last one is not a style choice dressed up as a rationale. `FR-ADR-048` requires
the booking reference in a monospaced face at a size that survives a phone screen at
arm's length at a door. Once one number in the product is mono, every number should
be, or the reference looks like a bug. And tabular figures are functional: a
countdown and a running total that re-flow as their digits change are hard to read
precisely when they matter most.

This product is mostly numbers — times, rows, seats, rupees, a reference. Giving
them their own voice is the typographic idea, and it is specific to this brief.

### 1.4 What was deliberately not done

- No cream-and-serif editorial look. Wrong room, and it is the default an
  unconsidered brief produces.
- No single acid accent on near-black. One accent carries no meaning; two carry
  two, and here they carry the two that matter.
- No hairline broadsheet grid. The seat map is already a dense grid of small
  squares; a second grid competes with the only one that carries information.
- No illustration in an empty state. An empty screen states what is true and offers
  the next action.

---

## 2. The token families — what each is for, and when *not* to use it

`FR-ADR-044` fixes the shape: one global stylesheet of custom properties on
`:root`, one `.module.css` per component, no component library, no CSS-in-JS, no
utility framework, no preprocessor. Naming is not fixed by any record — the `--fr-`
prefix and the family names below are this session's `[JUDGMENT CALL]`.

### 2.1 Spacing — `--fr-space-1` … `--fr-space-7`

A 4px base: 4, 8, 12, 16, 24, 32, 48.

**Do not** use a value between steps. A one-off `6px` is a decision nobody wrote
down, and on a seat map it is the difference between a grid and a smear. If a layout
needs something in between, the layout is wrong.

**Do not** use spacing tokens for seat geometry — that is what `--fr-seat-size`,
`--fr-seat-gap`, `--fr-seat-band-gap` and `--fr-seat-gutter` are for. The seat grid
must be able to change pitch without moving the rest of the page.

### 2.2 Radius — `--fr-radius-sm` … `--fr-radius-pill`

`sm` for seats and chips, `md` for controls and panels, `lg` for cards and sheets,
`pill` for the countdown track and the screen bar.

**Do not** put `pill` on anything rectangular and interactive. A pill-shaped seat
stops reading as a seat, and `radius-lg` on a 24px square erases the square.

### 2.3 Stroke — `--fr-stroke-hair`, `--fr-stroke-bold`

`hair` is a boundary. `bold` is a **state** — and specifically a state that must
survive the colour being removed. It is used for exactly two things: the focus ring,
and the border on a seat you are holding.

**Do not** use `bold` for emphasis. Once a 2px border means three things it means
nothing, and the seat map is where that costs a customer their seats.

### 2.4 Type — family, size, leading, weight, tracking

Six sizes, three leadings, four weights, three trackings.

**Do not** set `--fr-text-2xl` on anything other than the display headline and the
booking reference. It exists to make one thing enormous, and a second enormous thing
halves the effect.

**Do not** use `--fr-track-caps` on sentence-case text — it is for the small
uppercase eyebrow labels only. **Do not** use `--fr-track-ref` anywhere except the
booking reference; it is wide enough to be uncomfortable to read as prose, which is
the point when someone is reading characters out one at a time.

**Do not** use `--fr-font-display` at body size. At small sizes it is
indistinguishable from `--fr-font-body`, so it buys nothing and hides the
distinction where it does matter.

### 2.5 Colour — grounds, foregrounds, boundaries

Every colour token carries a machine-readable role in its trailing comment:

| Role | Floor | Criterion |
|---|---|---|
| `@ground` | — | a background other things sit on |
| `@text` | 4.5:1 | WCAG 2.2 1.4.3 Contrast (Minimum) |
| `@text-lg` | 3:1 | 1.4.3, large text — **defined but unused, on purpose** |
| `@ui` | 3:1 | 1.4.11 Non-text Contrast |
| `@decor` | exempt | and must say `why:"..."` |

Those floors are `FR-ADR-051`'s: WCAG 2.2 Level AA, adopted as this build's own
standard. **The measured figures are in `CONTRAST.md` and nowhere else.** Not in this
file, not in `tokens.css`, not in a code comment.

**`@text-lg` is deliberately unused.** A token does not know what size it will be
set at. Marking a colour "large text only" makes its 3:1 floor a promise about how
a future component will use it, and that promise cannot be checked. Every text
token in this system is held to 4.5:1 regardless of size — stricter, and stricter
needs no signature.

**Do not** add a colour without an annotation. `contrast.py`'s `ANNOTATED` check
fails, and that is the mechanism: a colour cannot enter this system unmeasured.

**Do not** reach for `@decor` to make a check pass. It is an exemption with a
written reason, and there are exactly three of them: the projector falloff under the
screen bar, the cosmetic list divider, and the perforation motif in the empty poster
box. Each is a graphic with nothing read on top of it. `DECOR-WHY` fails an
exemption with no reason, so the list cannot quietly grow.

**Do not** use `--fr-ink-muted` for anything a customer must act on. It clears 4.5:1
on all three grounds, so it is legal, but it is the quietest text in the system and
a control set in it will be missed.

**Do not** use `--fr-rule` where `--fr-rule-quiet` belongs, or the reverse.
`--fr-rule` is a boundary that carries meaning and is held to 3:1 — the band
separator on the seat map, the stub perforation, the divider between dashboard
sections. `--fr-rule-quiet` is cosmetic and exempt; if removing a line would lose
information, it is not `--fr-rule-quiet`.

### 2.6 The seat palette — the one family with its own law

Four fills, two edges, two inks, and a set of rules that are not stylistic:

1. **Hue is never the carrier.** Around one man in twelve cannot separate the
   palette a seat map normally reaches for. State is carried by lightness and by a
   mark; hue is the third, redundant cue.
2. **The four fills sit on a lightness staircase** with a floor of **12 CIE L\*
   between adjacent states, in both themes.** `contrast.py`'s `GREYSCALE` check
   desaturates every fill to the neutral of identical relative luminance — what the
   colour becomes when hue information is unavailable — and measures the steps.
   `CONTRAST.md` prints the staircase.
3. **Every state carries a distinct non-colour mark** (`glyph:` in the annotation),
   and `GLYPH` fails if two states share one, because then colour would be the only
   difference between them.
4. **Every fill must also separate from the seat-map field**, either by 8 L\* or by
   a declared `edge:` token clearing the 3:1 non-text floor. `SEAT-FIELD` checks it.
   This is why `--fr-seat-available` has an edge and the other three do not: it is
   the state that sits closest to the field on purpose, so the resting map is quiet.

**Do not** add a fifth seat state. There are four (`FR-ADR-045`) and that is a
ruling, not a starting point.

**Do not** give a seat category a colour. Category is carried by band position and
the legend. Four states times three categories is twelve swatches nobody can tell
apart, and the categories are `ASSUMED` anyway (§4).

### 2.7 Elevation — `--fr-shadow-card`, `--fr-shadow-sheet`, `--fr-scrim`

**Do not** let a shadow be the only thing separating two surfaces. An alpha shadow
has no fixed foreground/background pair, so `contrast.py` cannot measure it and does
not try. Where a boundary carries meaning it also gets `--fr-rule` or
`--fr-control-edge`, which are measured.

### 2.8 Motion — `--fr-motion-fast`, `-base`, `-change`, `--fr-ease-out`

**Do not** use `--fr-motion-change` for anything except a seat that changed state
under the reader on a poll. It is long on purpose; anything else moving for that
long is an animation, and this system does not have animations.

**Do not** express reduced-motion support by overriding a duration token. A token
can be overridden back. The rule at the foot of `tokens.css` is global and
unopt-out-able, and a token redeclared inside that media query would also land in
whichever `@block` was last open and be miscounted as a theme-only token — which is
the drift `DARK-IDENTICAL` exists to catch.

---

## 3. Light and dark are both first-class

Light is the bare `:root`. Dark is declared **twice** — once under
`prefers-color-scheme: dark`, guarded with `:not([data-theme="light"])`, and once
under `[data-theme="dark"]` — so an explicit choice wins in both directions and a
reader who never touched a setting still gets a full theme.

`contrast.py` enforces two things about this arrangement that are easy to get wrong
and impossible to notice:

- `THEME-PARITY` — light and dark declare exactly the same palette token names. A
  token defined in one theme only is a component that renders with an inherited or
  missing colour in the other, and nobody sees it until they switch.
- `DARK-IDENTICAL` — the two dark blocks are value-for-value identical. The day they
  drift is the day one of them stops being tested.

**No ADR requires dark mode.** It is not in any frozen source. Building it is this
session's `[JUDGMENT CALL]`, taken because a cinema booking app is used in a dark
room and forcing a bright screen on someone about to sit in one is a real product
failure, and because the cost is bounded by the two checks above. It is reversible:
deleting both dark blocks leaves a complete light system.

One token is **the same in both themes on purpose**: `--fr-surface-notice`, the slab
that says no real payment is taken. It must not look like chrome in either theme.

---

## 4. Flags that must travel with this document

These are not disclaimers. Under `CONSTITUTION.md` Art VII they are part of the
finding.

**`ASSUMED` — never hardens into a constraint.**

- **Seat category names — Standard, Premium, Recliner** (`OPEN-SEAT-01`). The client
  said "you pick". Nothing in this system may make a fourth category expensive:
  bands are generated from category rows and there is no per-category colour token.
- **Hall sizes — 90/120/150/180/200/220** (`OPEN-SCALE-02`). The client said "pick
  random". The 220-on-375px design target is derived from a number nobody ruled. The
  seat map must not depend on that count being exactly 220.
- **Peak concurrency — 50 bookers** (`OPEN-SCALE-03`). Not a design-system concern
  directly, listed for completeness.

**`PROVISIONAL` — one message from the client reverses it.**

- **Four roles** (`SRC-003 C-1`). The manager surface in `COMPONENTS.md` §10 exists
  because of a reconciliation, not a plain answer.
- **One cinema, six screens** (`C-2`). Why the cinema filter is not rendered.
- **Sales close 15 minutes *after* the advertised start** (`OPEN-BOOK-03`). The
  closed-showtime state depends on it; the alternative reading is 15 minutes before.

**`OPEN` — escalate, never invent.**

- `OPEN-EMAILFAIL-01` / `FR-ADR-049`: what the customer is told when the receipt
  email definitively fails. **No copy for that screen exists in this design system
  and none may be written.**
- `OPEN-ATTRIB-01`: no real image, title or brand appears in any example here.
- `OPEN-SHOWCANCEL-01`: there is no withdraw-showtime surface.
- `OPEN-TLS-01`: deferred; no design-system consequence.

**Gaps, stated as gaps.**

- **There is no browser or version matrix in any frozen source.** `SRC-001 §6.1`
  says a website that works well on a phone is enough, and `§9.1` says customers
  have a smartphone. Nothing more exists. A matrix written here would be an
  assumption hardening into a specification, which is the failure this project
  already produced once with the seven-minute hold.
- **There is no numeric performance budget in any frozen source.** `SRC-001 §7.3`
  says pages should feel immediate and seat maps in particular must not lag. Any
  millisecond figure in this design system would be invented.
- **This design system has never been rendered in a browser.** No component here has
  been built, screenshotted or measured on a device. Every claim about how it looks
  is reasoned from computed colour figures and stated geometry — the contrast and
  lightness numbers are measured, the appearance is not observed.

---

## 5. Dependencies

> **Since `FR-ADR-074`:** `@fontsource/inter-tight` and `@fontsource/jetbrains-mono` (fonts, bundled by Vite, no CDN),
> and `three` with `@react-three/fiber`, `-drei` and `-postprocessing` for the seat page's 3D hall only.

**None added.** Plain CSS custom properties and CSS Modules, both of which ship with
the fixed stack (`SRC-002 §4.1`, `FR-ADR-044`). No component library, no icon
package, no font package, no charting library for the dashboard.

Two things this system would be better with, **neither of which may be added without
the client saying so** (`SRC-002 §13.1`) — both are asked for in the session report,
not taken:

1. **A self-hosted display typeface.** The system stacks work and the mono voice
   carries the character, but a real display face would sharpen the identity. It is
   a licence question and a bundle-weight question against the ~15 MB static
   frontend budget (`SRC-002 §5.4.1`).
2. **An icon set.** Every mark in this system is drawn in CSS — the seat glyphs are
   a border, a hatch, a bar and a tick, all achievable with `linear-gradient` and a
   pseudo-element. That is a deliberate constraint, not a shortcut, and it is
   holding.

Until either is answered, the answer is no, and the system is complete without them.

---

## 6. How to change this system safely

1. Edit `tokens.css`. It is the only place a value is defined.
2. Run `py "docs/05 B DesignSystem/contrast.py"`. It regenerates `CONTRAST.md` and
   tells you what broke.
3. If you added a token, name it in `COMPONENTS.md`, or `TOKEN-COVERAGE` fails. If
   you removed one, remove every mention, or it fails the other way.
4. If you added a colour, annotate it. `ANNOTATED` fails otherwise, and that is the
   point.
5. Run `py "docs/05 B DesignSystem/contrast.py" --selftest` if you changed the
   checker. Thirteen checks, thirteen planted violations, and every one has to fire.
   A check nobody has watched fail is decoration.

Never write a contrast figure by hand into any document, including this one.
`CONSTITUTION.md` Art VII.1.
