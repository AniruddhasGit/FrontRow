# INR, integer paise, a minor-unit ratio of 100, and Asia/Kolkata — and the ratio is a one-way door

```
ADR id ............ FR-ADR-036
Pack .............. PACK-MONEY
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-LOCALE-01; SRC-001 §10.4; SRC-001 §7.6; SRC-002 §7.1
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §10.4` asked which country and city the product launches in and which currency. It was raised
as `OPEN-LOCALE-01` and classed reserved — money — because no model may choose a currency.

It blocked more than the interface. A minor-unit ratio cannot be hardcoded before it is known, and
until it was known there was no correct type for a money column.

The client answered: "India launched currency is rupees."

## Decision

**Market: India. Currency: INR. Minor unit: paise. Ratio: 100. Timezone: Asia/Kolkata.**

**Money is stored as an integer number of paise. Never a float, anywhere, at any layer.**

- **`Decimal` at the boundary.** A value arriving as text or JSON is parsed to `Decimal`, validated,
  and converted to an integer number of paise before it goes any further.
- **`bigint` in persistence.** Every money column is an integer count of paise. `bigint` rather than
  `integer` for the same reason as `FR-ADR-017`: nothing is deleted, revenue totals accumulate, and a
  2.1-billion-paise ceiling is ₹21,474,836 — reachable, and a ceiling that exists for no reason.
- **A formatted string at render time only.** Formatting happens in the presentation layer and nowhere
  else. A formatted money value never travels through an API response as the value of record.

**A float on the money path is a defect regardless of whether a test caught it.** Floats cannot hold
0.10 and summing them drifts.

**The ratio 100 is a one-way door.** `SRC-001 §7.6` makes bookings permanent, so reinterpreting the
minor unit later silently rewrites what every past customer paid. There is no migration that fixes
that, because there is no way to tell which rows were written under which interpretation.

**It is therefore a named configuration value, not a literal.** `CURRENCY_CODE=INR` and
`CURRENCY_MINOR_UNIT_RATIO=100` come from the environment (`SRC-002 §7.1`), are validated at startup,
and are logged once at boot so the running value is visible in the log. **`100` never appears as a
literal on the money path.** Not in a conversion, not in a test fixture, not in a seed script.

**No currency column per money value.** One currency exists and a per-row currency column would be a
constant repeated on every row, inviting a mixed-currency sum that nobody validates. If a second
currency ever arrives it is a schema change, and it should be one — it is a decision, not a data
point.

**Asia/Kolkata is the cinema's zone** and is stored on the cinema row (`FR-ADR-018`), not as a global
constant, for the same reason.

## Alternatives rejected

**`numeric(12,2)` in PostgreSQL.** Rejected. It is exact and it would work, but it lets a fractional
paisa be written, which is the case the rounding rule in `FR-ADR-038` exists to eliminate at source.
Integers make an unrounded value impossible to store rather than merely discouraged.

**A float or double for money.** Rejected outright. `GOTCHAS.md` records it and Art V.2 makes it a
defect.

**Store rupees rather than paise.** Rejected. Percentage uplifts (`FR-ADR-037`) produce sub-rupee
amounts, and rounding to whole rupees would make a 12.5% uplift on ₹250 either ₹281 or ₹282 with the
difference invisible.

**Hardcode 100, since INR is ruled and the ratio is a fact about INR.** Rejected. The ratio being a
fact is exactly why it must be explicit — a fact that is never stated is a fact nobody can check, and
Art V.3 requires it to be a named value.

**A per-row currency column for future-proofing.** Rejected above.

## Source

`SRC-003 OPEN-LOCALE-01` ("India launched currency is rupees") · `SRC-001 §10.4` (the question) ·
`§7.6` (bookings are permanent, which is what makes the ratio irreversible) ·
`SRC-002 §7.1` (twelve-factor configuration).

## Consequences

Every money column, every API field carrying money, and every test fixture deals in integer paise.
A field named `price` that holds `250.00` is a defect; the field is `price_paise` and holds `25000`.
**The naming convention is part of the decision** — a suffix on every money identifier is the cheapest
way to make a unit error visible in a code review.

`SUM()` over a `bigint` column returns `numeric` in PostgreSQL, which arrives in Python as `Decimal`
and mixes badly with `int`. `GOTCHAS.md` records it and it is directly relevant to the dashboard's
revenue totals (`FR-ADR-043`): cast back to `BigInteger` in the query.

Rendering uses Indian digit grouping — ₹2,50,000.00, not ₹250,000.00 — because the market is India.
That is a presentation rule and `FR-ADR-044`'s pack carries it.

**No tax is shown separately** (`FR-ADR-040`), so the stored total is a single figure that cannot be
split later. That is recorded there as an accepted consequence.
