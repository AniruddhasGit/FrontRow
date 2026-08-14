# Sales close 15 minutes after the advertised start, and existing holders may finish

```
ADR id ............ FR-ADR-042
Pack .............. PACK-MONEY
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED_PROVISIONAL
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-BOOK-03; SRC-001 §10.12; SRC-003 OPEN-LOCALE-01; SRC-002 §7.1
Constitution ...... frontrow-constitution@0.1.0
```

> ## ⚠ PROVISIONAL — the direction could go either way, and one message settles it
> The question asked how long **before** a show starts sales stop. The recommendation proposed a
> number of minutes **after** the start, because of trailers. The client answered `"yes 15 minutes"`.
> **The alternative reading is 15 minutes before the start.** `SRC-003 OPEN-BOOK-03` records both.

## Context

`SRC-001 §10.12` asked: how long before showtime do sales stop. It was raised as `OPEN-BOOK-03` with a
recommendation that proposed closing sales *after* the advertised start, on the reasoning that a
cinema runs trailers and a customer arriving at the advertised time has not missed anything.

The answer — `"yes 15 minutes"` — agrees with something and supplies a number, and it is genuinely
ambiguous which. `"yes"` reads as agreement with the recommendation's shape, which was "after". The
question's own wording was "before".

The two readings are thirty minutes apart and they produce opposite behaviour at the advertised start
time: under one reading the show is still selling, under the other it closed a quarter of an hour ago.

Art VII.3 forbids inventing an answer, and there is an answer here — it just has two readings. So the
reading is recorded, the rejected one is named, and it is flagged `PROVISIONAL`.

## Decision

**Sales close 15 minutes after the advertised start time.**

```
sales_close_at = showtime.starts_at + SALES_CUTOFF_MINUTES
SALES_CUTOFF_MINUTES = +15    (positive means after the start)
```

**It is a signed configuration value, not a constant.** A negative value produces the alternative
reading, so **reversing this decision is a configuration change and nothing more** — no code path
changes, no migration, no schema move. That is the reason it is expressed as a signed offset rather
than as "start plus fifteen minutes" written into the comparison.

**It is derived at evaluation time, never stored on the showtime row** (`FR-ADR-018`), so changing the
configuration takes effect immediately across every showtime rather than requiring a backfill.

**Evaluated in the cinema's zone against the injected clock**, never against the container's local
time.

**Checked at hold acquisition, not at confirmation.** A customer who acquired a hold before the
cut-off may finish checking out after it — `SRC-003 OPEN-BOOK-03` says so explicitly. The hold is at
most three minutes (`FR-ADR-027`), so the practical last moment a booking can complete is the cut-off
plus the hold.

**Two consequences of checking at hold rather than confirm, both intended:** the confirm path does not
need to re-check and cannot reject a customer who is already paying; and the effective close is
`starts_at + 15 minutes + hold`, which is the honest number and belongs in the runbook rather than
being rounded off.

**A past-cut-off showtime is still visible to customers.** It is shown with its seat map, marked
closed, and its seats are not selectable. Hiding it would make a customer think the showtime never
existed. `FR-ADR-045` carries the presentation.

## Alternatives rejected

**15 minutes before the advertised start.** This is the rejected reading and it is recorded rather
than dismissed. It matches the question's literal wording. It was not chosen because `"yes"` most
naturally attaches to the recommendation it answered, and because the recommendation's reasoning —
trailers — is a real property of cinemas.

**Ask the client again before proceeding.** Rejected, narrowly. The question was already asked once
and answered; re-asking the same question is how a decision queue stalls. The reading is recorded, the
reversal is a single configuration value, and it is flagged in the handoff. Under Art III.9 that is
the decide-then-batch path, and it is the right one for a reversible matter.

**Store the computed cut-off on the showtime row.** Rejected. Changing the offset would need a
backfill across every future showtime, and a row whose stored cut-off disagrees with the configured
offset is a bug nobody would find.

**Enforce the cut-off at both hold and confirmation.** Rejected. It would reject a customer who is
mid-payment, which contradicts the ruling's own second half.

**Hide past-cut-off showtimes from the listing.** Rejected above.

## Source

`SRC-003 OPEN-BOOK-03` (`"yes 15 minutes"`, with both readings recorded) · `SRC-001 §10.12` (the
question, worded "before") · `OPEN-LOCALE-01` (the zone the comparison runs in) ·
`SRC-002 §7.1` (configuration, not a constant).

## Consequences

**Under this reading a customer can buy a ticket for a film that started fourteen minutes ago.** That
is intentional and it matches how a cinema with trailers behaves. Under the other reading they cannot
buy one that starts in fourteen minutes. Both are defensible and the client owns which.

The acceptance criterion is binary and testable either way, because the clock is injected: set the
clock to `starts_at + 14m` and assert a hold succeeds; set it to `starts_at + 16m` and assert a 409.
**When the client rules, only the configured value and those two assertions change.**

The seat map for a closed showtime is still served, so the read path has no special case beyond a
flag in the response.

**This is flagged in the handoff for reversal**, alongside the other two `PROVISIONAL` readings —
`FR-ADR-009` on roles and `FR-ADR-010` on one cinema.
