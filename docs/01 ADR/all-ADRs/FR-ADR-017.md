# Primary keys are `bigint` identity columns, and no internal id appears in a public URL

```
ADR id ............ FR-ADR-017
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §4.3; SRC-002 §5.2.2; SRC-002 §8.1.5; SRC-003 OPEN-OPS-02
Constitution ...... frontrow-constitution@0.1.0
```

## Context

No frozen source names a primary key type. It has to be chosen before the first migration, it is
effectively permanent once bookings exist, and it interacts with two things this project cares about:
the unique constraint on `(showtime_id, seat_id)` that prevents overselling, and the fact that nothing
is ever deleted, so every table only grows.

The second question is separate and is often conflated with the first: whether an internal key may
appear in a URL a customer can see and change.

## Decision

**Primary keys are `bigint` identity columns** — `GENERATED ALWAYS AS IDENTITY` — on every table.

- 8 bytes, sequential, and index-friendly. On a `db.t3.micro` with 20 GB of storage and forever
  retention, narrow and locally-ordered index entries matter more than they would on a larger
  instance.
- Sequential insertion keeps the B-tree appending to the right rather than writing across the whole
  index, which is what random UUIDs do to write throughput and index size.
- The oversell guard is a unique index on `(showtime_id, seat_id)`. Two 8-byte integers make a 16-byte
  key; two UUIDs make a 32-byte key on the single most contended index in the system.

**No internal id appears in any URL, response body or interface element a customer can see.**

Two identifiers carry the public surface, and both already exist for other reasons:

- **A booking is addressed by its reference** (`FR-ADR-015`) — random, from the 30-character
  alphabet, unique-constrained. Never by its primary key.
- **Movies, showtimes, screens and seats are addressed by their internal id**, because they are not
  private. Knowing that showtime 41 exists discloses nothing; the seat map for it is already public to
  guests (`FR-ADR-014`).

The rule is therefore about **what is private**, not about ids in general. The private objects in this
system are bookings, payments, users and audit rows, and none of those is ever addressed by a
sequential key from outside.

**Users are addressed by nothing public.** A customer reads their own bookings through their session,
never through a user id in a path. An admin surface may use internal ids, because it sits behind the
admin router.

## Alternatives rejected

**UUIDv4 primary keys everywhere.** Rejected on write and index cost. Random UUIDs scatter index
inserts, and this project's hottest index is also its correctness guard. The usual argument for
UUIDs — safe to expose — is answered here by not exposing keys at all.

**UUIDv7 or ULID.** These fix the ordering problem and would be a reasonable choice. Rejected as
16 bytes against 8 for no benefit this project can use: there is no distributed id generation, no
merge of separately-generated datasets, and no client-side id assignment. The cost is real and the
benefit is hypothetical.

**`integer` rather than `bigint`.** Rejected. Nothing is ever deleted (`FR-ADR-012`), so every table
only grows, and 2.1 billion is a ceiling that exists for no reason. Widening a primary key later is a
migration on live data across every foreign key referencing it.

**A separate public UUID column on every table alongside the bigint key.** Rejected as two identifiers
per row where one suffices. It is the right pattern when every entity is private; here only bookings
are, and bookings already have a public identifier that a human can read aloud.

**Natural keys — a movie keyed by title, a seat keyed by its label.** Rejected. Titles are not unique,
labels are only unique within a screen, and a natural key that ever changes rewrites every referencing
row.

## Source

`SRC-002 §4.3` (PostgreSQL) · `§5.2.2` (`db.t3.micro`, 20 GB) · `§8.1.5` (the unique constraint) ·
`SRC-003 OPEN-OPS-02` (nothing is deleted, so tables only grow).

No frozen clause rules this. It is a technical decision under Art III.9 and the client may reverse it.

## Consequences

Showtime and seat ids are enumerable by anyone. That is acceptable because the seat map is public.
It does mean the seat-map endpoint is scrapeable, which is a rate-limiting concern rather than an
authorisation one (`FR-ADR-058`).

Because booking references are the public handle, the lookup-by-reference path needs an index on the
reference column and must be rate limited. Sequential ids would have made that endpoint trivially
enumerable; random references make it a guessing problem against a 30⁸ space.

`GENERATED ALWAYS AS IDENTITY` rather than `serial` means the sequence is owned by the column and
cannot be written to by accident. That is the stricter option and under Art III.10 needs no signature.
