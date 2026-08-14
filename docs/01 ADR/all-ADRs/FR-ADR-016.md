# Seat identity, seat categories, and how a screen's layout is represented

```
ADR id ............ FR-ADR-016
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §5.2.1; SRC-001 §5.2.3; SRC-003 OPEN-SEAT-01; SRC-003 OPEN-SEAT-02; SRC-003 OPEN-SEAT-03; SRC-003 OPEN-SEAT-04; SRC-003 OPEN-SCALE-02
Constitution ...... frontrow-constitution@0.1.0
```

> **Part of this record is `ASSUMED`, not `RULED`.** The client said "you pick" on seat categories
> (`OPEN-SEAT-01`) and "pick random" on hall sizes (`OPEN-SCALE-02`). Those choices are the build
> session's and **never harden into constraints**. They are flagged as assumed wherever they matter.

## Context

`SRC-001 §5.2.1` requires a seat map matching the real layout of the screen, and `§5.2.3` requires
seat categories to be distinguishable because they are priced differently. Neither says how a layout
is stored.

Four seat questions were ruled and three of them are removals: no accessible-seat marking
(`OPEN-SEAT-02`), no paired seats (`OPEN-SEAT-03`), no gap rule (`OPEN-SEAT-04`). Those removals are
what keep this simple — in particular `OPEN-SEAT-03`, because a paired seat would turn the lock from
per-seat into per-group, which is a materially harder concurrency problem.

## Decision

**A `seat` row is a real, physical, individually sellable seat.** One row per seat per screen. Seats
are created when the screen is configured and are not created per showtime.

**Identity: `(screen_id, row_label, seat_number)`, unique.** Row label is a short string (`A`, `B`,
…, and `AA` onward if a hall ever needs it); seat number is an integer within the row. Decomposed
rather than a single `A-12` string, because the seat map is drawn from it, sorted by it, and
`SRC-001 §5.2.1` requires it to match the real layout. A single label forces string parsing every
time the map is rendered.

**Layout: explicit grid coordinates on the seat row** — `grid_row` and `grid_col`. The seat map is
drawn by placing each seat at its coordinate. **Aisles, gaps and non-seat space are represented by the
absence of a seat at a coordinate, not by a placeholder row.** There is no "empty seat" entity,
because an empty space cannot be sold, held, priced or audited, and giving it a row means every query
over seats has to exclude it.

Grid coordinates are kept separate from `row_label` and `seat_number` on purpose. The label is what
the customer reads and what appears on the receipt; the coordinate is where it is drawn. In a hall
with a gap in the middle of a row those two are different numbers, and collapsing them produces a
seat map that does not match the room.

**Categories: a `seat_category` lookup table, not a database enum.** Each seat carries a non-null
`seat_category_id`. Seeded with three rows — **Standard, Premium, Recliner** — which is `ASSUMED`.
A table rather than an enum because a fourth category then costs an insert instead of a migration,
and because the category carries a price uplift (`FR-ADR-037`) which an enum cannot hold.

**Not modelled, on rulings:** no accessible-seat flag, no pair or group linkage between seats, no
adjacency or gap rule. Any available seat may be selected.

**Hall sizes**, `ASSUMED`: six screens of 90, 120, 150, 180, 200 and 220 seats. A spread rather than
one number, so the seat map is exercised at more than one size. The 220-seat hall on a 375-pixel-wide
phone is the design target.

## Alternatives rejected

**A single `label` string per seat, such as `A-12`.** Rejected. Sorting `A-2` after `A-12` is the
default and wrong, and every render becomes a parse.

**Storing the layout as a JSON blob on the screen row.** Rejected. The unique constraint that prevents
overselling is on `(showtime_id, seat_id)` and needs a seat to be a row with an id. A blob also cannot
carry a per-seat category foreign key or be joined for the seat map query.

**A PostgreSQL enum for seat categories.** Rejected. Adding a value to a PostgreSQL enum is a
migration, the values cannot carry the price uplift, and `OPEN-SEAT-01` was answered "you pick" —
which is exactly the kind of answer that gets revised.

**Materialising a seat row per showtime.** Rejected. Six halls at up to 220 seats across a month of
showtimes is a large table that duplicates unchanging data, and it moves the oversell guard onto rows
the application creates rather than rows that already exist. Occupancy is a `booking_seat` row against
the permanent seat.

**Modelling accessible seats anyway, since a real cinema needs them.** Rejected under Art VII.3. The
client ruled no, explicitly, on the grounds that this is a demonstration project. `SRC-003 OPEN-SEAT-02`
already records that a real cinema in India operates under accessibility obligations and that this
would need revisiting before anyone booked a real seat. It is a known deferral, not an oversight.

## Source

`SRC-001 §5.2.1` (the map matches the real layout) · `§5.2.3` (categories are priced differently) ·
`SRC-003 OPEN-SEAT-01` `ASSUMED` · `OPEN-SEAT-02`, `OPEN-SEAT-03`, `OPEN-SEAT-04` (all removals) ·
`OPEN-SCALE-02` `ASSUMED`.

## Consequences

Because there are no paired seats, **the Redis lock stays per seat** — the simplest form of the
hardest part of this system. `FR-ADR-025` depends on that.

The seat-map payload at 220 seats sets the cache entry size and the polling bandwidth. At a
3-second poll (`SRC-002 §8.6.1`) that payload is fetched by every viewer of a busy showtime twenty
times a minute, which is the single largest read load in the product.

A seat's category can change if the client re-fits a hall, and that changes the price of future
showtimes. It must not change what a past customer paid — `FR-ADR-039` snapshots the price onto the
booked seat for that reason.

Editing a screen's layout after showtimes exist is a separate hazard and is decided in `FR-ADR-022`.
