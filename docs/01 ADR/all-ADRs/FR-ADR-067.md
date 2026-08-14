# Seed data is structural only, with placeholder movies that could never be mistaken for real content

```
ADR id ............ FR-ADR-067
Pack .............. PACK-OPS
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-SEED-01; SRC-002 §6.1.6; SRC-003 OPEN-SCALE-02; SRC-003 OPEN-SCOPE-01; SRC-003 OPEN-ATTRIB-01; SRC-002 §9.1; SRC-003 OPEN-PAY-01
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §6.1.6` requires seed scripts with sample cinemas, screens and showtimes. Those are invented
product content — cinema names, screen layouts, film titles, showtimes — and Art VII.3 forbids the
build session inventing content the client will see and may treat as real. It was raised as
`OPEN-SEED-01`.

The client answered: "nope do not generate anything just generate a few fake records which we will
ingest to showcase the bookings. I will bring poster and movie titles and we'll fill them with dummy
data for demo. dummy data for about a month would be nice."

That draws a clear line. Structure is the build session's to generate. **Content is the client's to
supply.**

## Decision

**`scripts/seed.py` generates structural data only.**

**What it creates:**

- **One cinema**, named obviously as a placeholder — `DEMO CINEMA` — with `Asia/Kolkata` as its zone
  (`FR-ADR-010`, `FR-ADR-018`).
- **Six screens** of 90, 120, 150, 180, 200 and 220 seats, with full seat layouts and category
  assignments. **`ASSUMED`, from `OPEN-SCALE-02` where the client said "pick random"** — never a
  constraint (`FR-ADR-016`).
- **Three seat categories** — Standard, Premium, Recliner — with their uplift basis points. Also
  `ASSUMED` (`OPEN-SEAT-01`).
- **Movie rows as obvious placeholders**: `DEMO MOVIE 01` through `DEMO MOVIE 08`. **No poster, no
  synopsis text pretending to be a synopsis.** Runtime, certification and language are plainly
  synthetic.
- **Showtimes spanning about one month**, across all six screens, at plausible times — which is what
  the client asked for and what gives the day, week and month dashboard views real shapes to test
  against (`FR-ADR-043`).
- **Users**: one admin, twelve managers assigned two per screen (`FR-ADR-011`), and enough customers
  to run the concurrency proof — **fifty distinct authenticated customers** are required by
  `FR-ADR-034`.
- **Bookings and payments** across that month, at varying occupancy, so the dashboard shows a range
  rather than one number. Payments in `captured` state (`FR-ADR-041`).

**What it never creates:**

- **No invented movie title.** `DEMO MOVIE 01` is not a title anyone could mistake for a film.
- **No poster image**, and no placeholder image sourced from anywhere. `OPEN-ATTRIB-01` is open, and
  a seeded image from an unknown source is exactly the licence problem that row is about
  (`FR-ADR-007`).
- **No invented cinema or brand name.** `DEMO CINEMA`, not a plausible chain.
- **No realistic personal data.** Seeded users have addresses at a domain reserved for the purpose and
  names that read as synthetic. No real-looking Indian names attached to a booking history.
- **No card-shaped data of any kind** (`OPEN-PAY-01`, Art V.7). No number, no last-four, no expiry, no
  placeholder for one. The rule holds in the seed script specifically because a fixture becomes a
  habit.

**Every seeded row is identifiable as seeded.** The `DEMO` prefix on names and a reserved email domain
mean an operator looking at a database can tell demonstration data from real data at a glance.

**The script is idempotent.** Running it twice does not duplicate. It is keyed on the placeholder
identifiers and skips what exists, so it can be re-run after a partial failure.

**A separate, explicitly named command wipes and reseeds.** Not the default, because the default is
what someone runs by accident.

**Seeded time is relative to an injected clock**, not to hardcoded dates. A script that seeds
2026-08-14 is useless in a month. It seeds a month centred on the current date so the dashboard always
has past and future.

**Whether it may be run against the deployed environment: yes, once, deliberately, and it is the
client's action.** The client asked for demonstration data to showcase bookings, which means the
deployed environment needs it. The build session cannot run it there — `FR-ADR-003` gives it no write
access to anything in AWS — so it is a documented step in `docs/30 Deployment/` that the client
performs. **The wipe command is never run there**, and the specification says so in those words.

## Alternatives rejected

**Generate realistic movie titles and posters so the demonstration looks good.** Rejected by
`OPEN-SEED-01` and by Art VII.3. It is also the exact behaviour that would create an attribution
problem under `OPEN-ATTRIB-01`.

**Use a fake-data library for names and emails.** Rejected. It produces *realistic* personal data,
which is the opposite of what is wanted — the point is that seeded data is obviously seeded.

**Seed fixed calendar dates.** Rejected: it expires.

**Make the seed script destructive by default.** Rejected. It will eventually be run against something
that matters.

**Skip seeding bookings and only seed structure.** Rejected. The client asked for bookings
specifically ("to showcase the bookings"), and the dashboard cannot be built or reviewed against an
empty database.

**Seed a second cinema to exercise multi-cinema code paths.** Rejected under `FR-ADR-010` and
Art VII.3 — inventing a venue the client does not have.

## Source

`SRC-003 OPEN-SEED-01` (the ruling, verbatim above) · `SRC-002 §6.1.6` (seed scripts are Zone A) ·
`OPEN-SCALE-02` and `OPEN-SEAT-01` (both `ASSUMED`) · `OPEN-SCOPE-01` (one theatre, six halls, two
managers each) · `OPEN-ATTRIB-01` (why no images are seeded) ·
`SRC-002 §9.1` (fifty customers for the stress script) · `SRC-003 OPEN-PAY-01` (no card data).

The idempotency, the relative-time seeding and the `DEMO` naming convention are the build session's
under Art III.9.

## Consequences

**The demonstration looks obviously like a demonstration**, and that is the ruled outcome. If the
client wants it to look real, they supply titles and posters, which is what they said they would do.

The seed script is a Phase 2 deliverable and it is a **dependency of Phase 4**, because the
concurrency proof needs fifty authenticated customers before it can run (`FR-ADR-034`).

Seeded bookings need seeded payments in `captured` state, or the dashboard's revenue figure reads zero
(`FR-ADR-043`). That coupling is easy to miss and is worth a test asserting the seeded dashboard is
non-empty.

**Nothing is ever deleted** (`FR-ADR-012`), so seeded rows in the deployed environment are permanent
unless the client removes them by hand. Seeding there is a one-way action in practice and the
specification must say so before they run it.
