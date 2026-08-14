# A screen's seat layout is frozen once a showtime exists on it

```
ADR id ............ FR-ADR-022
Pack .............. PACK-DATA
Decision type ..... STRICTER_ADOPTION
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §9.3; SRC-001 §7.6; SRC-002 §8.1.5; SRC-003 OPEN-OPS-02
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §9.3` assumes seat layouts change rarely once a screen is configured. It is an assumption,
not a rule, and under Art II.7 it may not harden into one — but it does describe reality, and it means
the case this record covers is uncommon rather than impossible.

The hazard is concrete. A seat is deleted or renumbered while a booking references it. The oversell
guard is a unique constraint on `(showtime_id, seat_id)`, so the identity of a seat is load-bearing,
and `SRC-001 §7.6` requires the system to answer who booked *that seat* forever.

Nothing in the frozen sources says what happens. Left unruled, the admin CRUD in Phase 2 will simply
allow the edit, and the damage appears months later in the one query that has to answer for it.

## Decision

**Adding a seat to a screen is always allowed.** A new seat becomes available on future showtimes and
does not exist on past ones. Nothing references it, so nothing breaks.

**Removing a seat, renumbering it, or moving it to a different category is refused once any showtime
exists on that screen.** The API returns a 409 naming the constraint. This is not enforced only in the
interface — it is a check in the domain layer, because the admin CRUD is not the only caller.

**Changing a seat's grid coordinates is allowed**, because the coordinate is where the seat is drawn
and not what it is. A seat map redrawn slightly differently does not change what anyone bought.

**Retiring a seat that must come out of service** is done with an `is_active` flag on the seat row,
not a delete. An inactive seat is not offered on future showtimes, is not counted in the occupancy
denominator for future showtimes, and still resolves for every past booking that references it.

**The occupancy denominator for a showtime is the seat count at the time the showtime was created**,
stored on the showtime row as `seat_count_at_creation`. Computing it live from the current seat count
means retiring one seat silently changes last month's reported occupancy, which is a reporting figure
the client will act on.

**A screen with no showtimes is freely editable**, including deleting seats. That is the configuration
window and it is where the work belongs.

## Alternatives rejected

**Allow the edit and cascade to bookings.** Rejected outright under `FR-ADR-012` — no cascade may
reach a booking — and under `SRC-001 §7.6`.

**Version the layout: a new layout row per change, with showtimes pinned to a version.** This is the
correct answer for a system that re-fits halls regularly. Rejected here as disproportionate:
`SRC-001 §9.3` says layouts change rarely, one venue exists, and layout versioning adds a join to the
seat-map read path — the hottest query in the product. Recorded as the alternative to reach for if the
client ever asks to re-fit a hall mid-season.

**Allow renumbering because the label is cosmetic.** Rejected. The label is what the receipt says and
what the customer reads at the door. Renumbering seat `A-12` to `A-11` changes which seat a past
customer believes they bought.

**Allow a category change because it only affects price.** Rejected. It affects the price of *future*
showtimes correctly, and it would also change the price displayed against a past booking unless the
price is snapshotted. `FR-ADR-039` does snapshot it, which makes this safe in the money dimension —
but the seat map for a *live, already-selling* showtime would reprice mid-sale, which is the case
`FR-ADR-035` refuses. Freezing is the simpler rule and it is stricter.

## Source

`SRC-001 §9.3` (layouts change rarely — an assumption, cited as context, not as authority) ·
`§7.6` (auditability) · `SRC-002 §8.1.5` (the unique constraint makes seat identity load-bearing) ·
`SRC-003 OPEN-OPS-02` (nothing is deleted).

Adopting the restrictive option is a stricter adoption under Art III.10 and needs no signature.

## Consequences

The admin flow becomes: configure the screen fully, then create showtimes. Getting the layout wrong
after the first showtime exists means adding seats, or retiring them, but not editing them.

That is a real operational limitation and it will be felt the first time the client makes a typo in a
seat number. The Zone C and admin documentation must say so plainly rather than let it be discovered.

`seat_count_at_creation` on the showtime row is one integer that makes historical occupancy stable.
`FR-ADR-043` uses it as the denominator.

If the client asks for mid-season re-fitting, layout versioning is the rejected alternative to
reconsider, and it is a superseding record rather than an edit to this one.
