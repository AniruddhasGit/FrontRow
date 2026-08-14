# Every instant is stored as `timestamptz` in UTC and rendered in Asia/Kolkata

```
ADR id ............ FR-ADR-018
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-LOCALE-01; SRC-003 OPEN-BOOK-03; SRC-001 §5.1.4; SRC-001 §7.6
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-LOCALE-01` ruled the market as India and the timezone as Asia/Kolkata. It did not say
how an instant is stored, and no frozen source does.

A cinema is a physical place and a showtime is a wall-clock fact about that place: the 19:30 show
starts at 19:30 in the hall, not at an instant that happens to be 19:30 somewhere. But the sales
cut-off, the hold expiry and the audit trail are all instants, and comparing an instant to a
wall-clock time without an explicit zone is the defect this record exists to prevent.

`GOTCHAS.md` records the trap: a showtime stored without a zone, or evaluated in UTC on the server,
is wrong by the offset at both ends, and "sales close N minutes from the start" then closes at the
wrong moment.

## Decision

**Every timestamp column is `timestamptz`. Every stored value is UTC. Every rendered value is
converted to Asia/Kolkata at the boundary.** There is no `timestamp without time zone` anywhere in
the schema.

**A showtime carries `starts_at`, a `timestamptz`.** It is the advertised start, as an instant. The
admin enters a local date and time; the API converts it to an instant using the cinema's zone at the
point of entry, and stores the instant.

**The cinema row carries its IANA zone name**, `Asia/Kolkata`. Not because a second zone exists today
— there is one cinema (`FR-ADR-010`) — but because "the zone" otherwise becomes a global constant, and
a global constant is the thing that is wrong the moment a second venue appears in a different state.
It costs one column.

**`ends_at` is stored, not derived.** Derived from a movie's runtime it would silently change when an
admin corrects the runtime, and it would ignore trailers and turnaround. It is set at showtime
creation and it is what the receipt shows.

**The sales cut-off is derived, never stored.** It is `starts_at` plus the configured offset, computed
at evaluation time, so changing the offset in configuration takes effect immediately and does not
require rewriting rows. `FR-ADR-042` carries the offset and its provisional direction.

**Nothing reads the server's clock to decide "today".** "Today's showtimes" is a date in
Asia/Kolkata, computed from the injected clock and the cinema's zone, never from the container's
local time. A container in AWS is on UTC and would roll the date over at 05:30 local.

**Time is injected.** Domain code takes a clock; it never calls the system clock directly. A test that
reads the wall clock is a defect (Art IX.5), not a nuisance — a gate that goes red at midnight with no
code change has told you about your test, not your system.

**India observes no daylight saving and sits at a fixed +05:30.** That is true today and is recorded
as the reason no offset-transition handling is written. It is a fact about the zone, not a licence to
hardcode +05:30 — the zone name is stored and the conversion goes through the zone database, so a rule
change does not silently break the product.

## Alternatives rejected

**Store a naive local wall-clock time for showtimes, with the zone implied.** Rejected. Every
comparison against an instant — the cut-off, the hold expiry, the audit trail — then needs an implicit
conversion, and an implicit conversion is one someone forgets.

**Store both a local wall-clock time and an instant.** Rejected as two sources of truth for one fact.
They drift the first time one is corrected without the other.

**Derive `ends_at` from the movie's runtime.** Rejected above: an admin fixing a runtime typo would
retroactively change the advertised end time of shows that have already sold tickets.

**Put the zone in application configuration rather than on the cinema row.** Rejected as the weaker
option. It works exactly until there are two cinemas, and it makes the zone invisible in the data —
an operator reading the database cannot tell what 14:00 UTC means.

## Source

`SRC-003 OPEN-LOCALE-01` (Asia/Kolkata) · `OPEN-BOOK-03` (the cut-off is relative to the advertised
start) · `SRC-001 §5.1.4` (showtimes for a chosen movie and date) · `§7.6` (auditability).

The storage decision is the build session's under Art III.9.

## Consequences

Every date-bounded query — the customer's date filter, the manager's day/week/month dashboard —
converts to Asia/Kolkata before taking a date boundary. `FR-ADR-043` carries those boundaries.

A late-night show that starts at 23:45 Asia/Kolkata is on 2026-08-14 in local terms and 18:15 UTC on
the same day. The two agree here, but they would not for a show after 05:30 UTC-equivalent, which is
why the boundary is always taken in the cinema's zone.

The seed script generates instants, not local strings, so seeded data is correct under any server
zone.

`created_at` and `updated_at` are `timestamptz` and default to `now()` at the database, which is
always UTC. The injected clock governs domain decisions; the database clock governs row metadata.
Those are deliberately different and the difference is why a test can control expiry without having to
control the database.
