# One cinema with six screens, and the `cinema` entity stays in the schema anyway

```
ADR id ............ FR-ADR-010
Pack .............. PACK-DATA
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED_PROVISIONAL
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 C-2; SRC-003 OPEN-SCOPE-01; SRC-003 OPEN-SCALE-01; SRC-001 §1.1; SRC-001 §5.1.3; SRC-001 §6.6
Constitution ...... frontrow-constitution@0.1.0
```

> ## ⚠ PROVISIONAL — one message from the client reverses this
> `SRC-003 C-2` records the reconciliation. Read it before relying on this record.

## Context

`SRC-001 §1.1` says "We operate cinemas" — plural — and `§5.1.3` asks customers to filter listings by
cinema, which only makes sense with more than one.

`SRC-003 OPEN-SCOPE-01` says "the theatre has 6 cinema halls" — singular theatre, six halls — and
`OPEN-SCALE-01`, asked directly how many cinemas and screens, answered "i answered this above".

So the client's own scale answer describes one venue, and their own requirement document describes
several. The scope answer is later and more specific, but the requirement document is not withdrawn.

## Decision

**One cinema at launch, with six screens.**

**The `cinema` entity stays in the schema.** A `cinema` table holding exactly one row costs almost
nothing — one insert, one foreign key on `screen`, no query complexity worth naming. Removing it and
adding it back later is a migration on live booking data.

**Manager scoping attaches to the screen, not to the cinema.** That matches the ruling's own words —
"different managers for different cinema hall" — and it is the narrower scope, so it satisfies
`SRC-001 §4.4`'s per-cinema requirement automatically while also satisfying the ruling. See
`FR-ADR-011`.

`SRC-001 §6.6` is the binding reason this is not simplified away: the client may ask for a second
venue later, and no design decision may make that impossible.

The customer-facing cinema filter (`SRC-001 §5.1.3`) is a **user-visible** question, not a data
question, and is decided in `FR-ADR-046`'s pack rather than here — the entity existing does not
oblige the interface to render a one-option dropdown.

## Alternatives rejected

**Drop the `cinema` entity and hang screens off nothing.** Rejected under `SRC-001 §6.6`. It saves one
table and one column today and costs a migration against live bookings the moment a second venue
appears. It also silently deletes `SRC-001 §4.4`'s per-cinema manager scoping, which was never
withdrawn.

**Model several cinemas and seed more than one.** Rejected under Art VII.3 and `SRC-003 OPEN-SEED-01`.
Inventing a second venue is inventing product content the client will see and may treat as real.

**Attach manager scoping to the cinema rather than the screen.** Rejected because with one cinema it
scopes nothing — every manager would see everything, and the access-control test in Art VI.5 would
pass vacuously while protecting nothing. Screen-level scoping is the stricter option and under
Art III.10 adopting it needs no signature.

**Keep `cinema` but make the foreign key nullable "for simplicity".** Rejected. A nullable owner
produces screens belonging to nobody, and the manager-scope query then has a branch nobody tests.

## Source

`SRC-003 C-2` (the reconciliation) · `OPEN-SCOPE-01` ("the theatre has 6 cinema halls") ·
`OPEN-SCALE-01` · `SRC-001 §1.1` (plural, superseded in effect) · `SRC-001 §5.1.3` (the filter) ·
`SRC-001 §6.6` (excluded is not blocked).

## Consequences

Every screen carries a non-null `cinema_id`. Every showtime reaches a cinema through its screen. No
query needs to special-case "the one cinema", so nothing has to be unpicked if a second appears.

Hall sizes are `ASSUMED`, not ruled — the client said "pick random" on `OPEN-SCALE-02`. Six halls of
90, 120, 150, 180, 200 and 220 seats is the build session's choice and **never hardens into a
constraint**. It must be flagged as assumed every time a design leans on it, particularly the seat-map
payload size at 220 seats.

Twelve manager accounts across six halls follows from this shape plus `FR-ADR-009`.
