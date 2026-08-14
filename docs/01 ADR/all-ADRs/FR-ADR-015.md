# The booking reference: a 30-character alphabet with no `0`/`O` and no `1`/`I`/`l`

```
ADR id ............ FR-ADR-015
Pack .............. PACK-DATA
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-TICKET-01; SRC-003 OPEN-TICKET-02; SRC-001 §E E-9; SRC-002 §E E-5
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.3.3` asked for "a scannable ticket" and `SRC-002 §8.5.1` had the worker generate a QR
code. Both are withdrawn. The client ruled: "the receipt sent on email which has a unique ID. that
will be shown at the entrance."

That changes what the identifier is *for*. A QR code is read by a machine and its content can be
anything. This reference is **read aloud by a customer and typed by a person at a door**, and
`SRC-003 OPEN-TICKET-01` says so explicitly: it must avoid characters people confuse, naming
`0`/`O` and `1`/`I`/`l`.

The format itself was left to the PRD. Leaving it there would mean the data model is written before
the identifier it must hold a unique constraint on is defined, so it is decided here.

## Decision

**Alphabet — 30 characters:**

```
23456789ABCDEFGHJKMNPQRSTVWXYZ
```

Digits `2`–`9` and the uppercase letters, less five: `I`, `L`, `O` for the confusions the client
named, and `U` because a randomly generated string that spells something offensive is a real problem
in a customer-facing identifier. Excluding `U` removes the most common way that happens in a
consonant-heavy alphabet.

**Format — `FR-XXXX-XXXX`.** A fixed `FR-` prefix, then eight characters from the alphabet in two
groups of four, separated by a hyphen.

- The prefix makes the string recognisable as a FrontRow reference when a customer reads it out.
- Grouping in fours is what people can hold in working memory while reading from a screen to a
  keyboard.
- The hyphens and the prefix are presentation. **Storage is the eight characters, uppercase.**

**Generation.** Eight characters drawn from a cryptographically secure random source — not from a
sequence, a timestamp or a hash of the booking. The column carries a unique constraint. On a
collision the insert fails and generation retries, bounded at five attempts, after which the request
returns an error rather than looping.

**Input handling.** Comparison is case-insensitive and ignores hyphens and whitespace. A person
typing `fr abcd efgh` finds the same booking. **Nothing is silently corrected** — an `O` typed for a
zero is not mapped to anything, because `0` is not in the alphabet and the lookup simply fails. A
system that guesses what the customer meant can let the wrong person into the hall.

## Alternatives rejected

**A UUID.** Rejected outright. Thirty-six characters including hyphens, with `0`/`O` and `1`/`l`
confusions throughout, read aloud at a door. It is the correct answer for a machine-read identifier
and the wrong one for this.

**A sequential number, or the booking's primary key.** Rejected. It is guessable, so anyone could read
another customer's booking by incrementing, and it discloses how many bookings the business has
taken.

**Base32 / Crockford's alphabet as published.** Rejected because Crockford includes `0` and `1` and
maps `O` to `0` and `I`/`L` to `1` on input. The client's ruling excludes the characters entirely
rather than aliasing them, and aliasing is what allows a mistyped reference to resolve to a real
booking that is not the customer's.

**A shorter reference, say six characters.** Rejected. At 30⁶ ≈ 7.3 × 10⁸ the space is small enough
that guessing becomes viable against an endpoint that looks up by reference, and this reference is the
only thing that gets a person into the hall.

**Deriving it from the booking id with a checksum.** Rejected. Any deterministic derivation from a
sequential key is still enumerable once someone works out the function.

## Source

`SRC-003 OPEN-TICKET-01` (a unique id on the emailed receipt; avoid confusable characters) ·
`OPEN-TICKET-02` (manual human check, no scanner) · `SRC-001 §E E-9` · `SRC-002 §E E-5`.

The alphabet size, length and grouping are the build session's, under Art III.9. The client may
reverse any of them.

## Consequences

The space is 30⁸ ≈ 6.56 × 10¹¹. Against the volume this project will ever hold, collisions are
effectively theoretical, and the unique constraint catches the theoretical case rather than trusting
the arithmetic.

**Nothing prevents the same reference being presented twice at the door.** There is no used-ticket
state and no validation endpoint (`SRC-003 OPEN-TICKET-02`). That is accepted for a demonstration
project and is a real hole in a live one. It is recorded as an accepted weakness, not solved here.

Any endpoint that looks up a booking by reference is an enumeration target and must be both
authenticated and rate limited. `FR-ADR-058` carries the rate limiting.

The reference is shown on the confirmation screen as well as emailed (`FR-ADR-048`), because SES
failing after payment would otherwise leave the customer with nothing.
