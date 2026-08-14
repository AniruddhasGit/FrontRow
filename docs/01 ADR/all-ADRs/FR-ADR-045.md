# The seat map: four states, a non-colour cue on each, polled every three seconds

```
ADR id ............ FR-ADR-045
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §5.2.1; SRC-001 §5.2.2; SRC-001 §5.2.3; SRC-001 §5.2.4; SRC-001 §5.2.6; SRC-002 §8.6.1; SRC-002 §8.6.2; SRC-003 OPEN-SCALE-02
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.2.2` requires available, held and sold seats to be **clearly distinguished**. `§5.2.3`
requires categories to be distinguishable too. `§5.2.1` requires the map to match the real layout.
`SRC-002 §8.6.1` fixes the refresh mechanism: polling every three seconds, "because it is simple and
works behind any load balancer".

Three seat states are named in the requirement and the sweep found a fourth that nobody wrote down:
**the seats this customer is holding right now**. Without it, a customer's own selection looks
identical to a stranger's — and the whole checkout flow depends on the customer knowing which seats
are theirs.

## Decision

**Four states, not three:**

| State | Meaning | Selectable |
|---|---|---|
| `available` | free | yes |
| `held_by_me` | this customer holds it, in this session | yes, to deselect |
| `held_by_other` | someone else holds it | no |
| `sold` | booked | no |

**`held_by_me` is computed client-side from the hold token, not sent by the server.** The cached seat
map is shared across every viewer of the showtime (`FR-ADR-030`) and carries objective state only;
per-viewer state is overlaid at render. A per-customer seat map would destroy the cache hit rate.

**Every state carries a non-colour cue as well as a colour.** A distinct shape or border treatment per
state, and an accessible name on each seat naming its state. Colour alone fails for a colour-blind
customer and fails again in bright sunlight on a phone, and `§5.2.2` says *clearly* distinguished.

**Category is shown by position and legend, not by a second colour dimension.** Seats are laid out in
category bands and the legend names each with its price. Encoding four states and three categories in
colour at once produces twelve swatches nobody can tell apart.

**Polling every three seconds**, per `§8.6.1`.

- **Polling pauses when the tab is hidden** and resumes with an immediate fetch on becoming visible.
  A backgrounded tab polling for hours is load on a `t3.micro` for a customer who is not looking.
  This does not weaken accuracy: nothing can be selected in a hidden tab, and the resume fetch is
  immediate.
- **Polling continues while a hold is live**, because the countdown and the seat map are the same
  screen.
- **No manual refresh control.** A three-second poll makes it decoration, and a refresh button
  implies the automatic refresh is unreliable.

**The code is structured so WebSockets can replace polling later** (`§8.6.2`): the seat map component
consumes a subscription-shaped interface, and the polling implementation sits behind it. A note in
`docs/07 Architecture/` explains what changes on the load balancer when the client makes that switch,
which is the second exercise `§8.6.2` asks for.

**Staleness is bounded and stated.** Up to about 13 seconds in the worst case — a 10-second cache TTL
plus a 3-second poll (`FR-ADR-030`). `SRC-001 §3.3` asks for accuracy "within a few seconds" and this
is at the edge of it.

**A stale map never causes an oversell.** A customer clicking a seat that has gone loses at the Redis
lock or the unique constraint, and is told immediately and clearly, which is what `§5.2.6` requires.
`FR-ADR-052` carries the message.

**The running total updates as seats are selected** (`§5.2.4`), computed from the per-seat prices in
the map payload using the same rounding rule as the server (`FR-ADR-038`) — the client must not
implement its own arithmetic and reach a different number.

**A closed showtime** — past the sales cut-off (`FR-ADR-042`) — renders its map with every seat
unselectable and a banner saying sales have closed. It is not hidden.

**A sold-out showtime** renders its map fully, with a banner. Showing an empty list would hide which
seats went.

**The 220-seat hall on a 375-pixel-wide screen is the design target** (`OPEN-SCALE-02`, `ASSUMED`).
The map scrolls horizontally inside its own container; the page body never does.

## Alternatives rejected

**Three states, treating the customer's own holds as generic holds.** Rejected. The customer cannot
tell which seats are theirs, which makes deselecting impossible.

**Send `held_by_me` from the server.** Rejected: it makes the seat map per-customer and the cache
useless.

**Colour-only state encoding.** Rejected under `§5.2.2` and on accessibility.

**WebSockets now.** Rejected by `§8.6.1`, which says start with polling. It is also the client's
second exercise and building it now takes the lesson.

**Keep polling in a hidden tab.** Rejected on load, above.

**Hide showtimes past the cut-off.** Rejected. A customer who saw a showtime and returns to find it
gone assumes a bug.

## Source

`SRC-001 §5.2.1` (matches the real layout) · `§5.2.2` (available, held, sold, clearly distinguished) ·
`§5.2.3` (categories) · `§5.2.4` (running total) · `§5.2.6` (tell them immediately) ·
`SRC-002 §8.6.1` (3-second polling) · `§8.6.2` (structured for WebSockets later) ·
`SRC-003 OPEN-SCALE-02` `ASSUMED` (hall sizes).

The fourth state, the non-colour cue, and the visibility-based poll pause are the build session's
under Art III.9.

## Consequences

The seat map endpoint is the highest-traffic route in the product and is the one worth measuring
first. Its payload at 220 seats sets the cache entry size and the polling bandwidth.

Polling from every viewer of a busy Friday showtime is the largest sustained load on one `t3.micro`.
It is unquantified and it should be measured in Phase 3 rather than reasoned about. *(reasoned, not
observed.)*

Keyboard and screen-reader operation of a 220-seat grid is a real design problem and it is not solved
by adding an accessible name to each seat. `FR-ADR-051` carries the target and says plainly what is
and is not in scope.

The subscription-shaped interface is a small indirection now that makes `§8.6.2`'s exercise a
contained change later.
