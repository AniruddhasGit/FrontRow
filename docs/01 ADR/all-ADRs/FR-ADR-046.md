# A guest is stopped at the hold, and their seat selection survives the login round trip

```
ADR id ............ FR-ADR-046
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-BOOK-02; SRC-003 OPEN-ROLE-01; SRC-001 §4.1; SRC-001 §3.1; SRC-001 §5.1.3; SRC-003 C-2
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`FR-ADR-014` rules that booking requires an account and that a guest may see the seat map but cannot
hold. That settles the authorisation boundary. It does not settle the experience at it, and the
experience is what decides whether the customer completes.

`SRC-001 §3.1` says a customer should complete a booking end to end in under two minutes. A guest who
picks four seats, is bounced to a registration form, and returns to an empty seat map has spent that
budget twice and will probably leave.

A second question sits nearby: `SRC-001 §5.1.3` asks customers to filter by cinema, and there is one
cinema (`C-2`).

## Decision

**The guest is stopped at the hold — that is, at the moment they try to proceed with a selection —
not at the seat click and not at payment.**

- A guest may click seats. The selection is local and takes no lock, so it costs nothing and consumes
  nothing scarce.
- The running total updates as they select, exactly as it does for a customer (`SRC-001 §5.2.4`).
  Seeing the price is part of deciding.
- The primary action reads **"Sign in to hold these seats"** rather than "Continue". The requirement
  is stated before it is enforced, not discovered by clicking.
- Pressing it opens the authentication step. It does not navigate away and lose context.

**The selection survives the round trip.** The chosen seat ids and the showtime are held in
`sessionStorage` before the authentication step and restored after it.

**On return, the hold is not taken automatically.** The seats are re-selected in the interface and the
customer presses the action again.

That is deliberate. Between selecting and returning, a seat may have gone. Automatically taking a hold
would either silently drop the missing seat — the customer pays for three of the four they chose — or
fail with an error immediately after a successful registration, which reads as the registration having
failed. **Restoring the selection and letting them press once is one click that removes both failure
modes**, and it re-checks availability at the moment it matters.

**If a seat has gone while they were registering, it is shown as taken in the restored selection** and
the customer adjusts before pressing. `SRC-001 §5.2.6`'s "tell our customer immediately and clearly"
applies here as much as it does mid-checkout.

**Registration and sign-in are one screen with two tabs**, not two destinations. A new customer and a
returning one arrive at the same point with the same context.

**The cinema filter is not rendered while one cinema exists.** A dropdown with one option is a control
that cannot be used, and it makes the interface look like a template. The filter's code path exists
and the API supports the parameter — `SRC-001 §5.1.3` requires the capability, `C-2` explains why
there is one row today, and `SRC-001 §6.6` forbids blocking a second venue. **The control renders
automatically once more than one cinema exists**, so nothing has to be remembered later.

**Date, language and format filters render always**, because all three have multiple values from day
one.

## Alternatives rejected

**Stop the guest at the seat map.** Rejected. `SRC-001 §4.1` grants guests browsing, and seeing what
is available is what makes someone register.

**Stop the guest at payment, letting them hold seats first.** Rejected in `FR-ADR-014`: an
unauthenticated hold endpoint lets anyone lock a whole hall for three minutes with no account.

**Take the hold automatically on return from authentication.** Rejected above on both failure modes.

**Preserve the selection in a URL parameter rather than `sessionStorage`.** Rejected. A long seat list
in a query string is fragile, it survives being shared or bookmarked in a way that is confusing, and
`sessionStorage` clears itself when the tab closes, which is the right lifetime.

**Preserve it server-side against a session.** Rejected under `SRC-002 §7.3` — no local session state
— and it would need a store for data that is worth nothing thirty seconds later.

**Render the cinema filter with one option, for consistency.** Rejected above.

**Remove the cinema filter from the API too.** Rejected under `SRC-001 §6.6`.

## Source

`SRC-003 OPEN-BOOK-02` (booking requires an account) · `OPEN-ROLE-01` (a guest browses, then registers
to purchase) · `SRC-001 §4.1` (guests browse) · `§3.1` (under two minutes end to end) ·
`§5.1.3` (filter by cinema) · `SRC-003 C-2` (one cinema, the entity stays).

The stopping point, the selection-preservation mechanism and the filter-rendering rule are the build
session's under Art III.9.

## Consequences

A guest's selection is entirely client-side, so nothing on the server distinguishes a guest looking at
a seat map from a customer looking at one. The seat-map endpoint stays unauthenticated and cacheable
(`FR-ADR-030`).

The two-minute target in `SRC-001 §3.1` is measured from the seat map for a signed-in customer. For a
first-time guest it includes registration and will not be met — that is worth stating rather than
quietly measuring the easier path.

The restored-selection path needs a test where a seat is taken by another customer between selection
and return, asserting the customer is told rather than silently given three of four seats.

**Whether an account must verify its email before it can book** is decided in `FR-ADR-050`, and it
matters here: a verification step inserted into this flow would add a second interruption at exactly
the point this record is trying to protect.
