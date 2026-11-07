# COMPONENTS.md — the component specifications

Companion to `tokens.css` (the source of record) and `DESIGN-SYSTEM.md` (what each
token family is for). Every colour figure in this project lives in `CONTRAST.md`,
which is generated; no ratio is written by hand anywhere, including here.

**How to read a spec.** Each component gets: what it is for, its anatomy, the exact
tokens it uses, every state it can be in — including empty, loading, error and
partial — and what not to do with it. A token named here must exist in
`tokens.css`, and a token in `tokens.css` must be named here. `contrast.py`'s
`TOKEN-COVERAGE` check enforces both directions and both counts must be zero.

**Styling mechanism.** One `.module.css` per component, consuming the custom
properties from `tokens.css` (`FR-ADR-044`). No component library, no CSS-in-JS,
no utility framework, no preprocessor. A hex code inside a component file is a
defect.

**Copy rules** (`SRC-002 §2.2`, `FR-ADR-052`): say what happened, not how it felt.
Say what to do next where there is something to do. Never blame the customer for a
race they lost. No figures of speech.

---

## 0. Foundations every component inherits

### 0.1 The page frame

| Property | Token |
|---|---|
| Page background | `--fr-surface-base` |
| Body text | `--fr-ink` at `--fr-text-md` / `--fr-leading-body`, `--fr-font-body` |
| Content column | `max-width: var(--fr-page-max)`, centred |
| Prose column | `max-width: var(--fr-measure)` — never wider, regardless of the page |
| Page gutter | `--fr-space-4` on a phone, `--fr-space-6` above 40rem |

The page body never scrolls horizontally. Anything wider than the viewport scrolls
inside its own container (`FR-ADR-044`). The seat map is the only component that
regularly needs this.

### 0.2 Focus

Every interactive element, without exception:

```css
outline: var(--fr-stroke-bold) solid var(--fr-focus-ring);
outline-offset: 2px;
```

`outline-offset` is load-bearing, not cosmetic. It places the ring on the surface
*behind* the control rather than on the control's own fill, so one focus token can
be measured against the three page grounds — `--fr-surface-base`,
`--fr-surface-raised`, `--fr-surface-inset` — and never has to clear the brass of
`--fr-surface-accent` as well. A ring drawn inside a button would need a second
token and a second argument about which one applies.

Focus order follows visual order. The focus ring is never removed, never replaced
by a shadow, and never suppressed on mouse users.

### 0.3 Numbers are a separate voice

Every number a customer reads or repeats is set in `--fr-font-mono` with
`font-variant-numeric: tabular-nums`: showtimes, row letters, seat numbers, prices,
the countdown, the booking reference. Prose is `--fr-font-body`. This is the
system's one persistent typographic signature and it is functional — tabular
figures stop a countdown and a running total from jittering as they change.

### 0.4 Money

Rendered from integer paise at the last possible moment (`FR-ADR-036`), in
`--fr-font-mono`, with Indian digit grouping. The client never does its own
arithmetic: the running total uses the same per-seat half-up rule the server uses
(`FR-ADR-038`). Currency is INR and the minor-unit ratio is a one-way door.

### 0.5 Motion

| Token | Used for |
|---|---|
| `--fr-motion-fast` | a press, a hover, a checkbox |
| `--fr-motion-base` | a panel opening, a banner arriving |
| `--fr-motion-change` | one thing only: a seat that changed under the reader on a poll |
| `--fr-ease-out` | every transition in the system |

Under `prefers-reduced-motion: reduce` all animation collapses (see the rule at the
foot of `tokens.css`). The seat-change mark survives, as a static ring instead of a
pulse, because it carries information.

### 0.6 Elevation

| Token | Used for |
|---|---|
| `--fr-shadow-card` | a movie card, the price summary panel |
| `--fr-shadow-sheet` | the auth sheet, any overlay panel |
| `--fr-scrim` | the dimming layer behind an overlay |

Shadows are not measured for contrast — an alpha shadow has no fixed pair — so a
shadow may never be the only thing separating two surfaces. Where a boundary
carries meaning it gets `--fr-rule` or `--fr-control-edge`, both held to 3:1.

---

## 1. The seat map

**The hardest surface in this product.** Read this section before any other.

### 1.1 What it is

A grid of seats for one showtime in one hall. The customer taps seats to select
them, and a selection that has been accepted by the server is a *hold* that expires
in three minutes (`FR-ADR-027`). The map refreshes itself every three seconds
(`SRC-002 §8.6.1`); nothing the customer does triggers a refresh, and there is no
manual refresh control.

Halls run from 90 to 220 seats — six of them (`OPEN-SCALE-02`, which is **`ASSUMED`,
not ruled**: the client said "pick random", so no layout decision may depend on
those exact numbers). The design target is **the 220-seat hall on a 375-pixel-wide
phone** (`SRC-001 §6.1`).

### 1.2 Anatomy, top to bottom

```
+----------------------------------------------------+
|                  [ SCREEN ]                        |  screen bar + glow
|                                                    |
|  A  [ ][ ][ ]  [ ][ ][ ][ ][ ]  [ ][ ][ ]          |  row gutter + seats
|  B  [ ][ ][ ]  [ ][ ][ ][ ][ ]  [ ][ ][ ]          |
|     - - - - - - - - - - - - - - - - - - - -        |  band rule
|  C  [ ][ ][ ]  [ ][ ][ ][ ][ ]  [ ][ ][ ]          |
|                                                    |
|  <- the map scrolls sideways inside this box ->    |
+----------------------------------------------------+
|  Legend: what each of the four marks means         |
+----------------------------------------------------+
```

| Part | Tokens |
|---|---|
| Field (the box the map is drawn on) | `--fr-surface-inset` |
| Screen bar | `--fr-screen-bar`, `border-radius: var(--fr-radius-pill)` at the top edge, 4px tall, 60% of the map width, centred |
| Screen falloff | a linear gradient from `--fr-screen-glow` to transparent, 48px tall, directly below the bar |
| `SCREEN` label | `--fr-ink-muted`, `--fr-text-xs`, uppercase, `letter-spacing: var(--fr-track-caps)`, centred **inside the falloff, below the bar** — never on the bar, which is only 4px tall |
| Row gutter (the row letter, pinned left while the map scrolls) | width `--fr-seat-gutter`, `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted`, background `--fr-surface-inset` |
| Seat cell | `--fr-seat-size` square, `--fr-seat-gap` between, `border-radius: var(--fr-radius-sm)` |
| Gap between category bands | `--fr-seat-band-gap` |
| Band rule | 1px dashed `--fr-rule` across the band gap |
| Field padding | `--fr-space-4` |

**Aisles and gaps are the absence of a seat at a grid coordinate** (`FR-ADR-016`).
There is no placeholder element, no spacer seat and no "blocked" state. The grid is
drawn from `grid_row` / `grid_col`; the row letter and seat number the customer
reads are separate values and will not always agree with the coordinate.

### 1.3 Why the map scrolls

A 220-seat hall at `--fr-seat-size` plus `--fr-seat-gap` is wider than 375px. The
seat is not shrunk to make it fit: 24px is the WCAG 2.2 target-size minimum, and
shrinking it would fail a criterion to win an argument with a layout. Instead the
map scrolls horizontally inside its own container, the row gutter stays pinned, and
the page body never scrolls sideways.

**Vertically the map does not scroll inside its own box.** Rows grow the container
and the page scrolls normally. Two scroll axes in one element is how a customer
loses the screen bar and stops knowing which end of the hall they are looking at.

### 1.4 The four seat states

Exactly four (`FR-ADR-045`). No others exist — no blocked seat, no accessible-seat
marking, no couple seat, no used-ticket state (`OPEN-SEAT-02`, `OPEN-SEAT-03`,
`OPEN-SEAT-04`, `OPEN-TICKET-02`).

**Each state is told apart three times over: by fill lightness, by a mark, and by a
border. Colour is never the carrier.** Around one man in twelve cannot separate the
hue palette a seat map normally reaches for, so the hue is only ever the third,
redundant cue. `CONTRAST.md` proves the lightness separation by desaturating every
fill and measuring the steps.

| State | Fill token | Mark (`glyph:`) | What the mark looks like | Border | Seat number shown | Tappable |
|---|---|---|---|---|---|---|
| `available` | `--fr-seat-available` | `outline` | **no mark at all** — the cell is empty except for its number | 1px `--fr-seat-edge-available` | yes, `--fr-seat-ink` | **yes** |
| `sold` | `--fr-seat-sold` | `hatch` | **diagonal hatching**, 45°, edge to edge across the whole cell | none | yes, `--fr-seat-ink` | no |
| `held_by_other` | `--fr-seat-held-other` | `bar` | **one solid horizontal bar** across the middle of the cell, full width, 3px tall | none | yes, `--fr-seat-ink` | no |
| `held_by_me` | `--fr-seat-mine` | `check` | **a tick**, centred, filling most of the cell, drawn in `--fr-seat-ink-mine` | **2px** `--fr-seat-edge-mine` | no — the tick replaces it | **yes, to give the seat back** |

The mark colour follows the fill: the hatch on `sold` and the bar on `held_by_other`
are drawn in `--fr-seat-ink`, the same token as their seat numbers;
the tick on `held_by_me` is drawn in `--fr-seat-ink-mine`. Both ink tokens are
measured against every fill they are allowed to sit on — see `CONTRAST.md`.

**Telling `held_by_me` from `held_by_other` — the distinction that matters most.**
These two are never confusable, by four independent means at once:

1. **The mark.** `held_by_me` carries a **tick**. `held_by_other` carries a **flat
   horizontal bar**. A tick and a bar are different shapes at any size and in any
   colour, including no colour.
2. **The border.** `held_by_me` is the only state in the whole map with a 2px
   border. `held_by_other` has no border at all.
3. **The lightness.** In both themes they sit at opposite ends of the staircase:
   `held_by_me` is the fill furthest from the field — the loudest thing on the map —
   and `held_by_other` is two full steps closer to it. In light theme
   `held_by_me` is the darkest cell and in dark theme it is the brightest; either
   way it is the extreme.
4. **The behaviour.** `held_by_me` is tappable and tapping it gives the seat back.
   `held_by_other` does not respond to a tap.

Colour is the fifth cue and the least important: `held_by_me` is cyan — the colour
this system reserves for *your* things and the light off the screen — and
`held_by_other` is brass, the colour of the room, which is where someone else is
sitting.

**Order of the staircase, outward from the field, identical in both themes:**
`available` (nearest — the map at rest, defined only by its edge), then `sold` (the
settled mass, quiet because on a busy Friday most of the map is this), then
`held_by_other` (louder, because it is live and may come back), then `held_by_me`
(loudest, because it is yours). The direction flips between themes; the order never
does.

`held_by_me` is computed on the client from the hold token, not sent by the server
(`FR-ADR-045`).

### 1.5 Seat categories

Categories are shown by **position and legend, not by a second colour dimension**
(`FR-ADR-045`). Seats are laid out in contiguous bands; bands are separated by
`--fr-seat-band-gap` and a dashed `--fr-rule`; the legend names each band with its
price. Encoding four states and three categories in colour at once produces twelve
swatches nobody can tell apart, so the seat fill is owned entirely by state.

There are three categories — Standard, Premium and Recliner — and **that list is
`ASSUMED`, not ruled** (`OPEN-SEAT-01`: the client said "you pick"). Nothing in this
spec may make a fourth band expensive: the band is generated from the category rows,
never hard-coded, and there is no per-category colour token to add.

### 1.6 Accessible name

Every seat carries a name stating its identity, its category and its state
(`FR-ADR-051`), for example: `Row C seat 12, Premium, available`. For `held_by_me`
the name reads `Row C seat 12, Premium, held by you`. The seat number is present in
the name even when the tick has replaced it visually.

The map is **one tab stop**, not 220. Arrow keys move within the grid; Enter or
Space selects. A grid of 220 tab stops is not keyboard support, it is a keyboard
trap with extra steps.

### 1.7 A seat changing under the reader

The map polls every three seconds and pauses while the tab is hidden, fetching
immediately when it becomes visible again (`FR-ADR-045`). Worst-case staleness is
about thirteen seconds and is stated to nobody in the interface — it is a property
of the system, not a message.

**A seat that changes state between two polls must be legible, not a silent
repaint.** When a cell's state changes:

- the cell keeps a 2px `--fr-focus-ring` outline for `--fr-motion-change`;
- under `prefers-reduced-motion` that outline is static rather than pulsing, and it
  is held for the same duration;
- the fill transitions over `--fr-motion-base` with `--fr-ease-out`, so the eye can
  follow which cell moved;
- if the seat that changed was one of *the customer's own selected seats*, the mark
  is not enough. The error banner in §6 fires and names the seat.

### 1.8 Empty, loading, error and partial

| Situation | What renders |
|---|---|
| **Loading** | The field, the screen bar and the row gutters draw immediately at full size, with seat cells as `--fr-surface-inset` blocks at 60% opacity. The frame never resizes when the data lands. No spinner: the layout is already the answer. |
| **Empty** | Cannot happen. A showtime always has a hall and a hall always has seats. If the seat list is empty, that is an error, not an empty state, and §6 fires with `INTERNAL_ERROR`. |
| **Error (first load)** | The map is replaced by a message in `--fr-ink` on `--fr-surface-inset`: what failed and a control that retries. No partial grid. |
| **Error (a poll fails)** | **The last good map stays on screen.** A one-line strip appears at the top of the field in `--fr-ink-muted` on `--fr-surface-inset` saying the map is not updating, and polling keeps retrying. Blanking a map the customer is mid-selection on is worse than showing one that is a few seconds old. |
| **Sold out** | The full map renders, every seat `sold`, plus a banner above it (`FR-ADR-045`). Not an empty state — the customer wants to see that it is genuinely full. |
| **Sales closed** | The full map renders, every seat unselectable, plus a banner. Sales close 15 minutes **after** the advertised start (`OPEN-BOOK-03` — **`PROVISIONAL`**, the client's "yes 15 minutes" was ambiguous between before and after; one message reverses it). |
| **Hold expired** | Every `held_by_me` cell reverts to the state the next poll reports — usually `available`, sometimes `held_by_other` or `sold` if someone was faster. Each reverting cell fires the changed-seat mark in §1.7, so the customer watches the seats leave rather than finding them gone. The cells are **not** pre-emptively repainted at `0:00`: the client does not know what happened to them until the server says (`FR-ADR-047`). The countdown's own zero state (§7) is what says the hold ended. |
| **Partial** | The seat map and the price summary load independently. The map is usable before the price summary arrives; the primary action stays disabled until it does. |

### 1.9 What not to do

- Do not add a fifth state. Four is a ruling, not a starting point.
- Do not colour a seat by its category.
- Do not shrink `--fr-seat-size` to avoid the horizontal scroll.
- Do not add a manual refresh control.
- Do not distinguish two states by hue alone at any point, for any reason.

---

## 2. The seat legend

Sits directly below the map, always visible, never collapsed behind a control.

| Part | Tokens |
|---|---|
| Container | `--fr-surface-raised`, `--fr-radius-md`, padding `--fr-space-3` |
| Swatch | `--fr-seat-size` square, drawn with the exact fill, mark and border of the state it names |
| Label | `--fr-text-sm`, `--fr-ink` |
| Category rows | band name in `--fr-ink`, price in `--fr-font-mono` `--fr-ink-strong` |
| Divider between states and categories | `--fr-rule-quiet` |

The legend is the only place the four marks are named in words. Each swatch is the
real component at the real size — not a simplified circle — because a legend that
does not look like the map is a second thing to learn.

**States:** never empty and never loading; the four states are constants. The
category rows are loading-dependent and show a `--fr-surface-inset` block until the
prices arrive.

---

## 3. The movie card

Used in the browse listing (`SRC-001 §5.1.1`).

| Part | Tokens |
|---|---|
| Container | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-card`, padding `--fr-space-4` |
| Poster box | `aspect-ratio: var(--fr-poster-ratio)`, `--fr-radius-md`, background `--fr-surface-inset` |
| Title | `--fr-font-display`, `--fr-text-lg`, `--fr-weight-bold`, `--fr-track-tight`, `--fr-ink-strong`, `--fr-leading-tight` |
| Synopsis | `--fr-text-sm`, `--fr-ink-muted`, `--fr-leading-body`, clamped to three lines |
| Metadata row — runtime, certification, language, genre | `--fr-text-xs`, `--fr-ink-muted`; runtime in `--fr-font-mono` |
| Certification chip | `--fr-text-xs`, `--fr-ink`, 1px `--fr-control-edge`, `--fr-radius-sm`, padding `--fr-space-1` |
| Gap between elements | `--fr-space-3` |

**The poster is 2:3 and the box reserves that space before the image arrives**, so a
listing does not reflow as posters load. Posters are uploaded by the admin and
served by redirect to a presigned URL (`FR-ADR-061`).

| Situation | What renders |
|---|---|
| **Loading** | The poster box and three text blocks draw as `--fr-surface-inset` at the final dimensions. |
| **Missing poster** | The poster box draws the perforation motif in `--fr-poster-empty-mark` — a column of dots down both long edges, like a strip of film — with the movie title centred in `--fr-ink-muted` at `--fr-text-sm`. No icon, no "image not found", no broken-image glyph. A movie **cannot be published without a poster** (`FR-ADR-021`), so in the customer-facing listing this state means the image failed to load, not that none exists. In the admin's draft list it means the poster has not been uploaded yet. |
| **Error** | A card whose data failed does not render. The listing renders the cards it has. |
| **Empty listing** | One line of `--fr-ink` at `--fr-text-md` on `--fr-surface-base` saying nothing is showing for the chosen filters, and a control that clears them. Not an illustration. |

Demo content is obviously demo content: placeholder titles like `DEMO MOVIE 01`, and
**no image from anywhere** — the attribution question is open (`OPEN-ATTRIB-01`).

---

## 4. The showtime picker

Lists every showtime for a chosen movie and date (`SRC-001 §5.1.4`), in the cinema's
local time, Asia/Kolkata (`FR-ADR-018`).

| Part | Tokens |
|---|---|
| Date strip | horizontal, scrolls inside its own container; each day is a button `--fr-tap-min` tall |
| Selected day | `--fr-surface-accent` fill, `--fr-ink-on-accent` text |
| Unselected day | `--fr-surface-raised`, 1px `--fr-control-edge`, `--fr-ink` |
| Showtime button | `--fr-font-mono`, `--fr-text-md`, min height `--fr-tap-min`, `--fr-radius-md`, 1px `--fr-control-edge`, `--fr-surface-raised` |
| Hall name under the time | `--fr-text-xs`, `--fr-ink-muted` |
| Base price | `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted` |
| Closed showtime | `--fr-surface-inset` fill, `--fr-ink-muted` text, not focusable, with the word `Closed` in `--fr-text-xs` |
| Grid gap | `--fr-space-2` |

Filters are date, language and format — always rendered. **The cinema filter is not
rendered while one cinema exists** (`FR-ADR-046`); it appears on its own when a
second one does. A dropdown with one option is a control that cannot be used.

| Situation | What renders |
|---|---|
| **Loading** | The date strip is real (dates are known without a fetch); the showtime grid draws four `--fr-surface-inset` blocks at button size. |
| **Empty** | "No showtimes on this date." in `--fr-ink`, with the next date that has one offered as a button. An empty screen is an invitation to act. |
| **Error** | The message and a retry control, in place of the grid. The date strip stays usable. |
| **Partial** | Times render as they arrive; prices may lag, and a time with no price yet shows a `--fr-surface-inset` block where the price goes rather than a zero. |

---

## 5. The price summary

Sits under the seat map on a phone, beside it above 40rem. It carries the running
total and the primary action.

| Part | Tokens |
|---|---|
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-card`, padding `--fr-space-4` |
| Held-seat count, above the lines | `--fr-screen-ink`, `--fr-text-sm`, `--fr-weight-medium` — e.g. `3 seats held by you`. Screen-light, because these are your things. |
| Seat line — label and price | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink` |
| Category note per line | `--fr-text-xs`, `--fr-ink-muted` |
| **Perforation** above the total | a dashed 1px `--fr-rule`, `--fr-space-3` clear above and below |
| Total label | `--fr-text-sm`, `--fr-ink-muted`, uppercase, `--fr-track-caps` |
| Total figure | `--fr-font-mono`, `--fr-text-xl`, `--fr-weight-bold`, `--fr-ink-strong` |
| Primary action | `--fr-surface-accent` fill, `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min`, `--fr-weight-bold` |
| Secondary action | transparent fill, 1px `--fr-control-edge`, `--fr-accent-ink` |
| Seat cap note | `--fr-text-xs`, `--fr-ink-muted` |

The dashed rule above the total is the **stub perforation** — the system's one
borrowed physical device, used in exactly two places: here, and around the booking
reference. It is not decoration: it marks the tear between what you chose and what
you owe.

There is **no tax line, no discount field and no booking fee** (`FR-ADR-040`). The
price shown is the price paid. Do not leave space for one.

**Primary action copy depends on who is reading:**

| Reader | Copy |
|---|---|
| Guest | `Sign in to hold these seats` (`FR-ADR-046`) |
| Customer, no seats chosen | `Choose seats` — disabled |
| Customer, seats chosen | `Hold these seats` |
| Customer, hold live | `Pay ₹…` |

| Situation | What renders |
|---|---|
| **Empty** (no seats chosen) | The panel stays at full height with the total at `₹0.00` and the seat cap stated: "Up to 10 seats." A panel that appears and disappears makes the page jump under a thumb. |
| **Loading** | Prices as `--fr-surface-inset` blocks; the action disabled. |
| **Error** | The action is disabled and §6 carries the message. The summary itself never carries an error. |
| **Partial** | If some seat prices are known and some are not, the total is not shown at all — a partial total is a wrong number. The action stays disabled. |

---

## 6. The error banner

The one component the seat-lost case uses (`SRC-001 §5.2.6`). It is also the
general-purpose failure surface.

| Part | Tokens |
|---|---|
| Container | `--fr-surface-danger`, `--fr-radius-md`, padding `--fr-space-3`, 1px `--fr-control-edge` |
| Leading rule | 3px `--fr-danger-ink` down the leading edge |
| Message | `--fr-ink-on-danger`, `--fr-text-sm`, `--fr-leading-body` |
| Seat names inside the message | `--fr-font-mono`, `--fr-weight-bold` |
| Action inside the banner | `--fr-accent-ink`, underlined |
| Request id line (5xx only) | `--fr-text-xs`, `--fr-ink-muted`, `--fr-font-mono` |
| Arrival | slides in over `--fr-motion-base` with `--fr-ease-out` |

The banner appears directly above the seat map, inside the scroll container's
sticky header area, so it is visible without scrolling. It is announced through a
live region — an error that is only red has not been reported (`FR-ADR-051`).

**It never blames the customer for a race they lost.** For the seat-lost case:

> `C12` and `C13` were taken by another customer. Your other seats are still held.

Not an apology, not an exclamation, not "someone beat you to it". The seats that
went are named, and the remaining selection stays exactly as it was
(`FR-ADR-026`, `FR-ADR-052`).

**The interface branches on the error `code`, never on the message text**
(`FR-ADR-052`). Five different failures share HTTP 409 and each needs a different
screen:

| Code | What the banner does |
|---|---|
| `SEAT_UNAVAILABLE` | Names the lost seats from `details`, marks them **`held_by_other`** on the map, keeps the rest of the selection. **CORRECTED 2026-08-22 - this row said `sold` and that was wrong.** A seat lost to another customer's *hold* is not sold; it becomes `sold` only when that customer's booking commits, and it returns to `available` if their hold expires. `P-HLD-07` owns this and says so in terms. Marking it `sold` here told the customer a seat was gone for good when it may be free again in three minutes. |
| `HOLD_EXPIRED` | Returns the customer to the seat map with the previous selection re-applied and the map refreshed (`FR-ADR-047`). |
| `SEAT_LIMIT_EXCEEDED` | States the cap of ten and how many are currently selected. |
| `SALES_CLOSED` | Disables the map and states that sales for this showtime have closed. |
| `RATE_LIMITED` | States that too many attempts were made and when to try again. |
| `DEPENDENCY_UNAVAILABLE` | States that seat holds are unavailable right now and that browsing still works. Never silently degrades. |
| `INTERNAL_ERROR` | The message plus the request id: "If you need help, quote `a1b2c3d4`." Request id is shown on 5xx only. |

| Situation | What renders |
|---|---|
| **Empty** | Nothing. The banner is absent, not collapsed to zero height. |
| **Several at once** | One banner. The newest message replaces the previous one; errors do not stack into a wall. |
| **Dismiss** | Only errors with nothing left to do are dismissible. `SEAT_UNAVAILABLE` is not — it clears when the customer changes the selection. |

---

## 7. The hold countdown

Three minutes is short, and the customer has to feel it (`FR-ADR-027`,
`FR-ADR-047`).

| Part | Tokens |
|---|---|
| Digits | `--fr-font-mono`, `--fr-text-xl`, `--fr-weight-bold`, `--fr-countdown-fill`, `font-variant-numeric: tabular-nums` |
| Label | `--fr-text-xs`, `--fr-ink-muted`, uppercase, `--fr-track-caps` |
| Track | `--fr-surface-inset`, height 4px, `--fr-radius-pill` |
| Bar | `--fr-countdown-fill`, shrinking left to right |
| Bar, last 60 seconds | `--fr-countdown-urgent` |
| Digits, last 60 seconds | `--fr-countdown-urgent`, and the warning line appears |
| Warning line | `--fr-text-sm`, `--fr-ink`, naming what happens at zero |

Format is `m:ss`. It runs from a server-issued absolute `expires_at`, never from a
duration counted on the client, so a device with a wrong clock cannot invent time
(`FR-ADR-047`). It shows on **both** the seat map and the checkout screen and is
never hidden behind a tooltip.

**One warning threshold, at 60 seconds.** Not 60/30/10. Repeated escalation is
noise, and a customer who is told three times is being nagged rather than informed.
At the threshold three things change together: the bar colour, the digit colour, and
a line of text naming the consequence. The change is announced once through a live
region.

The bar length is the primary carrier — it works with the colour removed, which
matters because the only difference between the normal and urgent states is a hue.

| Situation | What renders |
|---|---|
| **No hold** | The component is absent. |
| **Live** | Digits, bar and label. |
| **Last 60s** | As above plus the warning line. |
| **Zero** | The countdown stops at `0:00`, the payment action is disabled, and the component states that the hold has expired. It does **not** claim the seats are free — the server owns that, and the customer is returned to the map with their selection re-applied. |
| **Clock skew** | If `expires_at` is already past on arrival, the zero state renders immediately. No negative numbers, ever. |

The component takes the current instant as an input. It never reads the wall clock
itself, which is why it needs no time-dependent test.

---

## 8. The checkout panel

| Part | Tokens |
|---|---|
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-sheet`, padding `--fr-space-5` |
| Heading | `--fr-font-display`, `--fr-text-xl`, `--fr-weight-black`, `--fr-track-tight`, `--fr-ink-strong` |
| Booking lines | as the price summary, §5 |
| Pay action | `--fr-surface-accent`, `--fr-ink-on-accent`, min height `--fr-tap-min` |
| Countdown | §7, repeated here |

### 8.1 The simulated-payment notice — a design element, not a footnote

A full-width slab at the top of the panel, above the heading, before anything else
is read:

| Part | Tokens |
|---|---|
| Slab | `--fr-surface-notice`, `--fr-radius-md`, padding `--fr-space-4` |
| Text | `--fr-ink-on-notice`, `--fr-text-md`, `--fr-weight-medium` |

> No real payment is taken. This is a demonstration system. Nothing is charged and
> no card details are collected.

`--fr-surface-notice` is **the same colour in both themes**, on purpose. It is the
one element in the system that must not look like chrome — a reader who has learned
the dark theme should still find this slab unfamiliar. It is persistent, never a
tooltip, never dismissible, and it is never smaller than body size (`FR-ADR-041`).

**There is no card number field, no CVV field, no expiry field, and no placeholder
for one** (`FR-ADR-041`). The fake button is a button. A simulated payment that
looks real to a customer is the worst thing this screen can do.

| Situation | What renders |
|---|---|
| **Loading** (payment in flight) | The pay action shows a busy state and is disabled; the countdown keeps running; nothing else moves. The panel does not blank. |
| **Failure** | §6 with `PAYMENT_FAILED`. The hold survives if it has not expired, and the customer may try again. |
| **Expired mid-payment** | §6 with `HOLD_EXPIRED`; the pay action is disabled; the customer returns to the map. |
| **Retry / refresh / double-tap** | The same `Idempotency-Key` returns the original booking. Never a second booking, never a second charge (`FR-ADR-020`). |

---

## 9. The booking reference

The customer's only proof of purchase and their only way into the hall. It is read
aloud and typed by hand at a door, by a human, from a phone screen at arm's length
(`FR-ADR-048`).

| Part | Tokens |
|---|---|
| Reference | `--fr-font-mono`, `--fr-text-2xl`, `--fr-weight-bold`, `--fr-ink-strong`, `letter-spacing: var(--fr-track-ref)` |
| Perforation above and below | dashed 1px `--fr-rule`, `--fr-space-4` clear |
| Label | `--fr-text-xs`, `--fr-ink-muted`, uppercase, `--fr-track-caps` |
| Container | `--fr-surface-inset`, `--fr-radius-md`, padding `--fr-space-4` |
| Copy control | `--fr-accent-ink`, `--fr-text-sm` |

**On the confirmation page the facts and the reference are one paper ticket stub** (the Ticket wireframe,
`FR-ADR-074`): `--fr-surface-ticket` paper, `--fr-ink-on-ticket` ink, labels and the copied note in
`--fr-ink-on-ticket-muted`, the tear line between the facts and the reference a dashed `--fr-rule-ticket`. The
copy control and the focus ring on the stub use `--fr-ink-on-ticket`, since the accent and the screen-light inks are
made for the room, not for paper. Like the payment notice (§8.1) the stub is the same colour in both themes.

Format is `FR-XXXX-XXXX` (`FR-ADR-015`). The prefix and hyphens are presentation;
the eight characters are the value. The alphabet already excludes `0`/`O` and
`1`/`I`/`l`, and `--fr-track-ref` is the wide tracking that makes the remaining
characters separable when someone is reading them out one at a time. The two groups
of four are what makes it speakable — nobody reads eight characters in one breath.

**It is not a QR code.** There is no scanner, no validation endpoint and no
used-ticket state (`OPEN-TICKET-01`, `OPEN-TICKET-02`). Entry is a human reading
this and checking it.

The reference appears in three places, all reading the same booking row: the
confirmation screen, the customer's bookings list, and the email.

**Confirmation screen copy** (`FR-ADR-048`), which says what has actually happened:

> Your booking is confirmed. Your reference is `FR-ABCD-EFGH`. A receipt is on its
> way to `<address>`.

Not "we have sent you an email". The screen shows the reference **immediately, and
independently of whether the email was sent**, because the email is what can fail.

| Situation | What renders |
|---|---|
| **Confirmed** | As above. This page is durable and reachable again from the bookings list, not a one-time interstitial. |
| **Receipt not yet sent** | Nothing changes. The reference is already the proof. |
| **Receipt definitively failed** | **Not specified, and nothing may be written here.** `FR-ADR-049` is `NOT_DECIDED` and reserved to the client (`OPEN-EMAILFAIL-01`). A plausible sentence written into this screen would close a question nobody answered. |

---

## 10. The dashboard panel

The manager and admin reporting surface (`OPEN-REPORT-01`, `FR-ADR-043`). Phase 8.

| Part | Tokens |
|---|---|
| Panel | `--fr-surface-raised`, `--fr-radius-lg`, padding `--fr-space-5`, `--fr-shadow-card` |
| Period tabs — day, week, month | `--fr-text-sm`; selected uses `--fr-surface-accent` / `--fr-ink-on-accent` |
| Figure | `--fr-font-mono`, `--fr-text-2xl`, `--fr-weight-black`, `--fr-ink-strong` |
| Figure label | `--fr-text-xs`, `--fr-ink-muted`, uppercase, `--fr-track-caps` |
| Occupancy bar track | `--fr-surface-inset`, `--fr-radius-pill` |
| Occupancy bar fill | `--fr-countdown-fill` |
| Row divider | `--fr-rule-quiet` |
| Section divider | `--fr-rule` |

Periods are whole calendar boundaries in Asia/Kolkata; the week is Monday to Sunday.

**A manager is read-only** (`OPEN-OPS-03`, and the four-role split is `C-1`,
**`PROVISIONAL`**). This panel contains no control that writes anything. A write
control on a manager surface is a defect, not a feature. **There is no export
control anywhere** (`OPEN-REPORT-02`).

| Situation | What renders |
|---|---|
| **Empty — a manager with no screens assigned** | The panel renders with the period tabs and a line stating that no screens are assigned to this account and who to ask. **This is the correct state, not an error**, and it must not render as one. |
| **Empty — a period with no bookings** | The figures render as `₹0.00` and `0%`. A zero is a fact; blanking it would hide the fact. |
| **Loading** | Figure-sized `--fr-surface-inset` blocks, tabs live. |
| **Error** | The message replaces the figures. The tabs stay usable so another period can be tried. |
| **Partial** | Never. A dashboard shows a complete period or it shows nothing — a half-summed figure is a wrong number a manager will act on. |

---

## 11. Forms — auth, admin movie authoring

| Part | Tokens |
|---|---|
| Field | `--fr-surface-inset`, 1px `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min`, padding `--fr-space-3` |
| Field text | `--fr-ink`, `--fr-text-md` |
| Label | `--fr-text-sm`, `--fr-weight-medium`, `--fr-ink`, always visible, never a placeholder |
| Help text | `--fr-text-xs`, `--fr-ink-muted` |
| Field in error | border becomes 2px `--fr-danger-ink` |
| Field error message | `--fr-text-xs`, `--fr-danger-ink`, associated with the field and announced |
| Tab bar (sign in / register) | one row, `--fr-rule` under the unselected, `--fr-surface-accent` bar under the selected |

Registration and sign-in are **one screen with two tabs**, not two destinations
(`FR-ADR-046`). Every input has a programmatically associated label. An error is
announced, not only coloured (`FR-ADR-051`).

Password help states the rules before they are broken: a 12-character minimum, no
required mixture of character classes, and a 72-byte maximum with its own clear
message (`FR-ADR-050`).

The admin's poster upload states the size limit and the accepted formats **before**
the file is chosen, not after it is rejected (`FR-ADR-061`), and the upload box uses
`--fr-poster-ratio` so the admin sees the shape the poster will be cropped to.

| Situation | What renders |
|---|---|
| **Loading** | The submit control is busy and disabled; fields stay readable and stay filled. |
| **Error** | Field-level errors on their fields; a form-level failure uses §6. |
| **Empty** | Not applicable — a form is its own empty state. |

---

## 11b. The stage curtain (CR-005)

A transition piece that covers a hall view for under two seconds. It carries no state and never takes a click.

| Part | Tokens |
|---|---|
| Velvet pleats | a repeating gradient from `--fr-velvet-deep` through `--fr-velvet` to `--fr-velvet-lit` and back |
| Valance trim | 3px `--fr-velvet-gold` under the pelmet |

| Situation | What renders |
|---|---|
| **Reduced motion** | Every move is instant. |

---

## 12. Token index

Every token in `tokens.css`, and where in this document it is used. This table is
what makes the coverage check meaningful in the direction that is easy to forget.

| Family | Tokens | Used by |
|---|---|---|
| Spacing | `--fr-space-1` `--fr-space-2` `--fr-space-3` `--fr-space-4` `--fr-space-5` `--fr-space-6` `--fr-space-7` | §0.1, §1.2, §2, §3, §4, §5, §8, §9, §10, §11 |
| Radius | `--fr-radius-sm` `--fr-radius-md` `--fr-radius-lg` `--fr-radius-pill` | §1.2, §2, §3, §5, §7, §8, §9, §10, §11 |
| Stroke | `--fr-stroke-hair` `--fr-stroke-bold` | §0.2, §1.4 |
| Type — family | `--fr-font-display` `--fr-font-body` `--fr-font-mono` | §0.1, §0.3, §3, §8, §9 |
| Type — size | `--fr-text-xs` `--fr-text-sm` `--fr-text-md` `--fr-text-lg` `--fr-text-xl` `--fr-text-2xl` | §0.1, §1.2, §2, §3, §5, §6, §7, §9, §10, §11 |
| Type — leading | `--fr-leading-tight` `--fr-leading-snug` `--fr-leading-body` | §0.1, §3, §6 |
| Type — weight | `--fr-weight-regular` `--fr-weight-medium` `--fr-weight-bold` `--fr-weight-black` | §3, §5, §6, §7, §8, §9, §10, §11 |
| Type — tracking | `--fr-track-tight` `--fr-track-caps` `--fr-track-ref` | §1.2, §3, §5, §7, §9, §10 |
| Seat metrics | `--fr-seat-size` `--fr-seat-gap` `--fr-seat-band-gap` `--fr-seat-gutter` | §1.2, §1.3, §1.5, §2 |
| Layout | `--fr-tap-min` `--fr-page-max` `--fr-measure` | §0.1, §4, §5, §8, §11 |
| Poster | `--fr-poster-ratio` | §3, §11 |
| Motion | `--fr-motion-fast` `--fr-motion-base` `--fr-motion-change` `--fr-ease-out` | §0.5, §1.7, §6 |
| Grounds | `--fr-surface-base` `--fr-surface-raised` `--fr-surface-inset` `--fr-surface-accent` `--fr-surface-danger` `--fr-surface-notice` `--fr-surface-ticket` | §0.1, §1.2, §2, §3, §4, §5, §6, §8, §9, §10, §11 |
| Seat fills | `--fr-seat-available` `--fr-seat-sold` `--fr-seat-held-other` `--fr-seat-mine` | §1.4 |
| Seat edges | `--fr-seat-edge-available` `--fr-seat-edge-mine` | §1.4 |
| Seat ink | `--fr-seat-ink` `--fr-seat-ink-mine` | §1.4 |
| Ink | `--fr-ink-strong` `--fr-ink` `--fr-ink-muted` | §0.1, §1.2, §3, §5, §9, §10, §11 |
| Ink on a fill | `--fr-ink-on-accent` `--fr-ink-on-danger` `--fr-ink-on-notice` `--fr-ink-on-ticket` `--fr-ink-on-ticket-muted` | §4, §5, §6, §8, §9, §10 |
| Accent and status ink | `--fr-accent-ink` `--fr-danger-ink` `--fr-screen-ink` | §5, §6, §9, §11 |
| Boundaries | `--fr-focus-ring` `--fr-rule` `--fr-control-edge` `--fr-rule-ticket` | §0.2, §1.2, §1.7, §3, §4, §5, §6, §9, §10, §11 |
| Seat-map graphics | `--fr-screen-bar` | §1.2 |
| Countdown | `--fr-countdown-fill` `--fr-countdown-urgent` | §7, §10 |
| Exempt | `--fr-screen-glow` `--fr-rule-quiet` `--fr-poster-empty-mark` `--fr-velvet-deep` `--fr-velvet` `--fr-velvet-lit` `--fr-velvet-gold` | §1.2, §2, §3, §10, §11b |
| Elevation | `--fr-shadow-card` `--fr-shadow-sheet` `--fr-scrim` | §0.6, §3, §5, §8, §10 |

---

## 13. What is deliberately not specified here

- **The copy shown when the receipt email definitively fails.** Reserved and
  undecided (`FR-ADR-049`, `OPEN-EMAILFAIL-01`). No screen, no wording, no
  placeholder sentence.
- **Any withdraw-showtime surface.** `OPEN-SHOWCANCEL-01` is open. No control
  exists in v1.
- **A browser or version matrix.** No frozen source names one. Inventing it here
  would harden an assumption into a specification, which is the exact failure this
  project already produced once.
- **Any real image, title or brand.** `OPEN-ATTRIB-01` is open; demo content is
  obviously demo content.
- **A screen-reader-optimised alternative to the seat map**, accessible-seat
  marking, and any published conformance claim — all explicitly out of scope
  (`FR-ADR-051`).
