# The movie entity: authored by hand, published deliberately, shown inside a display window

```
ADR id ............ FR-ADR-021
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-ROLE-01; SRC-003 OPEN-TMDB-01; SRC-003 OPEN-TMDB-03; SRC-001 §5.1.1; SRC-001 §5.1.3; SRC-001 §E E-5; SRC-002 §E E-2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-ROLE-01` describes what the admin creates: "the admin can add movie names and pictures
and other stuff which the people can view on the website. and also have a dealine of how long this
will stay". `OPEN-TMDB-01` confirms it and removes the import.

Three things need deciding that the ruling does not settle. Which fields exist. Whether "published"
and "inside its display window" are the same thing or two different gates. And whether the movie has
a natural key, given there is no external id to upsert on any more (`SRC-002 §E E-2`).

## Decision

**Fields**, from `SRC-001 §5.1.1` which survives unchanged: `title`, `synopsis`, `runtime_minutes`,
`certification`, `language`, `genre`, plus a `poster_object_key` pointing at S3.

- `language` and `certification` are **lookup tables**, not free text and not PostgreSQL enums.
  `SRC-001 §5.1.3` makes language a customer-facing filter, and a filter over free text produces
  "Hindi", "hindi" and "HIN" as three languages. A table means a new certification costs an insert.
- `genre` is **many-to-many** through a join table. A film is routinely two genres and a single column
  forces either a lie or a delimiter.
- `poster_object_key` is the S3 key, not a URL. The URL is built at render time from configuration, so
  moving buckets does not rewrite every row. Nullable — a movie can be drafted before its poster is
  uploaded — but a movie **cannot be published with a null poster**, which is a publish-time check,
  not a column constraint.

**Publication and the display window are two separate gates, and both must pass.**

- `published_at` — nullable `timestamptz`. Null means draft. The admin sets it deliberately.
  `OPEN-TMDB-03` puts that action on the admin alone.
- `display_from` and `display_until` — the "deadline of how long this will stay" the client asked for.

A movie is visible to a customer only when `published_at` is not null **and** the current instant in
the cinema's zone falls inside the window. They are separate because they answer different questions:
publication is "is this finished", the window is "is this the period we are showing it".
Overloading one column with both meanings means unpublishing a movie to change its dates.

**Endpoint inclusivity is stated so it can be tested:** `display_from` is inclusive,
`display_until` is exclusive. A show at exactly `display_until` is out.

**No natural key. No unique constraint on title.** Two films can share a title, and a re-release is a
legitimate second row. Uniqueness is the primary key alone.

**Nothing carried over from the import.** No external id, no `pending` state, no upsert key, no sync
timestamp, no "source" column. `FR-ADR-007` may add a provenance field if `OPEN-ATTRIB-01` closes
that way, and it is not added speculatively.

**No "upcoming" flag** (`SRC-001 §E E-5`). Customers see what is currently showing.

**Default listing order is newest first**, by `published_at` descending, overridden by the customer's
chosen sort (`OPEN-TMDB-01`).

## Alternatives rejected

**One `is_visible` boolean instead of publication plus a window.** Rejected. It cannot express "ready,
but showing from Friday", which is exactly what the client described.

**Derive visibility from whether the movie has any showtimes in range.** Rejected. It removes the
admin's control, and a movie with a mistakenly created showtime would publish itself.

**A unique constraint on title.** Rejected above — re-releases and coincidental duplicates are both
real.

**Free-text language and certification.** Rejected because language is a filter facet.

**Delete a movie that was created by mistake.** Rejected under `FR-ADR-012`. It is unpublished, which
removes it from every customer surface while keeping any showtimes and bookings resolvable.

## Source

`SRC-003 OPEN-ROLE-01` (title, pictures, a deadline for how long it stays) · `OPEN-TMDB-01` (hand
entry, newest first) · `OPEN-TMDB-03` (the admin publishes) · `SRC-001 §5.1.1` (the fields) ·
`§5.1.3` (the filters) · `SRC-001 §E E-5` · `SRC-002 §E E-2`.

Field types, the two-gate model and the inclusivity rule are the build session's under Art III.9.

## Consequences

The customer-facing movie query filters on `published_at IS NOT NULL` and on the window, in the
cinema's zone. That predicate appears in more than one place and belongs in one function, because a
missed clause there shows an unpublished movie to customers.

**A movie whose window ends while its showtimes still have bookings is a real state.** Those customers
must still see their booking and their receipt. The window governs the browse surface, not the
booking record. `FR-ADR-046`'s pack decides what the customer sees.

Poster upload happens before publication, which means the upload path has to work on a draft movie.
`FR-ADR-061` carries it.

Seeded movies are `DEMO MOVIE 01` style placeholders with no poster and no publication, per
`FR-ADR-067`. They exist to give showtimes something to point at.
