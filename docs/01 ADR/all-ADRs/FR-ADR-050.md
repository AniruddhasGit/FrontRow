# Authentication: email and password, no email verification gate in v1, and a password reset that exists

```
ADR id ............ FR-ADR-050
Pack .............. PACK-UX
Decision type ..... JUDGMENT_CALL
Decision owner .... build session
Decision status ... APPROVED
Decision outcome .. ADOPTED
Decided by ........ build session (Art III.9)
Decision date ..... 2026-08-14
Source ............ SRC-002 §4.8; SRC-001 §5.4.1; SRC-001 §7.4; SRC-003 OPEN-BOOK-02; SRC-003 OPEN-TLS-01; SRC-002 §8.4.1
Constitution ...... frontrow-constitution@0.1.0
```

## Context

`SRC-002 §4.8` fixes authentication: our own email and password with JWT, and Cognito must not be
used. `SRC-001 §5.4.1` says customers register and log in with email and password.

Neither says anything about password rules, email uniqueness, whether an address must be verified, or
whether a customer can recover a forgotten password. All four have to exist in some form before a
customer can register at all, so all four will be decided by whoever writes the registration form if
they are not decided here.

One of them is load-bearing rather than routine. The account's email address is where the receipt goes
(`FR-ADR-048`), and the receipt is the only way into the hall. An unverified address is a plausible
route to a customer who has paid and cannot enter.

## Decision

**Email is the identity. Unique, case-insensitively.** Stored as entered, compared and constrained on
its lowercased form via a unique index on `lower(email)`. Storing a lowercased copy in a second column
would be two fields to keep in step.

**No email verification gate in v1.** A customer can register and book immediately.

That needs justifying, because verification is the obvious defence for the failure above. It is not
adopted for three reasons. It inserts a second interruption into exactly the flow `FR-ADR-046` is
protecting, and `SRC-001 §3.1` targets two minutes end to end. It makes registration depend on SES
being healthy, so an SES outage stops new customers registering as well as stopping receipts. And it
is **not the control that catches the real failure** — the most common bad address is a valid,
deliverable one belonging to someone else, or a typo that bounces, and a verification link solves the
second only at the cost of the first two problems.

**What is adopted instead:** the address is validated for shape and normalised, it is **displayed back
to the customer on the confirmation screen** — "a receipt is on its way to `<address>`"
(`FR-ADR-048`) — so a typo is visible at the moment it matters, and the reference is on screen and in
the bookings list regardless. **This is recorded as an accepted weakness rather than a solved
problem**, and it is directly connected to `OPEN-EMAILFAIL-01` (`FR-ADR-049`), which the client has
not yet ruled. If they rule in a direction that needs a verified address, verification is added then.

**Password rules — a length floor, not a composition rule.** Minimum 12 characters. No mandatory
mixture of character classes. Length is what resists guessing; composition rules push people toward
predictable substitutions and toward writing passwords down. The maximum is 72 bytes, enforced
explicitly and with a clear message, because **bcrypt silently truncates at 72 bytes** — a truncation
nobody sees means two different long passwords authenticate the same account.

**Hashed with bcrypt, off the event loop.** `GOTCHAS.md` records why: roughly 300 ms of CPU inside an
`async def` stalls every other request on that worker, and on a shared 1 GB host a handful of
simultaneous logins is a visible outage. It runs in a thread.

**The comparison runs even when the email is unknown**, against a dummy hash, so response timing does
not disclose whether an account exists.

**Login and registration are rate limited.** `SRC-002 §8.4.1` names seat selection and booking
specifically; extending the limiter to the credential endpoints is stricter and under Art III.10 needs
no signature. An unlimited login endpoint is an open guessing oracle.

**A password reset flow exists**, by emailed single-use token with a short expiry. Without one, a
customer who forgets their password loses access to every booking they have made, and under
`FR-ADR-012` the account cannot be deleted and re-created — the email is taken forever. **The reset
response is identical whether or not the address is registered**, for the same disclosure reason as
the login timing.

**JWT in an `HttpOnly`, `SameSite=Lax` cookie**, not in `localStorage`, so a script cannot read it.
**The `Secure` flag is environment-driven and is off in the deployed environment until TLS exists** —
`OPEN-TLS-01` is deferred and Art VIII.14 keeps that environment un-named as production for exactly
this reason.

**On session expiry mid-flow the customer is returned to sign-in with their context preserved**, using
the same `sessionStorage` mechanism as `FR-ADR-046`.

**Roles are a single column on the user row**, not a many-to-many table. `FR-ADR-009` rules four
mutually exclusive roles where admin is a superset of manager by capability, not by composition. A
role table would model a combination that cannot exist.

## Alternatives rejected

**Require email verification before booking.** Rejected above, on flow cost, on SES coupling, and
because it does not catch the most common bad address. Recorded as an accepted weakness.

**Composition rules — one uppercase, one digit, one symbol.** Rejected above.

**Ignore the bcrypt 72-byte limit.** Rejected. Silent truncation is a real authentication defect.

**Argon2id instead of bcrypt.** Better resistance, and a new dependency under `SRC-002 §13.1`. Rejected
as not worth a permission request for a demonstration project; recorded as the upgrade to ask for if
this ever holds real accounts.

**No password reset in v1.** Rejected. Combined with forever retention and a permanently taken email
address, a forgotten password would be an unrecoverable account.

**JWT in `localStorage`.** Rejected. Readable by any script on the page.

**Skip rate limiting on login because `§8.4.1` does not name it.** Rejected: stricter, no signature
needed.

## Source

`SRC-002 §4.8` (own email and password with JWT, never Cognito) · `SRC-001 §5.4.1` (register and log
in) · `§7.4` (passwords handled properly) · `SRC-003 OPEN-BOOK-02` (an account is required, and the
receipt goes to it) · `OPEN-TLS-01` (the `Secure` flag stays environment-driven) ·
`SRC-002 §8.4.1` (rate limiting).

Every specific rule here is the build session's under Art III.9.

## Consequences

**A customer can register with a mistyped address and book.** They see the address on the confirmation
screen and the reference is on screen and in their bookings list. That is the mitigation, and it is
not a guarantee. It is the single largest accepted weakness in the customer flow and it is tied to
`OPEN-EMAILFAIL-01`.

The password reset flow is a second thing that must go through SES, which makes SES load-bearing for
account recovery as well as for receipts.

Hashing in a thread means the login path is not purely async, and the thread pool size becomes a
tuning parameter inside the API's roughly 200 MB budget.

The `Secure` cookie flag being off in the deployed environment is a real weakness with a named owner
and an open row. It is why that environment is never called production.
