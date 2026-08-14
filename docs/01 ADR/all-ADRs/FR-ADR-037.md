# Pricing: a base price per showtime plus a per-category percentage uplift, uniform across every hall

```
ADR id ............ FR-ADR-037
Pack .............. PACK-MONEY
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED_PROVISIONAL
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PRICE-01; SRC-003 OPEN-SEAT-01; SRC-001 §5.2.3; SRC-001 §5.5.1; SRC-001 §10.15
Constitution ...... frontrow-constitution@0.1.0
```

> ## ⚠ One part of this is PROVISIONAL
> That the base price is set **per showtime** rather than globally is a build-session reading of the
> client's words, recorded in `SRC-003 OPEN-PRICE-01` and reversible by one message. The two-part
> model itself is ruled.

## Context

`SRC-001 §10.15` asked whether price varies by seat category, time of day, day of week or movie —
noting that the answer decides whether pricing is a column or a table. It was raised as
`OPEN-PRICE-01`, classed reserved: money.

The client answered: *"the admin will set the ticket price and more the premium ticket the more% fix
price increase across all halls or any movie show."*

Two things are clear and one is not. The uplift is a percentage, and it is uniform across halls and
shows. What is not stated is at which level "the ticket price" is set.

## Decision

**A two-part model.**

**1. A base price per showtime, in paise.** `showtime.base_price_paise`, a non-null `bigint`, set by
the admin when the showtime is created (`SRC-001 §5.5.1`).

**This is the PROVISIONAL part.** "The admin will set the ticket price" does not say which level. Per
showtime is the narrower and more useful reading — a single global price would make an evening
blockbuster cost the same as a weekday matinee, which is not how any cinema prices. It is reversible:
collapsing to a global price is a configuration change plus a backfill, not a redesign.

**2. A fixed percentage uplift per seat category**, on the `seat_category` row, applied **uniformly
across every hall and every show**. That uniformity is what *"across all halls or any movie show"*
rules out: there is no per-hall and no per-movie category pricing.

**The uplift is stored as an integer number of basis points**, `uplift_basis_points`, where one basis
point is 0.01%. 12.5% is `1250`. Integer basis points rather than a decimal percentage keeps the
entire money path in integer arithmetic — a decimal percentage reintroduces a non-integer type into
the one calculation this project cares most about getting exactly right.

**Standard is 0 basis points.** It is not a special case in code; it is a row whose uplift happens to
be zero, and the same formula runs for it.

**The formula and its rounding are in `FR-ADR-038`**, with a worked example, because
`CONSTITUTION.md` Art IX.4 requires every rule that computes a number to state the rule, its inputs
and a worked example with the expected answer.

**Category uplifts are global and mutable, and changing one does not reprice anything already sold.**
`FR-ADR-039` snapshots the price onto the booked seat, and `FR-ADR-035` fixes the price at hold
acquisition. Between them, an uplift change affects only holds taken after it.

**No other pricing dimension exists.** No time-of-day pricing, no day-of-week pricing, no per-movie
pricing. Those were the other options `§10.15` offered and the answer named none of them. Adding one
is a new decision and it is reserved.

## Alternatives rejected

**A price table keyed by (showtime, category) with an absolute amount per row.** Rejected. It can
express per-hall and per-movie category pricing, which the ruling explicitly rules out, and it makes
"the same uplift everywhere" a data invariant nothing enforces — six halls would drift within a month.

**A global base price with per-showtime overrides.** Rejected as two ways to express one thing. The
override becomes the norm and the global value becomes a default nobody notices is wrong.

**Store the uplift as a `numeric` percentage.** Rejected above: it puts a non-integer type on the money
path.

**Store the computed per-seat price on the seat or category row.** Rejected. It duplicates a derived
value across every showtime and goes stale the moment a base price changes.

**Add time-of-day pricing because a real cinema has it.** Rejected under Art VII.3. The client was
asked and named none of it.

## Source

`SRC-003 OPEN-PRICE-01` (the ruling and the recorded reading) · `OPEN-SEAT-01` (three categories,
`ASSUMED`) · `SRC-001 §5.2.3` (categories are priced differently) · `§5.5.1` (the admin sets the
price) · `§10.15` (the question).

Basis points and the zero-uplift-Standard shape are the build session's under Art III.9.

## Consequences

Three category rows exist — Standard, Premium, Recliner — and those names are `ASSUMED`, not ruled
(`OPEN-SEAT-01`, "you pick"). **They never harden into a constraint** and must be flagged as assumed
each time they matter. A table rather than an enum (`FR-ADR-016`) is what makes a fourth category
free.

A showtime with no base price cannot exist, so the admin form cannot create one without it. A
`bigint` non-null column with no default makes that a database-level truth rather than a form
validation.

The uplift being global means one edit changes the price of every future show in every hall at once.
That is the ruled behaviour and it is also the most dangerous single admin write in the system — which
is why it carries an audit row with before and after (`FR-ADR-019`) and optimistic concurrency
(`FR-ADR-035`).

**If the client reverses the per-showtime reading to a global base price**, the column moves to a
configuration value and existing showtimes are backfilled. Contained, and recorded as such.
