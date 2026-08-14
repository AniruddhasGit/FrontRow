# A multi-seat hold is all-or-nothing, capped at ten seats, and enforced server-side

```
ADR id ............ FR-ADR-026
Pack .............. PACK-CONC
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-BOOK-01; SRC-003 OPEN-SEAT-03; SRC-001 §5.2.6; SRC-002 §8.1.2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-003 OPEN-BOOK-01` caps a booking at ten seats. `SRC-002 §8.1.2` requires atomic acquisition, but
it is written about one seat — "two users clicking the same seat at the same millisecond".

A customer selecting four seats produces four lock acquisitions. Nothing in the frozen sources says
whether those four succeed or fail together, and the difference is visible to the customer:
partial success means someone pays for three of the four seats they wanted and sits apart from the
person they came with.

Nothing says whether the ten-seat cap applies to the hold or only to the booking, either. If it
applies only at booking, a customer can hold a whole hall and then book ten of it.

## Decision

**A hold request names a set of seats and succeeds or fails as a whole.**

**The cap is ten, and it is enforced at the hold**, not only at confirmation. A request for eleven
seats is rejected before any lock is taken.

**The cap counts the customer's live holds on that showtime, not just this request.** Two requests for
six seats each on the same showtime is eleven seats held by one customer, and the second is refused.

**Acquisition order is deterministic: seat ids ascending.** Two customers requesting overlapping sets
therefore contend in the same order, which turns a possible mutual stall into a clean loser.

**On partial acquisition, the seats that were won are released immediately, using the same
compare-and-delete script that a normal release uses.** The customer is told which seats were taken,
by whom nothing is said, and their selection is left intact so they can adjust it —
`SRC-001 §5.2.6` requires them to be told immediately and clearly.

**That release is best-effort, and it is safe that it is.** If the API instance dies after winning
three of four locks and before releasing them, those three seats stay held for the remainder of the
3-minute TTL and then free themselves. No cleanup job is needed and none exists (`FR-ADR-005`). Three
seats unavailable for under three minutes is an acceptable worst case; the alternative — a
transactional release — would need a durable record of the partial hold, which reintroduces the hold
table `FR-ADR-025` rejected.

**Re-selecting a seat the same customer already holds is a no-op that succeeds, and does not extend
the TTL.** The hold's expiry is fixed at acquisition (`FR-ADR-027`), so a client that re-sends its
selection cannot walk the deadline forward.

**One customer may hold seats on more than one showtime at a time.** Nothing rules against it and it
is a legitimate purchase pattern — two films in one evening. The ten-seat cap is per showtime.

## Alternatives rejected

**Per-seat acquisition with partial success, letting the customer keep what they got.** Rejected on
the product outcome: a group of four that becomes a group of three is worse than a clear failure, and
`SRC-001 §5.2.6` is written about telling the customer immediately, which implies the selection is a
unit.

**A Redis transaction (`MULTI`/`EXEC`) or a Lua script that acquires all seats atomically.** This is
technically cleaner — genuinely all-or-nothing with no release path. Rejected because it makes the
error message worse: an all-or-nothing script reports failure without naming which seats were taken,
and the customer needs to know which ones to change. Sequential acquisition with rollback gives a
precise answer. The cost is the best-effort release above, which is bounded by the TTL.

**Enforce the cap only at booking confirmation.** Rejected. A customer could hold a 220-seat hall and
release nothing for three minutes, which is a denial of service with a valid account.

**Cap the total number of seats a customer may hold across all showtimes.** Rejected as a rule with no
basis in any ruling, and it would refuse a legitimate double booking. The per-showtime cap is what
`OPEN-BOOK-01` describes.

## Source

`SRC-003 OPEN-BOOK-01` ("10 maxx") · `OPEN-SEAT-03` (seats are individual, so a set is a set of
independent locks) · `SRC-001 §5.2.6` (tell the customer immediately and clearly) ·
`SRC-002 §8.1.2` (atomic acquisition).

All-or-nothing, the ordering rule, and the cap's application at hold time are the build session's
under Art III.9.

## Consequences

The hold endpoint takes a list and returns a hold token plus an expiry instant, or a 409 naming the
seats that were unavailable. It never returns a partial success.

The ten-seat cap is enforced in the domain layer, so the interface limit is a convenience and not the
control. The test asserts the eleventh seat is refused by the API with the interface bypassed.

Deterministic ordering matters for the stress test too: fifty requests for one seat is the required
proof (`SRC-002 §9.1`), but overlapping multi-seat requests are the case that would deadlock a naive
implementation, and they need their own test.

The cap check reads the customer's live holds on that showtime from Redis, which is a lookup of at
most ten known keys, not a scan.
