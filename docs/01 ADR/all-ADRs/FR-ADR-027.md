# The hold is 3 minutes from configuration, superseding the 7 minutes nobody decided

```
ADR id ............ FR-ADR-027
Pack .............. PACK-CONC
Decision type ..... CLIENT_RULING
Decision owner .... client
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ Aniruddha Jathar (SRC-003)
Decision date ..... 2026-08-14
Source ............ SRC-003 OPEN-HOLD-01; SRC-002 §E E-1; SRC-002 §8.1.1; SRC-001 §10.9; SRC-002 §7.1
Constitution ...... frontrow-constitution@0.1.0
```

> **This record exists as much for how the number was arrived at as for the number.** It is the one
> trap this project had already sprung before any code was written, and the method's whole
> justification rests on it.

## Context

`SRC-001 §10.9` is one of the client's own open questions: *"How long should selected seats be held
while the customer pays? **We assumed 7 minutes.**"*

`SRC-002 §8.1.1`, written by the same person as the developer, then says: *"place a lock in Redis with
a TTL of **7 minutes**"* — stated as a firm requirement.

**An assumption in a question became a specification in the next document, and nobody decided it.**
Not the client, who was still asking. Not the build session, which had not been engaged. The number
simply propagated because it was already written down, and by the time anyone read `§8.1.1` it looked
like a requirement.

It was raised as `OPEN-HOLD-01` rather than implemented. The client answered: **"make this 3
minutes."**

**It came back different from the assumption.** That is the entire argument for the mechanism, and it
is why `ASSUMED` may never become a `MUST` on this project.

## Decision

**The seat hold TTL is 3 minutes.**

**It is read from a configuration value, never a constant.** `SRC-002 §7.1` requires every setting to
come from an environment variable, and this one has already been changed once by a client message. A
literal `180` anywhere in the code is a defect against this record.

`SRC-002 §8.1.1`'s 7 minutes is superseded by erratum `E-1` and is dead text. **Any document, test or
comment stating 7 minutes is a defect**, including a test fixture that happens to use it.

**The expiry instant is fixed at acquisition and does not move.** The API computes `expires_at` once,
returns it to the client, and the Redis `PX` is set from the same value. The TTL is not refreshed by
polling, by re-selecting a held seat, or by any other activity — see `FR-ADR-026`.

**There is no extension mechanism.** A customer whose hold expires re-selects their seats and takes a
new hold, competing on equal terms with everyone else. An extend button is a way for one customer to
hold a seat indefinitely.

**Expiry is measured by Redis alone.** No second timestamp exists to disagree with it
(`FR-ADR-025`), so there is no clock skew between API instances to reconcile.

## Alternatives rejected

**Keep 7 minutes because `SRC-002 §8.1.1` states it as a requirement.** Rejected — this is the whole
point. Under Art II.1 a client ruling outranks the raw mandate, and `E-1` is filed.

**Make it 3 minutes as a constant, since it is now ruled.** Rejected under `SRC-002 §7.1` and on
evidence: this value has already changed once. A ruled value is not an immutable value.

**Refresh the TTL while the customer is active on the page.** Rejected in `FR-ADR-026`. The seat map
polls every three seconds, so any activity-based refresh makes the hold unbounded for any open tab.

**Offer a one-time extension.** Rejected as a rule with no ruling behind it, and because "one-time"
becomes "per session" the first time someone asks.

**Make the hold longer for larger selections.** Rejected for the same reason. It is a plausible
kindness that nobody ruled.

## Source

`SRC-003 OPEN-HOLD-01` ("make this 3 minutes") · `SRC-002 §E E-1` (the erratum) ·
`SRC-002 §8.1.1` (the superseded 7 minutes, cited as the text being corrected) ·
`SRC-001 §10.9` (the assumption that became it) · `SRC-002 §7.1` (twelve-factor configuration).

## Consequences

**Three minutes is tight for a real payment flow and comfortable for a simulated one.** The client's
own ruling notes this. Since `FR-ADR-041` makes payment simulated with an artificial delay, the flow
fits — but the artificial delay must be well under three minutes, and `FR-ADR-041` bounds it.

The expiry path becomes easy to exercise. A three-minute wall-clock wait is intolerable in a test
suite, which is why time is injected (`FR-ADR-018`) and expiry is tested by advancing an injected
clock, not by sleeping.

**The check `GOTCHAS.md` demands applies to every number in this project:** when a figure appears in a
specification, find the ruling that produced it. If the only source is an assumption, it is `ASSUMED`,
not `RULED`. Five figures on this project are still `ASSUMED` — hall sizes, peak concurrency and the
seat category names — and each must be flagged as such every time it matters.

The SIGTERM lock release (`FR-ADR-033`) interacts with this: an instance shutting down would otherwise
strand every seat it holds for the full three minutes.
