# The rounding rule: integer half-up, applied per seat, never to the total

```
ADR id ............ FR-ADR-038
Pack .............. PACK-MONEY
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-PRICE-01; SRC-003 OPEN-LOCALE-01; SRC-001 §5.2.4; SRC-001 §7.6
Constitution ...... frontrow-constitution@0.1.0
```

> **Reserved-but-reversible, decided and batched for the client to reverse** (Art III.9). Rounding is
> money. It is also reversible: `FR-ADR-039` snapshots the price onto every booked seat, so changing
> this rule later reprices nothing that was already sold. The client may reverse it at any time and it
> is surfaced for exactly that.

## Context

`SRC-003 OPEN-PRICE-01` gives the formula — a base price plus a fixed percentage uplift per seat
category — and says the rounding rule is to be stated with a worked example, "because a percentage of
an integer number of paise does not divide evenly and an unstated rounding rule is how two screens
disagree about a total".

`CONSTITUTION.md` Art IX.4 makes this an obligation rather than a nicety: every rule that computes a
number states the rule, its inputs, and a worked example with the expected answer. A specification
that computes money and gives no worked example cannot produce a binary test.

There are two independent questions and both are usually left implicit.

**Which way does a half go?** Half-up, half-even, floor or ceiling. The difference is one paisa per
seat, which sounds trivial until the seat map and the checkout screen implement it differently.

**Is rounding applied per seat and then summed, or once to the total?** This one changes the answer by
more than a paisa as the seat count grows, and it is the one that produces two screens disagreeing.

## Decision

**Rounding is half-up, on positive integers, computed in integer arithmetic with no float and no
`Decimal` anywhere in the expression.**

**Rounding is applied per seat. The booking total is the sum of the already-rounded per-seat prices.
The total is never rounded.**

**The rule:**

```
seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000

booking_total_paise = sum of seat_price_paise over every seat in the booking
```

`10000` is the basis-point denominator: one basis point is 0.01%, so a 100% multiplier is `10000`
basis points. Adding half the denominator — `5000` — before an integer floor division is integer
half-up. Both are named constants, not literals scattered through the code.

**Half-up rather than half-even**, because it is what a person doing the arithmetic by hand produces.
Banker's rounding gives a figure that differs from the obvious hand calculation, and the client — who
is also the operator — would reasonably conclude the system was wrong. Half-even's statistical
argument matters when rounding millions of transactions in an accounting system; it does not apply to
a per-seat ticket price a human checks against a calculator.

**Per seat rather than on the total**, because the seat map shows a per-seat price and
`SRC-001 §5.2.4` requires the running total to update as seats are selected. If the total were rounded
once, the displayed per-seat prices would not add up to the total shown next to them, and the customer
would be looking at two numbers that disagree.

### Worked examples

All figures in paise. Base price `25000` paise = ₹250.00.

**1. Standard, 0 basis points — no rounding occurs.**

```
(25000 * (10000 + 0) + 5000) // 10000
= (250000000 + 5000) // 10000
= 250005000 // 10000
= 25000                                  →  ₹250.00
```

**2. Premium, 1250 basis points (12.5%), on a base of 24999 paise — a genuine round.**

```
exact value = 24999 * 1.1250 = 28123.875 paise

(24999 * 11250 + 5000) // 10000
= (281238750 + 5000) // 10000
= 281243750 // 10000
= 28124                                  →  ₹281.24
```

Half-up takes `.875` up to `28124`. Floor would give `28123`.

**3. Recliner, 3333 basis points (33.33%), on a base of 25000 paise — an exact half, the case the
rule exists for.**

```
exact value = 25000 * 1.3333 = 33332.5 paise      ← exactly half

(25000 * 13333 + 5000) // 10000
= (333325000 + 5000) // 10000
= 333330000 // 10000
= 33333                                  →  ₹333.33
```

**Half-up gives 33333. Half-even would give 33332** — because 33332 is the even neighbour. One paisa,
and it is the single case where the two rules visibly disagree.

**4. Three Recliner seats — why the total is not rounded.**

```
per-seat, then sum:   33333 * 3        = 99999 paise   →  ₹999.99   ← this is the rule
round the total once: (33332.5 * 3)    = 99997.5
                      half-up          = 99998 paise   →  ₹999.98
```

**One paisa apart, and the first is what the customer was shown three times on the seat map.** This is
the disagreement `OPEN-PRICE-01` warned about, made concrete.

## Alternatives rejected

**Half-even (banker's rounding).** Rejected above. Correct in accounting systems, surprising here, and
it disagrees with the obvious hand calculation on exactly the tie case.

**Floor — always round down, in the customer's favour.** Rejected. It is defensible as a policy and it
is a *policy*, not an arithmetic convention: the business would systematically under-collect. That is
a money decision the client would have to make, and it would have to be stated to them as one rather
than smuggled in as a rounding choice.

**Ceiling — always round up.** Rejected for the mirror reason, and it is worse: it systematically
overcharges by up to a paisa per seat with no ruling behind it.

**Round the booking total once.** Rejected above — the displayed per-seat prices would not sum to the
displayed total.

**Compute in `Decimal` and quantise.** Rejected. It would produce the same answers if configured
correctly, and it adds a type whose rounding mode is set somewhere else — a context, a constructor
argument, or a default — which is one more place for the two screens to disagree. Integer arithmetic
has no mode to set.

**Leave the rule to the PRD, as `OPEN-PRICE-01` suggested.** Rejected. The data model is written
before the PRD in this project's dependency order, and it needs to know whether a rounded value is
stored. It is decided here and the PRD cites this record.

## Source

`SRC-003 OPEN-PRICE-01` (the formula, and the requirement that the rounding rule be stated with a
worked example) · `OPEN-LOCALE-01` (integer paise) · `SRC-001 §5.2.4` (the running total updates as
seats are selected) · `§7.6` (bookings are permanent).

The rounding mode and the per-seat application are the build session's under Art III.9, batched for
client reversal.

## Consequences

**One function computes a seat price, and every caller uses it.** The seat map, the checkout total,
the receipt, the dashboard revenue and the seed script all call the same function. Two
implementations of this formula is the failure mode, not the formula being wrong.

That function is a pure function of two integers and it gets a table-driven test whose cases include
all four worked examples above, byte for byte.

The rounded per-seat price is what is snapshotted onto the booked seat row (`FR-ADR-039`), so the
stored figure is the one the customer saw.

**No fractional paisa is ever storable**, because every money column is a `bigint` (`FR-ADR-036`).
That is not belt-and-braces — it means a caller that skips the rounding function cannot silently
persist an unrounded value; it gets a type error instead.

If the client reverses this to floor or half-even, the change is one function and its test table.
Nothing already sold moves, because the price was snapshotted.
