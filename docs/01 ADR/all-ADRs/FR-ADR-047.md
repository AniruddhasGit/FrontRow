# The hold countdown runs from a server-issued expiry instant, and expiry is handled by the server's answer

```
ADR id ............ FR-ADR-047
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-001 §5.2.5; SRC-001 §5.2.6; SRC-003 OPEN-HOLD-01; SRC-002 §E E-1; SRC-002 §8.1.4
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-001 §5.2.5` requires selected seats to be held temporarily while the customer completes payment,
then released automatically if they do not finish. `FR-ADR-027` makes that three minutes.

Three minutes is short. A customer who does not know they are on a clock will lose their seats, and a
customer who does know needs to be able to trust the number they are shown.

Nothing in the frozen sources says whether a countdown is displayed, what happens at zero, or which
side — client or server — decides that the hold has expired. Getting the last one wrong produces the
worst outcome: a client that believes the hold is alive submitting a payment against seats that are
gone.

## Decision

**The hold response carries an absolute expiry instant**, `expires_at`, in UTC. Not a duration and not
a remaining-seconds count.

An absolute instant is immune to clock skew in the way that matters: the client renders a countdown by
subtracting from its own clock, and a client clock that is wrong by a minute shows a wrong countdown —
but **the server never trusts the client's arithmetic**, so a wrong countdown cannot produce a wrong
outcome. A remaining-seconds count would also drift with network latency and with any pause in the
tab.

**A countdown is displayed** from the moment the hold is taken, in `m:ss`, on both the seat map and
the checkout screen. It is not hidden behind a tooltip; a customer with three minutes is entitled to
see all three.

**A warning at 60 seconds** — the countdown changes appearance and a short message names what happens
at zero. One threshold, not several: repeated escalation is noise, and 60 seconds is enough to finish
a simulated payment (`FR-ADR-041` bounds the artificial delay well below it).

**At zero the client stops the countdown, disables the payment action, and shows that the hold has
expired.** It does **not** delete anything, release anything, or claim the seats are free — it only
reports what its own clock says.

**The server is the authority.** Any request against an expired hold is refused with a 409, whether or
not the client noticed. `FR-ADR-029` re-validates the hold inside the confirm transaction for exactly
this reason. A client whose clock runs slow and submits at 3:05 is refused by the server, not
permitted by the countdown.

**On expiry the customer is returned to the seat map with their previous selection re-applied**, and
the map refreshed. Seats still free are re-selectable; seats taken in the interim are shown as taken.
The customer is not dumped on an error page and made to start from the movie listing.

**No extension and no renewal** (`FR-ADR-027`). Re-selecting takes a new hold and competes on equal
terms.

**The hold token lives in `sessionStorage`, so a page refresh keeps the hold.** A customer who reloads
mid-checkout finds their seats still theirs and their countdown still running from the same
`expires_at`. Without this a refresh would orphan a live hold — the seats locked, the customer unable
to confirm them, for the remainder of the three minutes.

**Closing the tab does not release the hold.** There is no unload-time release, because an unload
handler is unreliable and because a fire-and-forget release from a closing page can arrive after the
lock has expired and been re-acquired — the compare-and-delete token (`FR-ADR-025`) makes that
harmless, but the request is still one that cannot be relied on. The TTL is what releases it, which is
what `SRC-002 §8.1.4` intends.

## Alternatives rejected

**Send a remaining-seconds duration instead of an instant.** Rejected: it starts drifting the moment
it is sent and cannot survive a tab pause.

**Let the client release the hold at zero.** Rejected. It puts a correctness action on an unreliable
actor, and an abandoned tab firing a release is the exact scenario the lock token exists to defend
against.

**Trust the client's countdown and skip the server-side re-validation.** Rejected. It is the failure
this record exists to prevent.

**Show no countdown and let expiry surprise the customer.** Rejected against `SRC-001 §5.2.5` and
`§5.2.6`. Three minutes with no warning is an ambush.

**Warn at 60, 30 and 10 seconds.** Rejected as noise.

**Store the hold token in `localStorage`.** Rejected. It outlives the tab, so a stale token from
yesterday would be presented against a hold that no longer exists. `sessionStorage` has exactly the
right lifetime.

**Release the hold on `beforeunload`.** Rejected above.

## Source

`SRC-001 §5.2.5` (held temporarily, then released automatically) · `§5.2.6` (tell the customer
immediately and clearly) · `SRC-003 OPEN-HOLD-01` (three minutes) · `SRC-002 §E E-1` ·
`§8.1.4` (expiry needs no cleanup job).

The absolute instant, the single warning threshold and the storage choice are the build session's
under Art III.9.

## Consequences

The countdown is a display of a server fact, so it can be tested by asserting the response carries
`expires_at` and that the server refuses at `expires_at + 1s` on an injected clock. **The countdown
component itself never needs a wall-clock test**, which Art IX.5 would make a defect.

A customer whose device clock is badly wrong sees a wrong countdown and is still handled correctly by
the server. That is a visible oddity with no correctness consequence, and it is the right place for
the failure to land.

Refresh-safety through `sessionStorage` is a small feature with a large effect on a three-minute
window, and it needs its own test: take a hold, discard the page state, restore from storage, confirm
successfully.

The 60-second warning interacts with `FR-ADR-041`'s artificial payment delay. If that delay were ever
raised near a minute the warning would fire during payment, which is why the delay is validated at
startup against the hold TTL.
