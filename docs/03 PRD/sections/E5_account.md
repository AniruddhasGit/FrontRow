# E5 — Account and bookings

This epic covers everything between a visitor deciding to buy and that visitor being someone the
system can name: registration, sign-in, the session, password recovery, and the list of bookings the
account owns. It is the only place in the product where a person becomes a row. Booking requires an
account (`SRC-003 OPEN-BOOK-02`), the receipt goes to that account's email address and nowhere else
(`FR-ADR-014`), and nothing in this system is ever deleted (`FR-ADR-012`) — so an email address, once
registered, is taken permanently and the account behind it must always be recoverable.

**The one thing that will be got wrong here is treating this epic as a form.** It is not. Three of its
requirements are load-bearing for the rest of the product and each is invisible if you only read the
screen. The password comparison must run even when the email is unknown, or the sign-in endpoint tells
an attacker which addresses have accounts. The seat selection must survive the sign-in round trip, or
the two-minute budget in `SC-1` is spent twice and the highest-intent visitor on the site abandons at
the last step. And the password reset must work with no help from anyone, because a forgotten password
against a permanently-taken email address is an account that can never be recovered and every booking
it ever made is gone with it. A fourth thing will be got wrong by reading a withdrawn clause:
`SRC-001 §5.4.3` (cancel a booking) is **withdrawn by erratum `E-2`**. There is no cancellation control
in the bookings list, on a booking, or anywhere else, and adding one is a defect.

---

## S4 — Product specifications

### `P-ACC-01` · Register an account · `RULED`
`[SRC: SRC-001 §5.4.1 · SRC-003 OPEN-BOOK-02 · SRC-003 OPEN-ROLE-01 · FR-ADR-050 · FR-ADR-014 · FR-ADR-009]`
`[BRD: R-ACC-01 · R-ACC-03]`

**Behaviour.** A visitor supplies an email address and a password and receives an account with the
role `customer` and a live session, in one request. Registration signs the customer in; it does not
return them to a sign-in form to type the same password again.

**Who may do it.** Anyone, including a guest with no session. The endpoint is `public`. A caller who
already has a valid session may still call it — it creates a second, separate account — because there
is no reason for the server to refuse and no state to corrupt.

**Preconditions.**

- The submitted email address is not already registered, compared on its lowercased form
  (`FR-ADR-050`).
- The password satisfies `P-ACC-03` in full.
- Redis is reachable, because the rate limiter fails closed (`FR-ADR-058`, `FR-ADR-028`).

**Happy path.**

1. The server trims leading and trailing whitespace from the email address. It does not trim, alter or
   normalise the password in any way.
2. The server validates both fields against `P-ACC-03` and the bounds table below.
3. The server checks `lower(email)` against the unique index. This is a read; the index is the guard.
4. The server hashes the password with bcrypt, in a thread, off the event loop (`P-ACC-03`).
5. The server inserts the user row: `email` as entered, `password_hash`, `role = 'customer'`,
   `password_version = 1`, `created_at`, and `last_signed_in_at = NULL`. There is no `name`, `phone` or
   `address` column — no frozen source asks for one, and inventing one would be inventing scope.
   `SRC-001 §6.6` means adding one later is a migration, not a redesign.

**The complete field list of the user row, because more than one section reads it.** `id`, `email`,
`password_hash`, `role`, `password_version`, `created_at`, `last_signed_in_at`. **Nothing else.**

| Field | Type | Set when | Notes |
|---|---|---|---|
| `last_signed_in_at` | `timestamptz`, UTC, **nullable** | null at creation; written on every successful sign-in (`P-ACC-02`) | **Null means the account has never signed in.** That is a real and expected state, not a defect — a manager account created by an admin (`E6 P-ADM-17`) has no usable password until the holder sets one, so it sits at null until they do. `E6`'s `has_signed_in` is derived from this column and is not stored anywhere |
| `password_hash` | `text`, **`NOT NULL`** | at every insert, without exception — including a manager account created by an admin, which has **no usable password** | **The column is never null and there is no "no password" state in the data.** See the block below. A nullable column here would put a branch on the sign-in path, and that branch is what destroys `P-ACC-03`'s timing property |

`last_signed_in_at` is added because **no other field in this row records that a sign-in happened**, and
`E6 EP-ADM-22` and `E6 SCR-ADM-06` need to state whether a manager account has ever been used. It is
useful on its own — it is the only way to tell a dormant account from a live one — and it costs one
nullable column.
6. A unique-violation on `lower(email)` from a simultaneous second registration is caught and
   translated into the `EMAIL_ALREADY_REGISTERED` response, exactly as a unique-violation on a seat is
   translated rather than surfaced as a 500 (`FR-ADR-052`).
7. The server issues the session cookie described in `P-ACC-05` and returns `201`.
8. No email is sent. There is no verification gate (`P-ACC-04`) and no welcome message — nobody asked
   for one and every message through SES competes with the receipt for a sandboxed sending quota
   (`FR-ADR-060`).

**What `password_hash` holds for an account with no usable password.** `E6 P-ADM-17` creates a manager
account the admin sets no password for. **That row still carries a real bcrypt hash**, and the column
is `NOT NULL` on every row in the table.

- At creation the server draws **32 bytes from a cryptographically secure source**, hashes those bytes
  with bcrypt at `BCRYPT_COST` (`P-ACC-03`), writes the result to `password_hash`, and **discards the
  32 bytes without storing, logging or returning them**. Nothing in the system retains a value that
  verifies against that hash, and nothing can produce one.
- **The bytes are drawn per row**, not once at startup, and this is **not** `P-ACC-03`'s process-wide
  dummy hash. One shared unusable hash written into every no-password account would make those rows
  byte-identical in that column, which tells anyone who can read the table which accounts have never
  set a password. Per-row randomness costs one bcrypt call at account creation and removes the signal.
- `password_version` starts at `1`, exactly as for a registered customer, so `P-ACC-05`'s `pv` claim
  needs no special case. The reset that gives the manager their first password takes it to `2`
  (`P-ACC-08`), which is correct: there were no sessions to revoke and revoking none is harmless.
- `last_signed_in_at` stays null until that reset completes, which is what `E6 SCR-ADM-06` renders as
  "Has not signed in yet".

**`P-ACC-03`'s timing equalisation is unchanged by this, and that is the reason it is specified here
rather than left to the handler.** A sign-in attempt against such an account takes the **known-email**
branch: the row is found, **exactly one** bcrypt verification runs — against the sentinel hash — it
fails, and the response is `401 CREDENTIALS_INVALID` with `P-ACC-02` rows 1 and 2's words. There is no
third branch and no early return, so `P-ACC-03`'s acceptance criterion — the verify function is
invoked exactly once on every branch — covers this case without being extended.

**No message anywhere says that an account has not set a password yet.** Such a message would identify
which addresses are staff accounts, on the one endpoint an attacker probes at volume.

**A nullable `password_hash` is refused, and this is the reason.** Null would have to be tested for
before the verification, and a test before the verification is an early return — which is exactly the
regression `P-ACC-03`'s counter assertion exists to catch. The security property is preserved by
having nothing to branch on, not by remembering not to branch.

**No endpoint discloses whether a password is usable.** No response field carries it, and
`E6 EP-ADM-22`'s `has_signed_in` is derived from `last_signed_in_at` and never from the hash — they are
different facts, and an account can have signed in and later be given a new password.

**Password reset works for such an account with no special case** (`P-ACC-07`, `P-ACC-08`). The row
exists, so the link is sent; the reset writes a real hash over the sentinel. That is the only route by
which a manager account ever becomes usable, and it is the route `E6 P-ADM-17` depends on.

**`[JUDGMENT CALL]` — the sentinel construction is the build session's under Art III.9.** No source
says what a passwordless account's hash column holds. The two alternatives — a nullable column, and one
fixed sentinel string shared by every such row — are rejected above on the same ground: each creates
something a code path or a database reader can branch on.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Email field empty or whitespace only | `422` `VALIDATION_FAILED` | "Enter an email address." |
| 2 | Email is not a valid shape | `422` `VALIDATION_FAILED` | "That is not a valid email address." |
| 3 | Email longer than 254 characters | `422` `VALIDATION_FAILED` | "That email address is too long. The limit is 254 characters." |
| 4 | Password shorter than `PASSWORD_MIN_LENGTH` characters | `422` `VALIDATION_FAILED` | "Your password must be at least 12 characters. It does not have to contain numbers or symbols." |
| 5 | Password longer than 72 bytes | `422` `VALIDATION_FAILED` | "Your password is too long. The limit is 72 bytes and yours is 84. Most characters count as one byte; accented and non-Latin characters count as two, three or four." |
| 6 | Password field empty | `422` `VALIDATION_FAILED` | "Enter a password." |
| 7 | The email address already has an account | `409` `EMAIL_ALREADY_REGISTERED` | "An account already exists for that email address. Sign in instead, or reset the password if you have forgotten it." |
| 8 | More than 5 registrations from this IP in an hour | `429` `RATE_LIMITED` with `Retry-After` | "Too many accounts have been created from this connection. Try again in 12 minutes." |
| 9 | Redis unreachable | `503` `DEPENDENCY_UNAVAILABLE` | "Registration is unavailable right now. Browsing still works. Try again shortly." |
| 10 | Anything unhandled | `500` `INTERNAL_ERROR` | "Something went wrong and your account was not created. If you need help, quote `a1b2c3d4`." |

Row 7 discloses that an address has an account. That is unavoidable without an email-verification gate
and `P-ACC-04` rules that out for v1. **It is recorded as an accepted weakness, not solved**: the
sign-in and password-reset paths, which an attacker would probe at volume, do not disclose it
(`P-ACC-03`, `P-ACC-07`), and registration is limited to 5 per hour per IP (`FR-ADR-058`), which makes
enumeration through this route slow enough to be uninteresting. The alternative — returning `201` for
an address that already exists — would mean a customer who mistyped nothing and simply forgot they had
registered is told their account was created when it was not.

**Server-side validation.** Client-side validation exists to shorten the round trip and is never the
enforcement point (`SRC-002 §7.1` applies the same principle to configuration; the rule here is
`SRC-001 §7.4`).

| Field | Type | Bound | On failure |
|---|---|---|---|
| `email` | string | 3..254 characters after trimming. Exactly one `@`; a non-empty local part; a domain part containing at least one `.` and no whitespace | row 1, 2 or 3 |
| `password` | string | at least `PASSWORD_MIN_LENGTH` characters, default `12`; at most 72 bytes when encoded as UTF-8. **Never trimmed** — a leading or trailing space is part of the password | row 4, 5 or 6 |

**Every published string below that quotes `12` interpolates `PASSWORD_MIN_LENGTH`, and a literal is
a defect.** The strings are printed at the default, so they read `12` and do not change — but the
number in them is rendered from the configuration value, exactly as `P-ACC-07` already rules for the
reset lifetime ("a literal `30` in any of those places is a defect"). The strings that carry it are
`P-ACC-01` exception 4, `P-ACC-03` exception 1, `P-ACC-08` exception 5, and the password help and
password-too-short rows in `SCR-ACC-01` and `SCR-ACC-03`'s copy tables. A deployment that raises
`PASSWORD_MIN_LENGTH` to 14 and leaves a literal in the copy tells the customer a rule the server does
not enforce, and they will type twelve characters and be refused by a message that says twelve is
enough.

**`72` is not configuration and is deliberately a literal.** It is bcrypt's truncation point, a
property of the algorithm rather than a setting (`GOTCHAS.md`, `FR-ADR-050`), and there is no variable
behind it to render. The distinction is stated because "interpolate every number" applied blindly
would invent a `PASSWORD_MAX_BYTES` that nothing may set.

**The `84` in that message is `details.byte_length`, interpolated and never typed** — it is the
submitted password's actual byte count, so the customer is told their own number and not the example's
(`FR-ADR-052`; the same rule `PASSWORD_MIN_LENGTH` carries above). The published strings show the
worked example's value because that is what a rendering looks like.

**No further email normalisation is performed.** Dots are not stripped from a Gmail local part, plus
addressing is not collapsed, and no character is mapped to another. `FR-ADR-015` states the principle
for the booking reference and it holds here: a system that guesses what the customer meant is a system
that resolves one person's input to another person's record.

**Worked example — the 72-byte limit, which is a byte limit and not a character limit.**

Rule: reject when `len(password.encode("utf-8")) > 72`.

- Input A: `correct horse battery` — 21 characters, 21 bytes. **Accepted** (21 ≥ 12 minimum, 21 ≤ 72).
- Input B: `पासवर्डपासवर्डपासवर्डपासवर्ड` — the word `पासवर्ड` four times. That word is **7 code
  points** (`प ा स व र ् ड` — the vowel sign `ा` and the virama `्` are each their own code point),
  so the input is **28 code points**. Each encodes to 3 bytes in UTF-8, so the password is
  `28 x 3 =` **84 bytes**. **Rejected** by row 5, with `details.byte_length = 84`, even though it is
  only 28 characters and looks far shorter than input A's limit would suggest.

  *(This example previously read "25 Devanagari code points … 75 bytes". The two halves were
  internally consistent — `25 x 3 = 75` — and neither matched the literal string beside them, which is
  28 code points and 84 bytes. **The literal was right and the count was wrong**, so the count is
  corrected rather than the string: the literal is what `S1.5` has a test transcribe, and the point the
  example makes is stronger at 84 anyway. The undercount came from reading the rendered glyphs — the
  word displays as four clusters and is seven code points, which is exactly the trap the example
  exists to teach.)*
- Input C: `abcdefghijk` — 11 characters, 11 bytes. **Rejected** by row 4.

This example exists because bcrypt silently truncates at 72 bytes (`GOTCHAS.md`, `FR-ADR-050`). Without
the explicit check, input B and any other password sharing its first 72 bytes would authenticate the
same account and nobody would ever see it happen.

---

### `P-ACC-02` · Sign in and receive a session · `RULED`
`[SRC: SRC-001 §5.4.1 · SRC-002 §4.8 · FR-ADR-050 · FR-ADR-009]`
`[BRD: R-ACC-01]`

**Behaviour.** A visitor supplies an email address and a password and receives a session cookie
carrying their identity and role. Sign-in and registration are one screen with two tabs
(`FR-ADR-046`), so this specification and `P-ACC-01` share a surface but not an endpoint.

**Who may do it.** Anyone. The endpoint is `public`.

**Preconditions.** Redis is reachable (the limiter fails closed). Postgres is reachable.

**Happy path.**

1. The server trims the email address and lowercases it for lookup.
2. The server loads the user row by `lower(email)`.
3. **Whether or not a row was found, the server runs one bcrypt verification** — against the found
   row's hash, or against a fixed dummy hash computed once at startup (`P-ACC-03`).
4. On a match, the server writes `last_signed_in_at` on that user row from the injected clock
   (`FR-ADR-018`), as a single statement:
   `UPDATE users SET last_signed_in_at = :now WHERE id = :id`.
5. On a match, the server issues the session cookie of `P-ACC-05` and returns `200` with the caller's
   id, email and role.
6. On no match, the server returns `401 CREDENTIALS_INVALID`. The response is byte-identical whether
   the email was unknown or the password was wrong. **`last_signed_in_at` is not written on a failed
   attempt** — the column records sign-ins, not attempts, and a failed attempt is not one.

**Step 4 is a write on the sign-in path, and it is stated as one rather than left to be discovered.**
Sign-in has no other write, so this is its own statement in its own implicit transaction: there is
nothing for it to be atomic with. It is **not** an audit row — signing in is not a privileged write
(`E6 P-ADM-19` audits changes an admin makes, and explicitly does not audit reads or ordinary customer
activity), so nothing is inserted into `audit_log` here. The consequences, both stated: every
successful sign-in costs one indexed single-row update, and a customer who signs in on two devices
leaves only the later instant behind, because the column holds the **most recent** sign-in and not a
history of them. A history is not asked for by any source and is not built.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Email unknown | `401` `CREDENTIALS_INVALID` | "That email address and password do not match an account." |
| 2 | Email known, password wrong | `401` `CREDENTIALS_INVALID` | "That email address and password do not match an account." |
| 3 | Either field missing or empty | `422` `VALIDATION_FAILED` | "Enter your email address and password." |
| 4 | More than 10 attempts against this email address in 15 minutes | `429` `RATE_LIMITED` with `Retry-After` | "Too many sign-in attempts for that email address. Try again in 90 seconds." |
| 5 | More than 30 attempts from this IP in 15 minutes | `429` `RATE_LIMITED` with `Retry-After` | "Too many sign-in attempts from this connection. Try again in 30 seconds." |
| 6 | Redis unreachable | `503` `DEPENDENCY_UNAVAILABLE` | "Sign-in is unavailable right now. Browsing still works. Try again shortly." |
| 7 | Anything unhandled | `500` `INTERNAL_ERROR` | "Something went wrong and you were not signed in. If you need help, quote `a1b2c3d4`." |

Rows 1 and 2 are deliberately the same words, the same code and the same status. **This is the one
place in the product where two different situations are given one message on purpose**, and the
reason is that distinguishing them turns the endpoint into a directory of who has an account.

**There is no account lockout.** No frozen source rules one, and inventing a lockout threshold would
be inventing a policy. The token bucket is a throttle, not a lock: it refills continuously, so a
customer who trips row 4 waits and proceeds. **The consequence, stated because it is real:** the
per-email bucket is keyed on a value the caller submits, so a third party who knows a customer's email
address can keep that customer's bucket empty and slow their sign-in to one attempt every 90 seconds.
They cannot lock the account out and they cannot sign in. The per-IP bucket limits how cheaply they can
do it. This is accepted rather than solved, because the alternative — keying only on IP — is the
configuration `GOTCHAS.md` records as a limiter that protects nothing behind a load balancer.

**Server-side validation.** As `P-ACC-01`'s table for shape, with one difference: **the password is not
length-validated on sign-in.** A stored account may predate a rule change, and rejecting a 10-character
password at sign-in with "too short" would tell the caller that the password rules changed rather than
that the credentials are wrong. Any password that fails to verify produces row 1/2.

---

### `P-ACC-03` · Password rules, hashing, and a comparison that runs for an unknown email · `RULED`
`[SRC: SRC-001 §7.4 · SRC-002 §4.8 · SRC-002 §5.4.1 · FR-ADR-050]`
`[BRD: R-ACC-01 · R-QLY-06]`

**Behaviour.** Passwords have a length floor and a byte ceiling and no composition rule. They are
hashed with bcrypt, off the event loop. The verification runs on every sign-in attempt, including
those for an email address that has no account.

**Who may do it.** Not applicable — this is a rule the server applies, not an action anyone performs.

**Preconditions.** None.

**The rules, stated before they are broken.** All three appear as help text under the password field
at the moment it is focused, not as an error after it is submitted (`COMPONENTS.md §11`):

1. **Minimum `PASSWORD_MIN_LENGTH` characters, default `12`.** Length is what resists guessing. Every customer-facing string quoting the figure renders it from the variable (`P-ACC-01`).
2. **No required mixture of character classes.** No mandatory uppercase, digit or symbol. Composition
   rules push people toward predictable substitutions and toward writing the password down
   (`FR-ADR-050`).
3. **Maximum 72 bytes**, with its own message naming the byte count, because bcrypt truncates silently
   at 72 bytes and a truncation nobody sees means two different long passwords authenticate the same
   account.

**Hashing.**

- Algorithm bcrypt. `BCRYPT_COST` is configuration with a default of `12`
  (`FR-ADR-053` carries the configuration rule). **`[JUDGMENT CALL]` — the cost factor is the build
  session's under Art III.9.** Twelve is chosen to sit near the 300 ms figure `GOTCHAS.md` records, and
  it is a value Phase 7's load test replaces with a measured one. It is not a ruled number and it never
  hardens into one.
- **The hash runs in a thread**, via `asyncio.to_thread`. Roughly 300 ms of CPU inside an `async def`
  stalls every other request on that worker, and on a host with roughly 1 GB of memory and one API
  container a handful of simultaneous sign-ins is a visible outage (`SRC-002 §5.4.1`, `GOTCHAS.md`).
- **The thread pool size is `BCRYPT_THREAD_POOL_SIZE`, default `2`.** It was previously called "a
  named configuration value" and given no name, which `S7.9` rules is a defect in the section that
  introduces the setting. Two is the `t3.micro`'s vCPU count: bcrypt at cost 12 is **CPU-bound**, so a
  pool larger than the core count queues rather than parallelises while still paying for the threads,
  and the pool competes with the API's roughly 200 MB budget (`SRC-002 §5.4.1`).
- **The hashing wait is `BCRYPT_HASH_TIMEOUT_MS`, default `5000`** — five seconds. A request that has
  waited that long for a thread gives up rather than holding a connection behind a queue that is not
  draining, and that is the timeout exception 3 fires on. Without a name it fired on nothing.
  **The unit is milliseconds and the name carries it**, matching `PAYMENT_SIMULATED_DELAY_MS` and the
  product's other `_MS` settings; `S7.9` is the declared owner of the configuration inventory and this
  row adopts its name rather than publishing a second one. The arithmetic below reasons in seconds,
  because a 300 ms hash against a five-second budget is legible and a 300 ms hash against a
  five-thousand-millisecond budget is not — **the variable is milliseconds, the reasoning is seconds,
  and the conversion is written out so neither is inferred.**
- **The observable consequence, which is why neither may stay implicit: `BCRYPT_THREAD_POOL_SIZE` is
  the concurrency at which sign-in starts returning `503`.** At the default, roughly two sign-ins are
  hashing at once and the rest queue; at about 300 ms each (`GOTCHAS.md`, `[UNPROVEN HERE]`), a queue
  longer than `2 × (BCRYPT_HASH_TIMEOUT_MS / 1000) / 0.3` ≈ **33 waiting requests** starts timing the
  oldest out. That is a capacity number an operator has to be able to find, and it is not derivable
  from a document that says only "a named configuration value".

  ```
  BCRYPT_THREAD_POOL_SIZE = 2, BCRYPT_HASH_TIMEOUT_MS = 5000, ~300 ms per hash
    the timeout in seconds        = 5000 / 1000  = 5
    hashes completed per second   = 2 / 0.3      = 6.7
    requests servable inside 5 s  = 6.7 x 5      = 33
    the 34th concurrent sign-in   -> waits past the timeout -> 503 DEPENDENCY_UNAVAILABLE
  ```

  **Both values are `ASSUMED`** — no frozen source, ruling or `APPROVED` record names either — and
  both are replaced by Phase 7's load test with measured figures. The arithmetic above is
  *(reasoned from the configured values and a carried 300 ms estimate, not observed)*, and the 300 ms
  is itself `[UNPROVEN HERE]`. **`S7.9` carries both rows** — their defaults, bounds and what happens
  when they are absent — and this row does not restate them.
- **Raising the pool is not free and is the wrong first move.** More threads on two vCPUs make every
  hash slower rather than more numerous, and each thread's stack competes with the API's memory
  budget. The lever that actually moves this number is `BCRYPT_COST`, which is the thing Phase 7
  measures.

**The comparison runs for an unknown email, and this is the requirement, not an implementation note.**

- A dummy bcrypt hash is computed once at process start, from a value that is not a valid password.
- On a sign-in attempt for an unknown address, the server verifies the submitted password against that
  dummy hash and discards the result.
- **Observable consequence, stated as the requirement:** the response to a sign-in attempt for an
  unknown email address performs the same amount of work as one for a known email address with the
  wrong password, so an attacker cannot separate the two by measuring how long the server took.

**There are exactly two branches, and an account with no usable password is not a third one.** A
manager account created by `E6 P-ADM-17` carries a real but unusable bcrypt hash rather than a null —
the construction is specified in `P-ACC-01` — so a sign-in attempt against it is an ordinary
known-email, wrong-password attempt: one verification, one failure, one `CREDENTIALS_INVALID`. **This
row's guarantee therefore needs no exception written into it**, and the acceptance criterion below
needs no third case.

**How that is tested, and how it is not.** The acceptance criterion asserts that the bcrypt
verification function is invoked **exactly once** on both branches — the unknown-email branch and the
wrong-password branch — using a counter around the verify call. **It does not measure elapsed time.** A
timing assertion would be flaky under any load, and Art IX.5 makes a test that reads the wall clock a
defect. The structural assertion is the stronger one anyway: it fails the moment someone adds an early
return for an unknown address, which is the actual regression being guarded against.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Password below `PASSWORD_MIN_LENGTH` characters, on registration or reset | `422` `VALIDATION_FAILED` | "Your password must be at least 12 characters. It does not have to contain numbers or symbols." |
| 2 | Password above 72 bytes, on registration or reset | `422` `VALIDATION_FAILED` | "Your password is too long. The limit is 72 bytes and yours is 84. Most characters count as one byte; accented and non-Latin characters count as two, three or four." |
| 3 | Every thread in `BCRYPT_THREAD_POOL_SIZE` is busy and the request waits past `BCRYPT_HASH_TIMEOUT_MS` | `503` `DEPENDENCY_UNAVAILABLE`, logged at `WARNING` with the wait and the pool size, because this is a capacity signal and not a fault | "Sign-in is unavailable right now. Browsing still works. Try again shortly." |

**Server-side validation.** The password is validated on **registration** (`P-ACC-01`) and on **reset
completion** (`P-ACC-08`). It is **not** validated on sign-in (`P-ACC-02`).

**Worked example — where the byte count comes from.** See `P-ACC-01`'s worked example. The value in
`details.byte_length` is `len(password.encode("utf-8"))`, computed before hashing, and it is the number
the message quotes.

---

### `P-ACC-04` · No email-verification gate in v1 — an accepted weakness · `RULED`
`[SRC: SRC-003 OPEN-BOOK-02 · SRC-003 OPEN-EMAIL-01 · SRC-001 §3.1 · FR-ADR-050 · FR-ADR-048 · FR-ADR-049]`
`[BRD: R-ACC-01 · R-ACC-03]`

**Behaviour.** A customer can register and book immediately. No confirmation link is sent, no address
is verified, and no part of the product is gated on verification.

**Who may do it.** Not applicable — this is the absence of a step.

**This is recorded as an accepted weakness, not as a design preference.** The receipt is the customer's
only proof of purchase and their only way into the hall (`SRC-003 OPEN-TICKET-01`,
`SRC-003 OPEN-EMAIL-01`), and it goes to the account's address and nowhere else (`FR-ADR-014`). **An
unverified address is a plausible route to a customer who has paid and cannot enter.** That is the same
failure `OPEN-EMAILFAIL-01` describes, reached by a different road, and `OPEN-EMAILFAIL-01` is an open
row reserved to the client (`FR-ADR-049`).

**The larger consequence, recorded here because this row previously stopped at the receipt.** A
misdelivered receipt is not the worst outcome of an address the registrant does not control.
**Whoever controls the address controls the account**, deterministically, at a time of their choosing,
and by mechanisms this document already specifies:

1. `P-ACC-07` sends a single-use reset link **to the account's address**. The endpoint is public,
   anyone may ask for one, and the response is identical whether or not the address has an account.
2. `P-ACC-08` completes that reset, writes a new `password_hash`, increments `password_version` and
   issues a fresh session to whoever followed the link.
3. `P-ACC-05`'s `pv` claim then **immediately stops every existing session for that account from
   being accepted** — including the registrant's, on their next request.
4. `P-ACC-12` scopes `/api/me/` to the caller, and the caller is now the address's owner: every
   booking the account owns and every booking reference on it (`FR-ADR-015`, the reference being the
   only thing that gets a person into a hall).

**The registrant has no route back.** The reset goes to the address; the address is not theirs; the
address is taken permanently on `lower(email)` and nothing in this system is deleted (`FR-ADR-012`);
the bookings belong to the first user row and not to any second account they register (`P-ACC-09`);
and there is no support desk, because the client is the sole operator (`SRC-001 §8.2`).

**Every step in that chain is correct on its own terms and none of them is the defect.** The reset
must reach the account's address, or a forgotten password against a permanently-taken address is an
unrecoverable account (`P-ACC-07`). The session must die on a password change, or a customer who
resets precisely because someone else has their password leaves that person signed in for the whole
token lifetime (`P-ACC-05`). **What was missing was the sentence saying where they lead when the
address was never the registrant's.** It is written here rather than solved: `FR-ADR-050` is
`APPROVED` and immutable and rules the verification gate out for v1, and reason 3 below names this
exact situation and then stopped at the receipt. **This is an enlargement of an accepted weakness
already on the record, not a new decision, and it changes no behaviour in this document.**

**Why the gate is nevertheless not built** (`FR-ADR-050`, which is `APPROVED` and immutable):

1. It inserts a second interruption into the exact flow `SC-1`'s two minutes and `FR-ADR-046` are
   protecting.
2. It makes registration depend on SES being healthy, so an SES outage would stop new customers
   registering as well as stopping receipts.
3. It does not catch the most common bad address, which is a valid and deliverable address belonging to
   somebody else.

**What is built instead, and none of it is a guarantee:**

- The address is validated for shape and normalised only by trimming (`P-ACC-01`).
- The address is displayed back to the customer on the confirmation screen — "A receipt is on its way
  to `<address>`" (`FR-ADR-048`) — so a typo is visible at the moment it costs something. **It makes
  the typo visible; it does not make it fixable** — the block below states why, because a mitigation
  read without that sentence promises a recourse the product does not have.
- The booking reference is on the confirmation screen and in the bookings list independently of the
  email (`P-ACC-10`, `FR-ADR-048`).
- The booking's receipt dispatch record holds its state and its attempts (`FR-ADR-031`, `FR-ADR-032`),
  so the failure is recorded even though nothing watches it.

**No endpoint changes an account's email address, so the first mitigation is visibility without a
remedy.** `S3.8`'s route inventory is generated from the `endpoint` blocks and contains no route that
patches an account: the address is written once, by `P-ACC-01`, and is never written again by
anything. A customer who reads the confirmation screen and sees the wrong address can therefore do
**nothing about it**, and the mitigation was stated as though they could.

What is actually available to them, in full:

| What they can do | What it does not do |
|---|---|
| Register a second account at the correct address (`P-ACC-01`) | **It does not move the booking.** `P-ACC-09` binds the booking to the first user row and no endpoint reassigns one |
| Read the reference from the confirmation screen and from `SCR-ACC-04`, neither of which depends on the email (`FR-ADR-048`) | It does not stop the receipt reaching the wrong address, and it needs the first account's session — which the address's owner can end at any moment, by the chain in the block above |
| Nothing else. The mistyped address is taken permanently on `lower(email)` (`FR-ADR-012`) | — |

**An address-change endpoint is not specified here and this row does not invent one.** No frozen
source, ruling or `APPROVED` ADR asks for one; `SRC-001 §6.6` means adding one later is a migration
rather than a redesign; and adding a v1 endpoint to close a documentation defect would be a scope
change this specification may not make. **The gap stays a gap and is written down as one.**

**What may not be written here.** **No wording is specified for a customer whose receipt has
definitively failed, and no policy is stated about money already taken.** `OPEN-EMAILFAIL-01` is
reserved to the client and `FR-ADR-049` decides nothing. A plausible sentence written into this
specification would close a question nobody answered.

**Exception paths.** None. There is no step to fail.

**Server-side validation.** None beyond `P-ACC-01`'s email shape check.

---

### `P-ACC-05` · The session cookie, and signing out · `RULED`
`[SRC: SRC-002 §4.8 · SRC-002 §7.3 · SRC-003 OPEN-TLS-01 · FR-ADR-050 · FR-ADR-053 · FR-ADR-069 · FR-ADR-009]`
`[BRD: R-ACC-01]`

**Behaviour.** A session is a JSON Web Token in an `HttpOnly` cookie. The server keeps no session
table, no session store and no server-side session state, because containers are stateless
(`SRC-002 §7.3`).

**Who may do it.** **Sign-out is `public`, not `authenticated`.** It is mounted on the public router
and anyone may call it, with or without a session — as `EP-ACC-03` below declares and as `S3.8`'s
generated route inventory lists it. Every other endpoint reads the cookie through the router's
authorisation dependency (`P-ACC-12`).

**This row previously said `authenticated`, and that sentence was the outlier rather than the rule.**
Its own exception row 6 says sign-out with no session returns `204` and is not an error; `EP-ACC-03`
declares `auth: public`; `S3.8` is generated from that block and lists the endpoint under *Public —
no session required*. Three artefacts agreed and one sentence did not, and `S1.2.1` case 8 makes a
declared owner that states one thing two ways a defect in that row. **The reason sign-out is public
is exception row 6's reason**: the cookie is `HttpOnly`, so a client holding an expired or malformed
one **cannot clear it itself**, and a `401` here would leave that cookie in the browser with nothing
able to remove it. `E8 SCR-XCT-05` depends on this directly — its sign-out control must not be
blockable by a failed request, and it is the only sign-out control in the product.

**Where the token lives.**

| Property | Value | Why |
|---|---|---|
| Transport | a cookie named `fr_session` | not `localStorage`: a script on the page can read `localStorage` and cannot read an `HttpOnly` cookie (`FR-ADR-050`) |
| `HttpOnly` | always `true` | as above |
| `SameSite` | `Lax` | the customer arrives from the seat map on the same site; `Strict` would drop the cookie on any cross-site return and `None` would require `Secure` |
| `Secure` | from `COOKIE_SECURE`, a **required variable with no default** (`FR-ADR-053`) | `OPEN-TLS-01` is `DEFERRED`. **It is off in the deployed environment until that row closes.** Setting it without TLS would make the browser never send the cookie and the application would appear to lose every session (`FR-ADR-069`) |
| `Max-Age` | `SESSION_TTL_SECONDS` (43200). **Set explicitly.** A cookie with no `Max-Age` is a session cookie that dies when the browser closes, which would defeat this row's own reason for twelve hours — a customer who booked in the morning and reaches the door in the evening. The cookie's lifetime and the JWT's `exp` are set from the same value, so neither can outlive the other |
| `Path` | `/` | |
| Signing | HS256 with `JWT_SECRET`, a required variable with no default (`FR-ADR-053`) | a default signing secret is a forged session for anyone who reads the source |

**`OPEN-TLS-01` is not decided here and nothing in this specification decides it.** The deployed
environment is never called production (`FR-ADR-069`, Art VIII.14).

**Claims in the token.** `sub` (the user id), `role`, `pv` (the password version, see below), `iat`,
`exp`. **Nothing else.** No email address, no name — a JWT is base64, not encryption, and anyone who
obtains it can read every claim.

**The password version is what makes a session revocable.** The user row carries
`password_version`, an integer starting at 1 and incremented on every password change. The
authorisation dependency loads the user row by primary key on every authenticated request and rejects
the token if `pv` does not match the row. **`[JUDGMENT CALL]` — the build session's under Art III.9.**
The consequences, both stated:

- Completing a password reset immediately stops every existing session for that account from being
  accepted. Without this, a customer who resets their password because they believe someone else has
  it would leave that person signed in for the whole token lifetime.
- It costs one primary-key read per authenticated request. The manager dependency already reads the
  database to resolve assigned screens (`FR-ADR-011`), so this is the same shape of cost. It also means
  a role change takes effect on the next request rather than at the next sign-in.

**Signing out.**

1. The client calls the sign-out endpoint.
2. The server responds `204` with `Set-Cookie: fr_session=; Max-Age=0` and the same attributes the
   cookie was issued with, because a cookie is only cleared by a matching one.
3. The client discards any in-memory state and returns the customer to the movie listing.

**Sign-out clears the browser's copy. It does not revoke the token.** A token already copied out of the
browser stays valid until `exp` or until the password changes. This is a real property of a stateless
JWT and it is stated rather than implied. The mitigations are that `HttpOnly` stops a script taking a
copy, and that a password change revokes it. **Over plain HTTP the network can take a copy, which is
the largest single reason `OPEN-TLS-01` matters** (`FR-ADR-069`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No cookie on an authenticated endpoint | `401` `AUTH_REQUIRED` | "Sign in to continue." |
| 2 | Cookie present, signature invalid or malformed | `401` `AUTH_REQUIRED` | "Sign in to continue." |
| 3 | Cookie present, `exp` in the past | `401` `AUTH_REQUIRED` | "Your session has ended. Sign in to continue." |
| 4 | Cookie valid, `pv` does not match the user row | `401` `AUTH_REQUIRED` | "Your session has ended because the password was changed. Sign in to continue." |
| 5 | Cookie valid, the user row does not exist | `401` `AUTH_REQUIRED` | "Sign in to continue." |
| 6 | Sign-out called with no session | `204`, no body | nothing — signing out when not signed in is not an error |

**On a `401` mid-flow the customer is returned to sign-in with their context preserved**, using the
same `sessionStorage` mechanism as `P-ACC-13` (`FR-ADR-050`).

**Server-side validation.** The token is validated for signature, `exp`, the presence of every required
claim, and `pv` against the user row. A token missing any claim is rejected — an absent claim is never
treated as a default.

---

### `P-ACC-06` · Session lifetime, and the deliberate absence of a refresh token · `ASSUMED`
`[SRC: SRC-002 §4.8 · SRC-002 §7.3 · FR-ADR-050 · FR-ADR-053]`
`[BRD: R-ACC-01]`

**Behaviour.** The session token has a fixed absolute lifetime and there is no refresh token, no
sliding expiry and no silent renewal. When it expires the customer signs in again.

**Status is `ASSUMED` and it means what it says.** No frozen source and no `APPROVED` ADR states a
session lifetime. `FR-ADR-050` rules the cookie's shape and says nothing about how long it lasts. The
number below is the build session's inference, it is configuration, and **it never hardens into a
constraint.** It is flagged here so the next session does not read it as ruled.

| Value | Setting | Default |
|---|---|---|
| Session lifetime | `SESSION_TTL_SECONDS` | `43200` — twelve hours |

**The unit is seconds and the name carries it.** Every duration in this product's configuration is
named `_SECONDS` and holds an integer number of seconds, so no reader has to work out which unit a
given value is in. **The lifetime is stated once, in the table above, and nowhere else in this
document** — a second statement of it is how one figure becomes two.

**Why 12 hours and not something shorter or longer.** A customer's whole interaction with this product
is a few minutes long, so a short lifetime costs almost nothing at the moment of use. Twelve hours
covers "I booked this morning and I am at the door this evening", which is the whole of a same-day
booking, and it does not cover "I booked yesterday", which is the case a shared or stolen machine makes
dangerous. **The shorter of the two candidate lifetimes was taken deliberately.** Until `OPEN-TLS-01`
closes, `COOKIE_SECURE` is off in the deployed environment and the session cookie crosses the network
in the clear (`P-ACC-05`, `FR-ADR-069`), so every additional hour the token stays valid is an
additional hour in which anyone who copied it off the network can replay it. Adopting the stricter of
two options needs no signature (Art III.10).

**The cost is stated rather than hidden.** A customer who booked more than 12 hours before the film
signs in again to read their reference on `SCR-ACC-04`. The mitigation is that the reference does not
depend on a session at all: it is in the receipt email (`FR-ADR-048`), which is the customer's proof of
purchase and their way into the hall.

**Why there is no refresh token.** A refresh token is a second credential with a longer life, which
needs a store to revoke it, which is server-side session state that `SRC-002 §7.3` forbids and that
would need a table nothing prunes (`FR-ADR-012`). The whole mechanism exists to make short access
tokens usable; with one token and a 12-hour life there is nothing for it to do. **The cost is stated:
a customer whose session expires mid-flow is interrupted.** `P-ACC-05` returns them to sign-in with
their context preserved and `P-ACC-13` restores their seat selection, which is the mitigation.

**Exception paths.** As `P-ACC-05` row 3.

**Server-side validation.** `SESSION_TTL_SECONDS` is validated at startup to be a positive integer
number of seconds. A value of zero would make every session expire on issue, which looks exactly like a
broken sign-in.

**Worked example — when a session ends.**

- Rule: `exp = iat + SESSION_TTL_SECONDS`, both in seconds since the epoch.
- Inputs: a customer signs in at `2026-08-14T10:00:00Z` (`2026-08-14 15:30 IST`);
  `SESSION_TTL_SECONDS = 43200`, which is `43200 / 3600 = 12` hours.
- `iat = 2026-08-14T10:00:00Z`, `exp = 2026-08-14T10:00:00Z + 43200 s = 2026-08-14T22:00:00Z`
  (`2026-08-15 03:30 IST`).
- A request at `2026-08-14T21:59:00Z` is accepted. A request at `2026-08-14T22:00:01Z` is rejected with
  `401 AUTH_REQUIRED` and the message in `P-ACC-05` row 3.
- The comparison is against the injected clock, never the container's local time (`FR-ADR-018`).

---

### `P-ACC-07` · Request a password reset · `RULED`
`[SRC: SRC-001 §5.4.1 · SRC-003 OPEN-OPS-02 · FR-ADR-050 · FR-ADR-012 · FR-ADR-031 · FR-ADR-060]`
`[BRD: R-ACC-04]`

**Behaviour.** A visitor supplies an email address. If it has an account, a single-use reset link is
emailed to it. **The response is identical whether or not the address has an account.**

**Who may do it.** Anyone. The endpoint is `public`.

**Why this must exist at all, stated because it is the reason the requirement is not optional.**
Nothing in this system is ever deleted (`SRC-003 OPEN-OPS-02`, `FR-ADR-012`), so a registered email
address is taken permanently. A customer who forgets their password cannot delete the account, cannot
register again with the same address, and cannot reach any of the bookings that account owns — and
those bookings are the only record of what they paid for and the only place the reference lives if the
receipt email is gone (`FR-ADR-048`). There is no support desk: the client is the sole operator
(`SRC-001 §8.2`). **A reset flow that works without help from anyone is therefore the only route back
into an account, and its absence would make a forgotten password an unrecoverable loss of every
booking the customer ever made.**

**Preconditions.** Redis is reachable. Postgres is reachable.

**Happy path.**

1. The server trims and lowercases the submitted address and looks up the user row.
2. **If no row exists**, the server does nothing further and returns `202` with the body and the words
   in the copy table below.
3. **If a row exists**, the server marks every outstanding unused reset token for that user as used, so
   at most one live token exists per account at a time.
4. The server generates a token: 32 bytes from a cryptographically secure source, rendered URL-safe
   (43 characters). The token itself is never stored.
5. The server inserts a `password_reset_token` row holding `user_id`, `token_sha256` (the SHA-256 of
   the token, hex), `expires_at`, `used_at` (null), `email_claimed_at` (null), `email_sent_at` (null),
   `created_at`. **Only the hash is stored**, so somebody who can read the table cannot mint a session
   from it.

**The two email columns are declared here because this row creates the row, and they are read and
written only by the worker** (`E4 P-TKT-12`). They were previously used by that specification and
declared by neither, which is a column that exists in one section's SQL and in no section's schema.

| Column | Meaning | Written by |
|---|---|---|
| `email_claimed_at` | **a worker is holding this send job.** It is a claim, not a record of anything reaching a customer, and it is cleared again when a send fails | `E4 P-TKT-12`'s conditional claim, and its explicit release on an SES failure |
| `email_sent_at` | **an email went out.** Set only after SES accepts, and **never cleared by anything** | `E4 P-TKT-12` step 4 |

**They are two columns rather than one on purpose, and the reason is a lockout.** A single column
cannot say both *a worker is holding this* and *a customer received this*, and a claim mechanism built
on one column either cannot recover from a worker crash — the reset link is then never sent, silently,
on the only route back into an account whose address is taken permanently (`FR-ADR-012`) — or it
recovers by re-sending a credential that already went out. `E4 P-TKT-12` carries the full statement,
its stale branch and the worked example of the crash; this row's job is to declare the columns it
depends on. **`used_at` is a third and separate thing**: it records the customer spending the token
(`P-ACC-08`) and has nothing to do with the send.
6. The server writes the reset email to the transactional outbox in the same transaction
   (`FR-ADR-031`). The worker sends it through SES. The response does not wait for the send.
7. The server returns `202` with the same body as step 2.

**The link.** `{PUBLIC_BASE_URL}/account/reset/confirm?token=<token>`. `PUBLIC_BASE_URL` is a required
variable with no default (`FR-ADR-053`). The email states that the link works once and expires in 30
minutes, and it names the account address it was requested for.

**The email's verbatim words are `SCR-ACC-06`**, in this section. **`E4 P-TKT-12` owns the sending** —
the queue message, the single-send claim and every failure path — and enumerates what the message
carries; `SCR-ACC-06` writes those items out as strings, including the shared expiry sentence this row
requires. Neither restates the other: the words live in one place and the behaviour in the other.

| Value | Setting | Default |
|---|---|---|
| Reset token lifetime | `PASSWORD_RESET_TTL_SECONDS` | `1800` — thirty minutes |

**The unit is seconds and the name carries it**, as `P-ACC-06`'s `SESSION_TTL_SECONDS` does. The
lifetime is stated once, in the table above.

**The number in every customer-visible sentence is rendered from that value, never typed.** Each place
this document quotes "30 minutes" — the confirmation body in the exception table below, the same
sentence on `SCR-ACC-02`, the `202` body of `EP-ACC-05`, and the reset email itself — interpolates
`PASSWORD_RESET_TTL_SECONDS / 60` as a whole number of minutes into one shared string. **A literal
`30` in any of those places is a defect**, because the copy and the constant would then be free to
drift apart and a customer would be told a lifetime the server does not honour. If the configured value
is changed to something that is not a whole number of minutes, the render rounds down and the sentence
understates the lifetime, which is the safe direction: a link that still works after the sentence said
it would not is a smaller failure than one that stopped working earlier than promised.

**`[JUDGMENT CALL]` — 1800 seconds is the build session's under Art III.9.** It is long enough for an
email to arrive through a sandboxed SES identity and be read, and short enough that a link sitting in a
mailbox is not a standing credential.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Address has no account | `202`, identical body | "If that email address has an account, a reset link is on its way to it. The link works once and expires in 30 minutes." |
| 2 | Address has an account | `202`, identical body | "If that email address has an account, a reset link is on its way to it. The link works once and expires in 30 minutes." |
| 3 | Field empty or not a valid shape | `422` `VALIDATION_FAILED` | "Enter an email address." |
| 4 | More than 5 requests from this IP in an hour | `429` `RATE_LIMITED` with `Retry-After` | "Too many reset requests from this connection. Try again in 12 minutes." |
| 5 | Redis unreachable | `503` `DEPENDENCY_UNAVAILABLE` | "Password reset is unavailable right now. Try again shortly." |
| 6 | Anything unhandled | `500` `INTERNAL_ERROR` | "Something went wrong. If you need help, quote `a1b2c3d4`." |

Rows 1 and 2 are the same status, the same body and the same words, for the same reason `P-ACC-02`
rows 1 and 2 are: an endpoint that answers differently is a directory of who has an account.

**The limit of that guarantee, stated rather than claimed.** The two responses are identical in
content and status. They are **not** identical in the work done — the known-address branch performs
two additional database writes. A determined observer who can measure response latency precisely and
repeatedly may be able to separate them. **This is stated as a limitation and not claimed as a
guarantee.** Equalising it would mean inserting a discarded row for every probe of an unknown address,
into a table that is never pruned (`FR-ADR-012`), which trades a small disclosure for an unbounded one.

**Server-side validation.** `email`: string, 3..254, the same shape check as `P-ACC-01`. Nothing else
is submitted.

**Worked example — when a token stops working.**

- Rule: `expires_at = created_at + PASSWORD_RESET_TTL_SECONDS`, compared against the injected clock in
  UTC (`FR-ADR-018`).
- Inputs: the request is handled at `2026-08-14T10:00:00Z`; `PASSWORD_RESET_TTL_SECONDS = 1800`, which
  is `1800 / 60 = 30` minutes — the same 30 the customer-visible sentence renders.
- `expires_at = 2026-08-14T10:00:00Z + 1800 s = 2026-08-14T10:30:00Z`.
- A submission at `2026-08-14T10:29:59Z` against an unused token **succeeds**.
- A submission at `2026-08-14T10:30:01Z` **fails** with `400 RESET_TOKEN_INVALID`.
- A second submission of a token that succeeded at `10:29:59Z` **fails**, at any instant, because
  `used_at` is set.

---

### `P-ACC-08` · Complete a password reset · `RULED`
`[SRC: SRC-001 §5.4.1 · SRC-001 §7.4 · FR-ADR-050]`
`[BRD: R-ACC-04]`

**Behaviour.** A visitor holding a valid, unused, unexpired token supplies a new password. The password
is changed, every existing session for that account stops being accepted, and the customer is signed
in.

**Who may do it.** Anyone holding the token. The endpoint is `public` — the token is the credential.

**Preconditions.** The token exists, has not been used, and has not expired. The new password satisfies
`P-ACC-03`.

**Happy path.**

1. The server hashes the submitted token with SHA-256 and looks the row up by that hash. The submitted
   token is never logged (`FR-ADR-056` excludes credentials from logs).
2. The server validates the new password against `P-ACC-03`.
3. The server hashes the new password with bcrypt, in a thread.
4. **In one transaction**: `UPDATE password_reset_token SET used_at = :now WHERE id = :id AND used_at
   IS NULL` — and the update must report exactly one affected row, or the transaction rolls back; then
   `UPDATE users SET password_hash = :hash, password_version = password_version + 1,
   last_signed_in_at = :now`. **`last_signed_in_at` is written here too**, because step 6 signs the
   customer in and this path is the only way a manager account created by an admin ever signs in for
   the first time (`E6 P-ADM-17`). Here it is inside the existing transaction rather than its own
   statement, because a transaction is already open around the password change; on `P-ACC-02` there is
   no other write and it stands alone.
5. **The single-use guarantee is the conditional update, not a prior read.** Two simultaneous
   submissions of the same token both read `used_at IS NULL`, and exactly one of them affects a row.
   This is the same shape as the seat guard: the read cannot protect what the write must.
6. The server issues a fresh session cookie (`P-ACC-05`) carrying the **new** `pv`, and returns `200`.
   Every previously issued token for this account now fails `P-ACC-05` row 4.
7. No confirmation email is sent. Nobody asked for one and it would compete with the receipt for the
   sandboxed SES quota (`FR-ADR-060`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Token not found | `400` `RESET_TOKEN_INVALID` | "That reset link is not valid. Request a new one." |
| 2 | Token already used | `400` `RESET_TOKEN_INVALID` | "That reset link has already been used. Request a new one." |
| 3 | Token expired | `400` `RESET_TOKEN_INVALID` | "That reset link has expired. Request a new one." |
| 4 | Token missing from the request | `422` `VALIDATION_FAILED` | "That reset link is not valid. Request a new one." |
| 5 | New password below `PASSWORD_MIN_LENGTH` characters | `422` `VALIDATION_FAILED` | "Your password must be at least 12 characters. It does not have to contain numbers or symbols." |
| 6 | New password above 72 bytes | `422` `VALIDATION_FAILED` | "Your password is too long. The limit is 72 bytes and yours is 84. Most characters count as one byte; accented and non-Latin characters count as two, three or four." |
| 7 | The conditional update affects zero rows (lost the race) | `400` `RESET_TOKEN_INVALID` | "That reset link has already been used. Request a new one." |
| 8 | **The per-IP reset-confirm bucket is empty** — `RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR`, 10 per hour | `429` `RATE_LIMITED` with `Retry-After: 360` | "Too many attempts from this connection. Try again in 6 minutes." |
| 9 | Redis unreachable | `503` `DEPENDENCY_UNAVAILABLE` | "Password reset is unavailable right now. Try again shortly." |
| 10 | Anything unhandled | `500` `INTERNAL_ERROR` | "Something went wrong and your password was not changed. If you need help, quote `a1b2c3d4`." |

Rows 1, 2 and 3 carry different words and the same code, so the interface shows one screen and the
message tells the customer which of the three happened. None of them discloses whether the address had
an account, because the token is the only thing being checked.

**Row 8 was missing, and its absence was a security defect rather than an omission.** `EP-ACC-06`'s
`rate_limit` field said this endpoint was limited; its `responses` carried no `429`, its `errors`
omitted `RATE_LIMITED`, this table had no row, and no bucket table in the document had one — while row
9's `503` on Redis loss only makes sense if a limiter runs at all. **On the balance of the artefacts an
engineer would have built no limiter**, and row 9 would then have been unreachable code guarding
nothing.

**This bucket is its own, and it is not the reset-request bucket.** `RATE_LIMIT_RESET_IP_PER_HOUR`
(5/hour, `P-ACC-07` row 4) covers asking for a link. Sharing one family across both would mean a
customer who requests a reset and then uses it spends two of five tokens per recovery, and four
mistyped passwords would lock them out of the only route back into an account whose address is taken
permanently (`FR-ADR-012`). **The failure mode of getting this wrong is a customer permanently unable
to recover their own account**, which is worse than the attack the bucket exists to bound.

**Ten per hour, and every request spends a token.** A legitimate customer confirms once per link, with
a few retries if the new password fails `P-ACC-03`; five links per hour is the most that can exist
(`P-ACC-07`), so ten confirms per hour is roughly two attempts per obtainable link. A request rejected
for a malformed token or a failing password **still spends its token** — otherwise an attacker gets
unmetered attempts by sending deliberately malformed ones, and the length check that saves the database
read would become the thing that defeats the limiter.

**Why this limiter exists, which is not the reason the other four exist, and the honest arithmetic.**
Every other bucket in this product protects capacity. This one guards a **credential**: the reset token
is the only value in the product that an unauthenticated request can present to take over an account,
with no second factor behind it. It must be said plainly what the limiter does and does not do:

```
the token is 32 random bytes from a CSPRNG (P-ACC-07 step 4), rendered as 43 URL-safe characters
guess space                       = 2^256
guesses inside a 30-minute life   at 10/hour/IP  = 5
                                  unlimited, at 1000 req/s = 1.8 x 10^6
either way, the probability of hitting a live token is indistinguishable from zero
```

**So the limiter is not what makes the token unguessable today, and claiming otherwise would be
inventing evidence.** What it buys is this: the entropy argument rests entirely on `P-ACC-07` step 4
continuing to draw 32 bytes from a secure source. Shortening the token, narrowing its alphabet or
swapping `secrets` for `random` is a one-line change that **no test in `08 SIT` or `09 NegativeTesting`
would catch**, because every functional test still passes against a weak token. The limiter is the only
control that survives that change, and it is what keeps a generator defect from becoming instant
account takeover. **That is why it may not be dropped later as an optimisation** — it is not paying for
itself today, and it is not supposed to be.

Two secondary effects, stated because they are real and smaller than the first: it bounds the indexed
lookup per guess, and once an attacker holds a valid token it bounds the bcrypt work at step 3, which
runs on the same `BCRYPT_THREAD_POOL_SIZE` pool sign-in uses (`P-ACC-03`) — an unlimited confirm path
is a way to saturate that pool and take sign-in down with it.

**Server-side validation.**

| Field | Type | Bound | On failure |
|---|---|---|---|
| `token` | string | exactly 43 URL-safe characters; anything else is rejected without a database read | row 4 |
| `password` | string | as `P-ACC-03` | row 5 or 6 |

**The old password is not required and is not accepted as a field.** The customer requesting a reset is
by definition the one who does not have it.

---

### `P-ACC-09` · Every booking belongs to one registered customer · `RULED`
`[SRC: SRC-001 §9.2 · SRC-003 OPEN-BOOK-02 · SRC-003 OPEN-ROLE-01 · FR-ADR-014 · FR-ADR-012 · FR-ADR-013 · FR-ADR-009]`
`[BRD: R-ACC-03]`

**Behaviour.** A booking carries a non-null foreign key to a user row. There is no anonymous order, no
guest checkout, and no placeholder user.

**The referential action is `ON DELETE RESTRICT`, and this row states it because it is the row that
owns the column.** The declaration is
`booking.user_id integer NOT NULL REFERENCES users(id) ON DELETE RESTRICT`. Deleting a user row that
any booking references **fails**: the delete is refused, the transaction that attempted it rolls
back, and nothing is destroyed.

**This is the document-wide default applied to this column, not a new decision.** `FR-ADR-012`,
`E6 P-ADM-18` and `E8 P-XCT-04` all already state it — nothing on a path that can reach a booking is
ever deleted, no foreign key on any such path uses `ON DELETE CASCADE`, and the default for every
relationship is `ON DELETE RESTRICT`. It was stated everywhere except on the column itself, which
left the Phase 2 migration with three candidates and no rule. The other two are named here so that a
reader who considers either stops at this row rather than at a test:

| Candidate | Why not |
|---|---|
| `ON DELETE CASCADE` | **It silently destroys paid bookings and is unrecoverable.** A booking is permanent — there is no customer cancellation and no refund (`FR-ADR-013`; `SRC-001 §5.4.3` is withdrawn by erratum `E-2`) — so a cascade would remove the booking, its `booking_seat` rows and their snapshotted prices (`FR-ADR-039`), and with them every takings figure computed from them (`E7`). **A cascade is a delete that happens without anyone writing the word delete**, and it is the failure this row exists to make impossible |
| `ON DELETE SET NULL` | **The column is `NOT NULL`.** It is not a policy choice that was rejected; it is a statement the database refuses to accept, and naming it costs one line and saves a developer the round trip |

**The booking's `status` and `cancelled_at` columns are not an exception to any of this.** They exist
in the schema so that adding cancellation later is not a migration over live bookings, and no v1
endpoint sets or returns either (`P-ACC-10`, `FR-ADR-013`). **Neither is a route by which a booking
leaves the table**, and `SRC-001 §6.6` keeping them there is not a reason to loosen the key.

**`P-ACC-05` exception 5 remains reachable, and that is why it stays.** `RESTRICT` refuses the delete
only for a user row that a booking references. A user row with **no** bookings can still be removed
by the same direct database action that is the only route to creating an admin account in the first
place (`E6 P-ADM-17`), which is outside the router and outside this document's endpoints. A live
session whose user row has gone is therefore a real state, not dead code, and `P-ACC-05` exception
5's `401 AUTH_REQUIRED` is the specified answer to it. **The two rows agree once the action is
stated: a booking's owner cannot be deleted, an account with no bookings can.**

**Who may do it.** A `customer` or an `admin` (admin is a superset of customer by capability,
`FR-ADR-009`). A `guest` cannot. A `manager` is read-only for privileged actions but is a person with
an account and may book as themselves — the manager restriction is on privileged writes
(`SRC-003 OPEN-OPS-03`), not on being a customer.

**Where the guest is stopped: at the hold, not at the seat map and not at payment** (`FR-ADR-014`,
`FR-ADR-046`).

- A guest may browse, open a showtime, and see the seat map. Reading availability is browsing.
- A guest may click seats. The selection is local and takes no lock.
- **The first authenticated action is the hold.** A hold consumes a scarce resource for three minutes
  and an unauthenticated actor could acquire an unbounded number of them.
- The hold endpoint is owned by the seat-locking epic. This specification states **where** the boundary
  is and **what code** is returned; it does not specify that endpoint.

**There is no separate delivery-email field on a booking.** The receipt goes to the account's address
(`FR-ADR-014`). There is no case where they differ, and a second address would be a second identity
path for the customer's only proof of purchase.

**Preconditions.** The caller holds a valid session.

**Happy path.** Not applicable — this is a constraint, and its happy path is every booking that exists.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A guest presses the primary action on the seat map | `401` `AUTH_REQUIRED` from the hold endpoint | The interface does not let this reach the server in the normal case: the action reads "Sign in to hold these seats" (`COMPONENTS.md §5`). If it does reach the server — an expired session, a direct call — the customer sees "Sign in to hold these seats." |
| 2 | A caller submits a booking for a different user's id | not possible: the owner is taken from the session, never from the request body | — |
| 3 | A `DELETE` is attempted against a user row that a booking references | the foreign key refuses it under `ON DELETE RESTRICT` and the transaction rolls back. **No application path issues it** — no endpoint deletes an account — so this can only arrive from a direct database action | — (no user-facing surface; the operator sees the constraint violation) |

**Server-side validation.** The booking's `user_id` is read from the authorisation dependency's
resolved caller. **It is never read from the request body**, and no endpoint accepts a `user_id`
field. A field that does not exist cannot be forged.

---

### `P-ACC-10` · The customer's own bookings, upcoming and past · `RULED`
`[SRC: SRC-001 §5.4.2 · SRC-003 OPEN-TICKET-01 · SRC-003 OPEN-LOCALE-01 · FR-ADR-048 · FR-ADR-015 · FR-ADR-036 · FR-ADR-018 · FR-ADR-013]`
`[BRD: R-ACC-02]`

**Behaviour.** A signed-in customer sees every booking their account owns, in two groups — upcoming and
past — each row carrying its reference, its seats, its hall, its showtime, its film and the amount
paid.

**Who may do it.** `authenticated`. Enforced once on the router as a dependency (`SRC-001 §7.4`,
Art VI.4), never per handler. The dependency resolves the caller; the query filters on that caller
(`P-ACC-12`).

**Preconditions.** A valid session.

**Happy path.**

1. The dependency resolves the caller's user id from the session.
2. The server selects bookings where `booking.user_id = caller.id`, joined to their showtime, screen
   and movie, and their booked seats.
3. Each booking is classified upcoming or past by `P-ACC-11`.
4. Each group is ordered by `P-ACC-11` and paged **independently**, by the rule below.
5. Money is returned as an **integer number of paise** and rendered at the last possible moment
   (`FR-ADR-036`). The API never returns a formatted currency string and never returns a float.

**What `page` means when no `group` is named. `page` applies to both arrays, independently.**

`group` is optional; when it is absent both groups are returned. `page` defaults to `1`, so the landing
request — no `group`, no `page` — returns the first page of upcoming **and** the first page of past.
The question that had no answer is what `page=2` with no `group` does, and it is this:

```
GET /api/me/bookings?page=2                 (no group)
  upcoming  ->  rows 21..40 of the upcoming ordering, counted against total_upcoming
  past      ->  rows 21..40 of the past ordering,     counted against total_past
```

- **The parameter is applied to each group separately**, each against its own ordering (`P-ACC-11`) and
  its own `total_`. `page_size` behaves the same way and applies to both.
- **`page` is never ignored and it is never an error when no `group` is named.** Silently discarding a
  parameter a caller sent is the failure mode that takes longest to notice: the caller sees a `200`
  full of rows and no signal that the server did something other than what was asked. A `422` was
  rejected for the same reason it is not a `422` today — nothing about the request is out of bounds.
- **The two groups have different lengths, so a page valid for one can be past the end of the other.**
  That group's array comes back **empty**, and the other's comes back full. An empty array is not an
  error and does not change the status code.

**Worked example — the different-lengths edge.** A customer has `total_upcoming = 2` and
`total_past = 37`, with the default `page_size = 20`.

| Request | `upcoming` | `past` | Status |
|---|---|---|---|
| `?page=1` (or no `page`) | 2 rows | 20 rows | `200` |
| `?page=2` | **empty** — page 2 starts at row 21 and there are 2 | 17 rows | `200` |
| `?page=3` | **empty** | **empty** — 37 rows end on page 2 | `200` |
| `?group=upcoming&page=2` | **empty** | **`[]`** — present, with `total_past` still `37` | `200` |

**Both arrays are always present, in every response, whatever `group` says.** Naming a group does not
remove the other array — it returns `[]`, with its `total_` still populated. A field that sometimes
vanishes forces every client to branch on **shape** rather than on value, and this response is read by
a screen that renders three different zero states: no bookings at all, a group that is genuinely
empty, and a page past the end of a group that has rows. A client testing `past === undefined` and one
testing `past.length === 0` draw different screens from the same response, which is exactly the class
of ambiguity `FR-ADR-052` already forbids on the error envelope.

`total_upcoming` and `total_past` are returned on every response, so a caller can always tell an empty
array that means "this group has nothing" from one that means "this group has nothing **on this
page**". `SCR-ACC-04` renders a different zero state for each, and names which. **With the array always
present, `total_` is the only thing a client ever has to test**, which is the whole benefit.

**Every field on a row, and where it comes from:**

| Field | Source | Shape |
|---|---|---|
| `reference` | the booking's stored 8 characters | returned in presentation form, `FR-XXXX-XXXX` (`FR-ADR-015`) |
| `movie_title` | the movie row | string |
| `hall_name` | the screen row | string. The client's word is "hall"; the schema's word is "screen" (`SRC-003 OPEN-SCOPE-01`) |
| `showtime_starts_at` | `showtime.starts_at` | **ISO-8601 carrying the cinema's UTC offset**, e.g. `2026-08-20T14:00:00+05:30`. Serialised from the `cinema` row's zone, never from a literal and never in bare UTC — see the block below |
| `showtime_ends_at` | `showtime.ends_at`, stored not derived (`FR-ADR-018`) | **ISO-8601 carrying the cinema's UTC offset**, as `showtime_starts_at` |
| `seats` | the booked-seat rows | array of seat labels, e.g. `["C12","C13"]`, **ordered by row letter, then by seat number compared as an integer** — the rule below, which every endpoint returning seat labels follows |
| `seat_count` | derived | integer, 1..10 (`FR-ADR-026`) |
| `total_paise` | the **sum of the snapshotted** `booking_seat.price_paise` (`FR-ADR-039`) | integer. Never recomputed from current prices |
| `booked_at` | `booking.created_at` | **ISO-8601 carrying the cinema's UTC offset**, as above. It is rendered to the customer on the same rows, so it takes the same treatment |
| `group` | computed per `P-ACC-11` | `"upcoming"` or `"past"` |

**Every instant on this response carries the cinema's UTC offset, and the client never converts.**

```
2026-08-20T14:00:00+05:30        correct
2026-08-20T08:30:00Z             the same instant, and wrong on this wire
```

The offset is read from the **`cinema` row**, which `P-ADM-26` makes the authority on the venue's
zone, and it is serialised by the server. This is `P-BRW-06`'s rule, adopted verbatim rather than
re-derived, and the reason is its reason: **a client converting UTC to local is a second
implementation of `FR-ADR-018`, and it is the one that is wrong on a device whose own clock is set to
another country.**

The two alternatives are both defects, and naming them is the point:

- **Hardcoding `Asia/Kolkata` in the client** contradicts `P-ADM-26` — the cinema row wins, always —
  and breaks silently the moment `EP-ADM-29` changes the venue's zone, because nothing redeploys the
  browser.
- **Using the browser's own zone** shows a customer in Dubai a showtime ninety minutes off, on the
  screen they open at the door.

`SCR-ACC-04` renders `20 Aug 2026, 2:00 pm` (`S7.19`) and **there is no honest way for it to get that
from a bare `Z` instant**, which is what made this a wire defect rather than a rendering preference.
The client's only job is to format what it was given; `booked_at` takes the same treatment because it
is rendered on the same rows. **This is a wire change and the merge owner regenerates the contract.**

**Seat label ordering, stated once here and cited by every endpoint that returns seat labels.**

```
sort key = (row letter ascending, seat number ascending as an INTEGER)
  F7, F8, F9        correct
  F9, F7, F8        wrong - that is insertion order
  F2, F10           correct - 2 < 10 as integers
  F10, F2           wrong - that is a string comparison
```

**This is the rule for `EP-ACC-07`, `EP-ACC-08`, `EP-TKT-01` and the receipt (`E4 P-TKT-06`,
`SCR-TKT-02`), and those rows cite this one rather than restating it.** It was previously stated on
this row alone, and the others said only "seat labels" — so three surfaces returning the same booking's
seats had no ordering at all.

**Why insertion order is not good enough, which is the part that makes this worth a rule.** Ordering by
the booked-seat row's own id usually looks correct, because seats are normally created in label order
when a hall is laid out. It **diverges wherever a label does not follow the seat id**, which
`E6 P-ADM-14` explicitly permits: a seat added to a hall already in service gets the next id and
whatever label the layout needs. A customer who booked `F7`, `F8` and `F9` then reads
`Seats F9, F7, F8` on their receipt and at the door, and the person checking it has to re-sort three
labels by eye. **The number is compared as an integer, not as text**, or a hall wide enough for `F10`
sorts it before `F2`.

**What is deliberately absent from every row:**

- **No cancellation control, no cancel link, no "cancel" field, and no space left for one.**
  `SRC-001 §5.4.3` is withdrawn by erratum `E-2` and `FR-ADR-013` makes a confirmed booking final.
- **No refund amount, no refund state, no cancellation reason.**
- **The booking's `status` and `cancelled_at` columns exist in the schema and are not returned by any
  v1 endpoint** (`FR-ADR-013`). They are in the schema so that adding cancellation later is not a
  migration over live bookings; exposing them would be exposing a state nothing can produce.
- **No QR code and no scannable artefact** (`SRC-003 OPEN-TICKET-01`).
- **No tax line, no discount field, no booking fee** (`FR-ADR-040`).

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | No session | `401` `AUTH_REQUIRED` | "Sign in to see your bookings." |
| 2 | The caller has no bookings at all | `200` with two empty groups | "You have not booked anything yet." with a control that opens the movie listing |
| 3 | The caller has past bookings but none upcoming | `200`, `upcoming` empty | "You have nothing coming up." above the past list |
| 4 | Postgres unreachable | `503` `DEPENDENCY_UNAVAILABLE` | "Your bookings cannot be loaded right now. Try again shortly." |
| 5 | Anything unhandled | `500` `INTERNAL_ERROR` | "Something went wrong. If you need help, quote `a1b2c3d4`." |
| 6 | `page` is inside its bounds but past the end of one group, with no `group` named | `200`; that group's array is empty, the other group's is returned normally, and both `total_` counts are returned unchanged | that group's past-the-end zero state on `SCR-ACC-04`: "You have upcoming bookings, but none on this page. Go back to the first page." — or the same sentence with *past* in place of *upcoming* |

Row 2 is an empty state and **not** an error. Row 3 is a partial state and not an error either.
Row 6 is neither: both groups still have bookings, and one of them simply has none on the page that
was asked for. It is listed in this table so that an implementer reading only the exception paths finds
the case rather than inventing a `404` or a `422` for it.

**Server-side validation.**

| Parameter | Type | Bound | On failure |
|---|---|---|---|
| `group` | string | `upcoming` or `past`; optional; when absent both groups are returned | `422` `VALIDATION_FAILED`, "That is not a valid filter." |
| `page` | integer | 1..1000, default 1. **Applies to both groups independently when `group` is absent**, each against its own `total_`; a value past the end of one group returns that group empty and is not an error | `422` `VALIDATION_FAILED`, "That is not a valid page." |
| `page_size` | integer | 1..50, default 20. Applies to both groups, as `page` does | `422` `VALIDATION_FAILED`, "That is not a valid page size." |

**Worked example — the total on a row.** Rule: `total_paise` is the sum of the already-rounded per-seat
prices; the total is never itself rounded (`FR-ADR-038`).

- Inputs: three booked seats with snapshotted prices `45000`, `54000` and `54000` paise.
- `total_paise = 45000 + 54000 + 54000 = 153000`.
- Rendered: `153000 / 100 = 1530.00` → **`₹1,530.00`**, in `--fr-font-mono`, with Indian digit
  grouping (which is identical to Western grouping below `₹1,00,000` and diverges above it).
- The API returns `153000`. It never returns `1530.0` and never returns `"₹1,530.00"`.

---

### `P-ACC-11` · What separates upcoming from past, against which instant, and in what order · `ASSUMED`
`[SRC: SRC-001 §5.4.2 · SRC-003 OPEN-LOCALE-01 · FR-ADR-018 · FR-ADR-043]`
`[BRD: R-ACC-02]`

**Behaviour.** A booking is **upcoming** while the evaluation instant is strictly before its showtime's
`ends_at`, and **past** from `ends_at` onward.

**Status is `ASSUMED`.** `SRC-001 §5.4.2` asks for "upcoming and past bookings" and names no boundary.
No ruling and no `APPROVED` ADR names one. The rule below is the build session's inference under
Art III.9 and **it never hardens into a constraint.** It is flagged so the next session does not read
it as ruled.

**Who may do it.** Not applicable — this is a classification rule.

**Preconditions.** The showtime carries `ends_at`, which is stored and not derived (`FR-ADR-018`).

**The rule, in full.**

```
booking.group = "upcoming"  if  now < showtime.ends_at
booking.group = "past"      if  now >= showtime.ends_at
```

- `now` is the **injected clock**, in UTC. Never the container's local time and never the client's
  clock (`FR-ADR-018`, Art IX.5).
- The comparison is between two instants, so it is zone-independent. **The zone matters only for what
  is rendered**, which is Asia/Kolkata (`SRC-003 OPEN-LOCALE-01`).

**Why `ends_at` and not `starts_at`.** A customer sitting in the hall during the film is the single
most likely person to open this list, because they are being asked for their reference at the door and
the film has started. Classifying by `starts_at` would move their booking into "past" at the exact
moment they most need to find it. `ends_at` is stored precisely so it cannot drift when an admin
corrects a runtime (`FR-ADR-018`). It also lines up with the sales cut-off, which is `starts_at + 15`
minutes and is therefore **after** the advertised start — a showtime can still be selling while it is
running (`FR-ADR-042`, `PROVISIONAL`).

**Ordering.**

| Group | Order | Why |
|---|---|---|
| `upcoming` | `showtime.starts_at` **ascending**, then `booking.created_at` descending, then `booking.id` ascending | the show you need next is at the top |
| `past` | `showtime.starts_at` **descending**, then `booking.created_at` descending, then `booking.id` ascending | the show you just saw is at the top |

The two tie-breakers make the order **total**, so paging is stable. Two bookings for the same showtime
would otherwise be returned in an order the database is free to change between pages, which shows a
customer the same booking twice and hides another.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A showtime with a null `ends_at` | `500` `INTERNAL_ERROR` | "Something went wrong. If you need help, quote `a1b2c3d4`." |

Row 1 cannot occur — `ends_at` is not nullable — and it is written down rather than assumed away,
because a classification rule that silently defaults a null to "past" would hide a data defect by
mis-filing a customer's booking.

**Server-side validation.** None — no input.

**Worked example — one showtime, three evaluation instants.**

Inputs, with both the stored instant and its Asia/Kolkata rendering:

- `showtime.starts_at = 2026-08-20T08:30:00Z` = `2026-08-20 14:00 IST`
- `showtime.ends_at   = 2026-08-20T11:05:00Z` = `2026-08-20 16:35 IST`

| Evaluation instant (UTC) | Same instant in Asia/Kolkata | `now < ends_at`? | Group |
|---|---|---|---|
| `2026-08-20T09:30:00Z` | `2026-08-20 15:00 IST` — the film is running | yes | **upcoming** |
| `2026-08-20T11:05:00Z` | `2026-08-20 16:35 IST` — the film has just ended | no (`>=`) | **past** |
| `2026-08-20T11:06:00Z` | `2026-08-20 16:36 IST` | no | **past** |

The boundary is closed at the top: at exactly `ends_at` the booking is past.

---

### `P-ACC-12` · A customer sees their own bookings and nobody else's · `RULED`
`[SRC: SRC-001 §7.4 · SRC-001 §5.4.2 · FR-ADR-014 · FR-ADR-015 · FR-ADR-009 · FR-ADR-011]`
`[BRD: R-ACC-02 · R-ACC-03]`

**Behaviour.** Every endpoint under `/api/me/` returns only rows owned by the caller resolved from the
session. The owner is never taken from the request.

**Who may do it.** `authenticated` — `customer`, `manager` and `admin`. A `manager` and an `admin`
calling `/api/me/bookings` see **their own** bookings as people, not anybody else's.
**`/api/me/` means the caller, for every role, with no exception and no override parameter.** There is
no v1 endpoint by which an admin reads another customer's bookings; if the client asks for one it is a
new specification with its own audit row (`FR-ADR-019`), not a query parameter added here.

**How it is enforced.** Once, on the router, as a dependency (`SRC-001 §7.4`, Art VI.4, `FR-ADR-011`).
The dependency yields the caller's user id and the handler's query filters on it. **A handler that
reads a user id from the request and checks it itself is the pattern that eventually misses one**, and
it is a defect here whether or not it happens to be correct.

**Preconditions.** A valid session.

**Happy path.** As `P-ACC-10`.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | A reference that exists and belongs to another customer | `404` `NOT_FOUND` | "No booking with that reference is on your account." |
| 2 | A reference that does not exist at all | `404` `NOT_FOUND` | "No booking with that reference is on your account." |
| 3 | No session | `401` `AUTH_REQUIRED` | "Sign in to see your bookings." |
| 4 | **The per-user lookup bucket is empty** — `RATE_LIMIT_LOOKUP_USER_PER_MIN`, 20 per minute | `429` `RATE_LIMITED` with `Retry-After: 3` | "Too many lookups. Try again in 3 seconds." |
| 5 | **The per-IP lookup bucket is empty** — `RATE_LIMIT_LOOKUP_IP_PER_MIN`, 60 per minute, which is what refuses first when several callers share one address | `429` `RATE_LIMITED` with `Retry-After: 1` | "Too many lookups. Try again in 1 second." |

**Row 5 was missing and is added here.** `EP-ACC-08` declares both buckets and the header carries
whichever one refused (`S7.20`, `FR-ADR-058`); a table that derives only the narrower one is
incomplete, because the wider one refuses first for a caller behind a shared address. Both figures are
derived and never typed: `ceil(60 / 20) = 3` and `ceil(60 / 60) = 1`. **Row 5's singular is copy that
ships** — `S7.20` names this bucket as one of only four in the product that reach `Retry-After: 1`,
and `"{n} seconds"` written unconditionally puts "1 seconds" on a live path.

**Rows 4 and 5 belong to `EP-ACC-08` alone, and `EP-ACC-07` is deliberately unlimited.** This row's
behaviour covers *"every endpoint under `/api/me/`"*, which made its exception table read as though the
bookings **list** were limited too — while `EP-ACC-07` carries `rate_limit: none`. The two are
consistent and the asymmetry is the point:

| Endpoint | Limited | Why |
|---|---|---|
| `EP-ACC-08` `/api/me/bookings/{reference}` | **yes**, both lookup buckets | It takes a **guessable identifier**. The reference is the only value that gets a person into a hall (`FR-ADR-015`), so any endpoint that resolves one is an enumeration target and is limited as well as authenticated |
| `EP-ACC-07` `/api/me/bookings` | **no** | **There is nothing to enumerate.** It accepts no identifier at all — the caller's user id comes from the session and no user id is accepted in the path, the query or the body, so there is no guess a caller could make. Limiting it would spend Redis on a control with no attack to stop, and would rate-limit a customer refreshing their own bookings list at a door |

**A reader must be able to tell an unlimited endpoint from an oversight**, which is why the absence is
written down rather than left as a silence. `P-ACC-14` enumerates every bucket this epic has and has no
row for the list; that is the same statement from the other side.

**Rows 1 and 2 are deliberately identical.** A `403` on row 1 would confirm that the reference exists,
which turns the endpoint into an oracle for probing the reference space. The reference is the only
thing that gets a person into a hall (`FR-ADR-015`), so the lookup is authenticated **and** rate
limited (`FR-ADR-058`) **and** answers "not yours" and "not real" the same way.

**The test shape, stated because the obvious test passes against broken code.**

The acceptance criterion has **three** assertions and all three are required:

1. **Non-empty for their own.** Sign in as customer A, who has at least one booking. `GET
   /api/me/bookings` returns a **non-empty** list, and A's reference is in it.
2. **Denied for another's.** Still signed in as A, `GET /api/me/bookings/{B's reference}` returns
   `404 NOT_FOUND`.
3. **The other direction.** Sign in as customer B and `GET /api/me/bookings/{B's reference}` returns
   `200`.

**A test asserting only assertion 2 passes against a query that returns nothing for anybody.** That is
the failure this shape exists to catch, and it is the same shape the manager-scope test uses
(`CLAUDE.md`, `FR-ADR-011`). Assertion 1 proves the query works; assertion 2 proves it is scoped;
assertion 3 proves the scoping is by identity rather than by the data simply being absent.

**Server-side validation.** The reference is normalised for lookup as `FR-ADR-015` specifies:
case-insensitive, hyphens and whitespace ignored, the `FR` prefix optional. **Nothing is silently
corrected** — a character outside the 30-character alphabet is not mapped to anything and the lookup
simply fails with row 2.

---

### `P-ACC-13` · The seat selection survives sign-in or registration · `RULED`
`[SRC: SRC-001 §3.1 · SRC-001 §5.2.6 · SRC-003 OPEN-BOOK-02 · FR-ADR-046 · FR-ADR-014 · FR-ADR-045 · FR-ADR-052]`
`[BRD: R-ACC-05]`

**Behaviour.** A visitor who chooses seats and is then asked to sign in or register returns to the same
showtime with the same seats selected. **The hold is not taken automatically.** A seat that has gone in
the interim is reported by name before the customer proceeds.

**Who may do it.** A `guest` (before authenticating) and a `customer` whose session expired mid-flow.

**Preconditions.** The visitor has selected at least one seat on a seat map. The selection is entirely
client-side and has taken no lock (`FR-ADR-046`), so nothing on the server distinguishes a guest
looking at a seat map from a customer looking at one.

**Exactly what is stored, where, and for how long.**

| Property | Value |
|---|---|
| Mechanism | `sessionStorage` — **not** `localStorage`, not a cookie, not a URL parameter, not the server |
| Key | `fr.pending_selection` |
| Value | `{"showtime_id": 412, "seat_ids": [1187, 1188], "stored_at": "2026-08-14T10:00:00Z"}`. `stored_at` is the instant of the write — the moment the visitor left the seat map |
| Written | **once**, when a visitor who is not authenticated leaves this seat map for the authentication screen with a non-empty selection, **before** the authentication step opens. **By either route out** — the seat map's primary action **or** the header's `Sign in` link (`E8 SCR-XCT-05`). **Which control they pressed does not change what is stored**: see the block below |
| Lifetime | until the tab closes, which is `sessionStorage`'s own behaviour and is the right lifetime; **and** discarded on restore if `stored_at` is more than **30 minutes** before the current instant |
| Cleared | on a successful hold; when the visitor navigates to a different showtime; **and on sign-out, which clears every `fr.*` value and not this key alone** — the rule below |

**`fr.pending_selection` is one of two keys and this row owns only this one.** The live local
selection on the seat map is `fr.selection`, written on every tap and owned by `E2 P-SEA-03`, which
carries the table setting the two side by side and the reason the two write policies cannot share one
key. **This row's key is the one-shot snapshot handed to the authentication round trip**, written
once and deleted on restore. Neither row restates the other's half.

**Every route out of the seat map to the authentication screen writes it, not only the primary
action.** `E8 SCR-XCT-05`'s header carries a `Sign in` link on every route in the product, the seat
map included, and a visitor who uses it never touches the primary action. **Under a write-on-press
rule that visitor arrived at `SCR-ACC-01` with nothing stored**, fell to that screen's *otherwise*
branch, and was returned to the **movie listing** — their showtime gone, their seats not restored,
and no message — from the same screen that returns everyone else to their seats. The rule is
therefore stated by **what the visitor is doing**, leaving a seat map with a selection, rather than
by **which control they touched**:

```
leaving /showtimes/{id} for the authentication screen, not authenticated, selection non-empty
  -> write fr.pending_selection, then open SCR-ACC-01
        by the primary action        "Sign in to hold these seats"
        by the header's Sign in link  E8 SCR-XCT-05
```

Both routes then arrive at `SCR-ACC-01` in the same state, show the same context note, and return to
the same seat map with the same seats re-selected. **Which of two controls the visitor pressed two
screens earlier may not decide whether they keep their selection** — and this is the one seam in the
product where a guest becomes a customer, so it is where losing it costs the sale.

**Sign-out clears every `fr.*` value in `sessionStorage`, without exception.** Not this key, not a
named list of keys — **the whole `fr.` namespace**, whatever any lane has put in it.

```
sign-out  ->  for every key in sessionStorage starting with "fr."  ->  remove it
```

This row states the rule because it owns the storage table; **it does not own the individual keys and
does not enumerate them.** `fr.pending_selection` is this lane's. The live hold token and
`fr.last_booking_reference` belong to E2 and E3, which state their own halves — including that signing
out **releases the live hold**, which is that lane's decision and not restated here.

**The rule is a namespace sweep rather than a list because a list is the thing that goes stale.** Every
key added later is covered on the day it is added, by a lane that never has to find this table. The
`fr.` prefix exists for exactly this.

**The consequence that makes this sharper than tidiness, stated because a partial clear looks
harmless.** `fr.last_booking_reference` survives sign-out under any per-key reading. Customer A signs
out on a shared machine; customer B signs in on the same tab and opens the checkout route; that
screen's own rule redirects — **with no request, from the stored value** — to **customer A's
confirmation URL**. B lands on a 404 naming a booking that is not theirs, having been sent there by
the product. Nothing leaks, because `EP-TKT-01` returns the same 404 to every non-owner
(`E4 P-TKT-09`), but the reference itself was on B's screen and in their history, and the reference is
the one value that gets a person into a hall (`FR-ADR-015`). **A partial clear is how a shared machine
hands one customer another customer's ticket number.**

**Why `sessionStorage` and not the server** (`FR-ADR-046`): a server-side selection would be session
state, which `SRC-002 §7.3` forbids, and it would need a store for data that is worth nothing thirty
seconds later. **Why not a URL parameter:** a long seat list in a query string survives being shared or
bookmarked, which produces a link that re-selects seats for a stranger.

The 30-minute staleness discard is a **`[JUDGMENT CALL]`** under Art III.9. It exists because a
restored selection older than that is very likely to be entirely unavailable, and restoring it only to
report every seat gone is worse than starting clean.

**Happy path.**

1. The guest selects seats. The running total updates as they select, exactly as it does for a customer
   (`SRC-001 §5.2.4`).
2. The primary action reads **"Sign in to hold these seats"** — the requirement is stated before it is
   enforced, not discovered by clicking (`COMPONENTS.md §5`, `FR-ADR-046`).
3. Pressing it writes `fr.pending_selection` and opens the authentication screen (`SCR-ACC-01`). It
   does not navigate away and lose context. **A visitor who instead follows the header's `Sign in`
   link (`E8 SCR-XCT-05`) writes the same value and opens the same screen**, per the storage table
   above, and every step below reads the same for both.
4. The visitor registers (`P-ACC-01`) or signs in (`P-ACC-02`). Either returns a session.
5. The interface returns to the seat map for `showtime_id` and **refetches the seat map** before
   restoring anything.
6. Seat ids from the stored selection that are still `available` are re-selected.
7. Seat ids that are now `sold` or `held_by_other` are **not** selected, are shown in their real state,
   and are named in the error banner (`COMPONENTS.md §6`).
8. `fr.pending_selection` is deleted. **`E2 P-SEA-03`'s `fr.selection` is not** — that key holds the
   live selection this step has just re-applied, it is written on every change, and it is that row's
   to clear. Deleting both here would erase the selection step 6 restored.
9. **The hold is not taken.** The customer presses the primary action — now reading "Hold these seats"
   — once.

**Why the hold is not taken automatically** (`FR-ADR-046`, and it is the part most likely to be
"improved" into a defect): taking it automatically would either silently drop a seat that has gone, so
the customer pays for three of the four they chose, or fail with an error immediately after a
successful registration, which reads as the registration having failed. **Restoring the selection and
letting them press once removes both failure modes**, and it re-checks availability at the moment it
matters.

**Exception paths.**

| # | Trigger | Server / client | What the user sees, verbatim |
|---|---|---|---|
| 1 | **Two or more** stored seats are now `sold` or `held_by_other`, and at least one survives | client-side, after the refetch; no server error | "C12 and C13 were taken while you were signing in. Your other seats are still selected." |
| 1a | **Exactly one** stored seat has gone, and at least one survives | as row 1 | "C12 was taken while you were signing in. Your other seats are still selected." |
| 2 | Every stored seat has gone | client-side | "The seats you chose were taken while you were signing in. Choose again from the map." |
| 3 | Sales for the showtime closed while the visitor was registering | the hold endpoint returns `409` `SALES_CLOSED` when pressed | `E2 P-HLD-14` row 9's body, reproduced and not authored here: "Sales for this showtime closed at 7:45 pm. Choose another showtime." — the time renders `sales_close_at` in `S7.19`'s `h:mm am/pm` form in Asia/Kolkata and is never typed |
| 4 | The stored entry is older than 30 minutes | client-side | nothing is restored and nothing is said. The seat map opens with no selection. |
| 5 | `sessionStorage` is unavailable or full | client-side | nothing is stored and nothing is said before the fact. On return the map opens with no selection. The sign-in still works. |
| 6 | The stored `showtime_id` no longer exists | client-side | the interface returns to the movie listing. "That showtime is no longer available." |

**Exception 3 publishes no string of its own, and this row previously did.** It published the
sales-closed **banner** — `Sales for this showtime have closed.` — against a **hold attempt**, which
is a different surface with a different job. `E1 P-BRW-07` owns that banner and states in terms that
a hold attempted on a closed showtime takes `E2 P-HLD-14` row 9's body **and not the banner**; `E2`
states the same split from its own side, that a banner describes a standing condition the customer
can see for themselves while an error explains an action that was just refused. Both are declared
owners and this row is neither, so this row cites rather than restates. **The customer most likely to
meet this case is the one who has just spent thirty seconds registering** — and the banner names no
time and offers no next step, which leaves them with a refusal, no idea when sales closed, and
nothing to do about it.

Rows 1 and 1a's wording is the rule from `FR-ADR-052` applied literally: it says what happened, it
names the seats so the interface can highlight them, and **it does not blame the customer for a race
they lost**. It is not "someone beat you to it" and it is not an apology. The singular and the plural
are chosen by count and not by judgement — one offending seat takes 1a, two or more take row 1, with
the labels in the order the customer selected them and joined `A, B and C`, which is the shape
`SEAT_UNAVAILABLE` already uses.

**Which situation this row owns, and which it does not.** A customer can lose a chosen seat in two
distinct ways, and the product publishes **two** sentences for them — deliberately two, not
accidentally three:

| Situation | Owner | The sentence |
|---|---|---|
| The local selection is refreshed and a seat has gone. **No sign-in is involved** — the customer is already signed in and the map simply re-polled | **`P-SEA-03`**, lane E2 | `C12 is no longer available. It has been removed from your choices.` |
| **The customer returns from registration or sign-in** and a seat has gone in the meantime | **this row** | `C12 and C13 were taken while you were signing in. Your other seats are still selected.` |

They are two rather than one because the customer's mental state is different and the sentence has a
different job. On a refresh nothing the customer did caused it and there is nothing to explain, so the
sentence is a bare statement. **On return from sign-in the customer has just spent thirty seconds
typing a password and needs to be told that the time is what cost them the seat** — otherwise the
registration reads as the thing that went wrong. Naming the interval is the whole content of the
second sentence.

**"Still selected", never "still held", on both sides of that split.** Nothing is held until a hold
request is made and granted, and the hold is all-or-nothing (`P-HLD` rows in E2) — so a sentence
saying seats are "still held" at this point would name a state that does not exist and promise a
guarantee the customer does not have. This row's happy path step 9 is explicit that **the hold is not
taken** here, which is exactly why the word matters.

**Server-side validation.** None — nothing in this specification is submitted to the server. The
restored selection is re-validated by the hold endpoint like any other selection, which is the point:
the client-side restore is a convenience and the server's check is the enforcement.

---

### `P-ACC-14` · The credential endpoints are rate limited · `RULED`
`[SRC: SRC-002 §8.4.1 · SRC-002 §8.4.2 · SRC-002 §7.9 · FR-ADR-058 · FR-ADR-028 · FR-ADR-052]`
`[BRD: R-ACC-01 · R-ACC-04]`

**Behaviour.** Sign-in, registration, password-reset request, password-reset **confirm** and booking-reference lookup each carry a
token bucket in Redis. Exceeding one returns `429` with `Retry-After`.

**Who may do it.** Not applicable — this is a control the server applies.

**`SRC-002 §8.4.1` names seat selection and booking, not these endpoints.** Extending the limiter to
them is stricter and needs no signature (Art III.10, `FR-ADR-058`). An unlimited sign-in endpoint is a
guessing oracle and an unlimited registration endpoint fills a table nothing prunes (`FR-ADR-012`).

**The buckets that belong to this epic** (`FR-ADR-058`, whose values are **estimates, not
measurements**, and are replaced by Phase 7's load test):

| Endpoint | Per user / per key | Per IP |
|---|---|---|
| sign-in | 10 / 15 minutes, keyed on the submitted `lower(email)` | 30 / 15 minutes |
| registration | — | 5 / hour |
| password reset request | — | 5 / hour |
| password reset **confirm** | — | 10 / hour, its own bucket and **not** the request's (`P-ACC-08` row 8) |
| booking lookup by reference | 20 / minute, keyed on the caller's user id | 60 / minute |

**Both buckets must have a token.** They are independent (`FR-ADR-058`).

**The per-IP key is the real client address**, taken from the rightmost-but-one entry of
`X-Forwarded-For` with exactly one trusted proxy (`FR-ADR-058`). Not the leftmost, which a client can
forge. **Getting this wrong is silent** — every customer shares one bucket and the limiter appears to
work while protecting nothing — so the test asserts that two requests carrying different forged
`X-Forwarded-For` values from the same peer are counted in the same bucket.

**On Redis being unreachable the limiter fails closed: `503`.** Not unlimited access
(`FR-ADR-058`, `FR-ADR-028`). A limiter that fails open removes a control at the moment the system is
least healthy.

**Exception paths.**

| # | Trigger | Server | What the user sees, verbatim |
|---|---|---|---|
| 1 | Any bucket empty | `429` `RATE_LIMITED`, `Retry-After` in seconds | the endpoint-specific wording in `P-ACC-01` row 8, `P-ACC-02` rows 4 and 5, `P-ACC-07` row 4, `P-ACC-08` row 8, `P-ACC-12` rows 4 and 5 |
| 2 | Redis unreachable | `503` `DEPENDENCY_UNAVAILABLE` | the endpoint-specific wording in `P-ACC-01` row 9, `P-ACC-02` row 6, `P-ACC-07` row 5 |

**Server-side validation.** None — the limiter runs before the handler, as a router dependency.

**Worked example — the `Retry-After` value on sign-in.** Rule: `Retry-After` is computed from the
bucket's refill rate, never from a constant (`FR-ADR-058`).

- Inputs: the sign-in per-email bucket has capacity `10` and refills `10` tokens per `900` seconds.
- Refill rate = `900 / 10` = **one token every 90 seconds**.
- A customer empties the bucket at `t = 0`. At `t = 0` the next token is available at `t = 90`.
- `Retry-After: 90`, and the message reads "Try again in 90 seconds."
- The same customer retrying at `t = 30` gets `Retry-After: 60`, because 60 seconds remain until the
  next token. **A constant would have said 90 both times, which is a wrong number the second time.**

---

### `P-ACC-15` · A booking completes in under two minutes, and the first-time figure is reported separately · `RULED`
`[SRC: SRC-001 §3.1 · FR-ADR-046 · FR-ADR-027 · FR-ADR-041]`
`[BRD: R-QLY-05]`

**Behaviour.** A signed-in customer completes a booking from opening the seat map to seeing the
confirmation on screen in under **120 seconds**. A first-time visitor's run, which includes
registration, is measured and reported as its own figure with no target attached to it.

**Who may do it.** Not applicable — this is a measured criterion, `SC-1`.

**What is measured, exactly.**

| Mark | Definition |
|---|---|
| `t0` | the instant the seat map for a chosen showtime is first painted with real seat data — the first render after the seat-map response resolves, **not** the click that requested it and **not** the moment the page's shell appears |
| `t1` | the instant the confirmation screen paints the booking reference (`FR-ADR-048`) |
| Signed-in figure | `t1 − t0`, for a customer who already had a session at `t0`. **Target: under 120 seconds.** |
| First-time figure | `t1 − t0` for a visitor with no account at `t0`, whose run includes pressing "Sign in to hold these seats", registering, and returning through `P-ACC-13`. **No target.** |

**The first-time figure is reported honestly and separately, and is never merged into the signed-in
one.** `FR-ADR-046` states the reason plainly: it includes registration and will not be met. Reporting
one blended number would either fail a criterion the product does meet, or hide the fact that the
first-time path is slower — and the first-time path is the one every customer takes exactly once.

**Reporting rule, from the honesty floor.** **The worst run first, then the median, each with its
count.** "37 runs; slowest 84 s; median 51 s" — never "about 50 seconds". A rate with no count is not
evidence.

**What is inside the budget and cannot be optimised away.** These are named so nobody measures a path
that skips them:

- the simulated payment's artificial delay, `PAYMENT_SIMULATED_DELAY_MS`, which is configuration
  bounded well below the hold TTL and checked at startup (`FR-ADR-041`; the bound and its check belong
  to the payment epic). **The name carries the unit and the unit is milliseconds, not seconds** — it is
  `_MS` in `S7.9`'s configuration table and everywhere else it appears, so a term of `1500` here is
  `1.5` seconds of a 120-second budget, not 1,500 of them. This epic does not set its value.
- one round trip to acquire the hold, and one to confirm.
- the customer's own reading and choosing time, which is the largest term and is not removable.

**What is not inside the budget:** the seat map's 3-second poll (`SRC-002 §8.6.1`) gates nothing — a
seat is selectable the moment the map is painted — and the receipt email is asynchronous through the
outbox, so `t1` never waits for SES (`FR-ADR-031`, `FR-ADR-048`).

**Exception paths.**

| # | Trigger | Result | What the user sees, verbatim |
|---|---|---|---|
| 1 | The run exceeds 120 seconds and the 3-minute hold expires mid-run | the hold is gone; `409` `HOLD_EXPIRED` on confirm | "The hold on your seats has ended and they have been released. You have not been charged." |

The hold TTL is 180 seconds and the target is 120 seconds, so the criterion has 60 seconds of margin
before the customer's own hold becomes the thing that fails. That relationship is worth stating: **the
two-minute target is not arbitrary against a three-minute hold.**

**Server-side validation.** None. This is measured, not enforced.

**Worked example — one signed-in run.**

- `t0 = 2026-08-14T10:00:00.000Z` — the seat map paints for showtime 412.
- The customer selects two seats and presses "Hold these seats" at `+18.4 s`. The hold is granted with
  `expires_at = 2026-08-14T10:00:21.400Z + 180 s`.
- The customer presses "Pay ₹1,530.00" at `+41.9 s`. The simulated payment returns after its
  configured delay.
- `t1 = 2026-08-14T10:00:47.300Z` — the reference paints.
- `t1 − t0 = 47.3 s`. **Under 120 s: the criterion passes for this run.**
- The same walk performed by a visitor with no account, whose registration took 39 seconds, gives
  `86.3 s`. **That figure is reported on its own line, labelled first-time, with no pass or fail
  attached.**

---

## S5 — UX specification

### `SCR-ACC-01` · Sign in or register — one screen, two tabs
**Route.** `/sign-in` and `/register` — **two routes, one screen**, with the tab preselected by the
route. Switching tabs replaces the URL without a navigation, so the browser's back button returns to
the seat map rather than to the other tab.
· **Who reaches it.** guest · a customer whose session expired · anyone following a "sign in" control
· **Component basis.** `COMPONENTS.md §11` (forms), `COMPONENTS.md §6` (the error banner)

**What the user arrives with / leaves with.** They arrive in one of two states, and **the state is
decided by whether they left a seat map with seats selected, never by which control they pressed**:
from a surface with no selection behind it — the movie listing, or the header's `Sign in` link from
any screen that is not a seat map (`E8 SCR-XCT-05`) — with nothing stored; or from a seat map with a
non-empty selection, in which case `fr.pending_selection` has already been written **by whichever
route out they took**, the primary action or that same header link (`P-ACC-13`). So "Sign in to hold
these seats" and the header's `Sign in` link arrive here identically and **this screen cannot tell
them apart** — which is the point, because under the earlier write-on-press rule the header route
arrived with nothing stored and was silently dropped on the movie listing. Both are **deliberate**
sign-ins. They leave with a session cookie and are returned to exactly where they came from: the seat
map for the stored showtime, with the selection restored, or the movie listing.

**A third arrival exists and this screen does not own its destination**: a customer sent here by a
`401` mid-task. `SCR-XCT-04` preserves the path they were on and returns them there. The scope note
under the states table below sets out both cases and which row owns each.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Tab bar — `Sign in` / `Register` | one row; `--fr-rule` under the unselected, `--fr-surface-accent` bar under the selected | two tabs, never two destinations (`FR-ADR-046`). The email field's contents survive a tab switch; the password field does not | — |
| Email field | `--fr-surface-inset`, 1px `--fr-control-edge`, `--fr-radius-md`, min height `--fr-tap-min`, text `--fr-ink` at `--fr-text-md` | `type="email"`, `autocomplete="email"`, `inputmode="email"` | shape checked on blur; **enforced on the server** (`P-ACC-01`) |
| Email label | `--fr-text-sm`, `--fr-weight-medium`, `--fr-ink` | always visible, never a placeholder | — |
| Password field | as the email field | `autocomplete="current-password"` on the sign-in tab, `new-password` on the register tab | length checked on blur on the register tab only; enforced on the server |
| Show-password control | `--fr-accent-ink`, `--fr-text-sm` | toggles the field between masked and visible; the accessible name changes with the state | — |
| Password help text | `--fr-text-xs`, `--fr-ink-muted` | **on the register tab, visible before the field is touched** — the rules are stated before they are broken (`P-ACC-03`) | — |
| Primary action | `--fr-surface-accent` fill, `--fr-ink-on-accent`, `--fr-radius-md`, min height `--fr-tap-min`, `--fr-weight-bold` | reads `Sign in` or `Create account` by tab | disabled only while a request is in flight, never while a field is invalid — a control that cannot be pressed cannot say why |
| Forgot-password link | `--fr-accent-ink`, `--fr-text-sm` | sign-in tab only; opens `SCR-ACC-02`, carrying whatever is in the email field | — |
| Context note | `--fr-text-sm`, `--fr-ink-muted` | shown only when `fr.pending_selection` exists: states that the seats are still selected | — |
| Field in error | border becomes 2px `--fr-danger-ink`; message `--fr-text-xs` `--fr-danger-ink` | associated with the field and announced, not only coloured (`FR-ADR-051`) | — |
| Form-level failure | `COMPONENTS.md §6` banner on `--fr-surface-danger` | used for `CREDENTIALS_INVALID`, `RATE_LIMITED`, `DEPENDENCY_UNAVAILABLE`, `INTERNAL_ERROR` | — |

**There is no "remember me" control**, no social sign-in, and no password-strength meter. None is asked
for by any source, and a strength meter would contradict `P-ACC-03`'s deliberate absence of composition
rules by scoring what the rules do not require.

**States.**

| State | What renders |
|---|---|
| **Empty** | The full form at full height, both fields blank, the primary action enabled. A form is its own empty state (`COMPONENTS.md §11`). |
| **Loading** | The primary action shows a busy state and is disabled. **Both fields stay readable and stay filled.** Nothing is blanked and nothing resizes. |
| **Error — field** | The offending field takes the 2px `--fr-danger-ink` border and its message renders beneath it, associated by `aria-describedby` and announced. Other fields keep their values. |
| **Error — form** | The banner renders above the tab bar. The password field is cleared; the email field is not. Clearing the password is so a shoulder-surfer does not read a failed attempt off a screen the customer has stopped looking at. |
| **Success** | No success screen. The interface navigates immediately: to the seat map with the selection restored if `fr.pending_selection` exists, otherwise to the movie listing. A success message on a screen nobody stays on is a screen nobody reads. **This rule governs a deliberate sign-in only — see the scope note below.** |
| **Partial** | Not applicable — there is nothing to load. The screen renders complete on first paint and needs no data fetch. |
| **Rate limited** | The banner states the wait, **rendered from the `Retry-After` integer by `S7.20`** — seconds below 120, minutes at or above it, so this screen's sign-in strings read "90 seconds" and "30 seconds" while its registration string reads "12 minutes". The header itself is never shown. The primary action stays enabled: the customer may try again, and the server is the thing that says no. |
| **Redis unavailable** | The banner states that sign-in is unavailable and that browsing still works. It never silently degrades (`FR-ADR-028`). |

**Copy.**

| Where | Verbatim |
|---|---|
| Tab labels | `Sign in` · `Register` |
| Email label | `Email address` |
| Password label | `Password` |
| Password help, register tab | `At least 12 characters. No numbers or symbols required. Maximum 72 bytes.` — **`12` interpolates `PASSWORD_MIN_LENGTH`**; `72` is bcrypt's truncation point and is correctly a literal (`P-ACC-01`) |
| Primary action, sign-in tab | `Sign in` |
| Primary action, register tab | `Create account` |
| Forgot-password link | `I have forgotten my password` |
| Context note when a selection is pending | `Your seats are still selected. Sign in to hold them.` |
| Show-password control | `Show password` / `Hide password` |
| Invalid credentials | `That email address and password do not match an account.` |
| Email already registered | `An account already exists for that email address. Sign in instead, or reset the password if you have forgotten it.` |
| Email empty | `Enter an email address.` |
| Email malformed | `That is not a valid email address.` |
| Password too short | `Your password must be at least 12 characters. It does not have to contain numbers or symbols.` — **`12` interpolates `PASSWORD_MIN_LENGTH`** |
| Password too long | `Your password is too long. The limit is 72 bytes and yours is 84. Most characters count as one byte; accented and non-Latin characters count as two, three or four.` |
| Rate limited, sign-in | `Too many sign-in attempts for that email address. Try again in 90 seconds.` |
| Redis unavailable | `Sign-in is unavailable right now. Browsing still works. Try again shortly.` |
| Unhandled failure | `Something went wrong and you were not signed in. If you need help, quote a1b2c3d4.` |

No sentence apologises, none uses an exclamation mark, and none blames the customer (`SRC-002 §2.2`,
`FR-ADR-052`).

**Which sign-in this screen's destination rule describes, and which it does not.**

This screen is reached two ways, and **its success destination governs only the first**:

| How the customer got here | Where sign-in sends them | Owner |
|---|---|---|
| **A deliberate sign-in** — they navigated here themselves, from the header or a link, with **no interrupted task to return to** | this screen's success rule above: the seat map if `fr.pending_selection` exists, otherwise the movie listing | **this screen** |
| **An interrupted request** — a `401` sent them here mid-task, from any surface | back to **the path they were on**, which `SCR-XCT-04` preserved | **`SCR-XCT-04`** |

**`SCR-XCT-04` owns the interrupted case, and this screen does not.** The 401 interstitial is the
surface the customer is actually on when the question arises, and it preserves **the path** rather than
only a seat selection — which is the difference that matters. Under this screen's rule applied to an
interruption, an admin whose session expired mid-edit has no `fr.pending_selection`, falls to
"otherwise", and is dropped on the movie listing with their work abandoned and no route back. A
manager interrupted on a dashboard lands there too. **The rule is right for the case it was written
for and wrong for the case it was being read into**, which is why the two are separated rather than
merged.

The two are **not one rule stated twice.** They take different inputs — a stored selection against a
preserved path — and they are correct for different situations, so a reader finding both has found a
deliberate pair.

**Accessibility.**

- Focus order: tab bar → email → password → show-password → primary action → forgot-password link.
  Visual order and focus order are the same (`FR-ADR-051`).
- The tab bar is a real tab pattern: `role="tablist"`, arrow keys move between tabs, and the panel is
  labelled by its tab. Switching tabs moves focus to the first field of the new panel.
- Every input has a programmatically associated visible label. No placeholder is used as a label.
- Field errors are associated with `aria-describedby` and the error region is a live region, so an
  error is announced and not only coloured (`FR-ADR-051`).
- The form-level banner is announced through the same live region as everywhere else in the product
  (`COMPONENTS.md §6`).
- Every control is at least `--fr-tap-min` tall.
- The focus ring is `--fr-stroke-bold` solid `--fr-focus-ring` with a 2px offset, never removed and
  never suppressed for mouse users (`COMPONENTS.md §0.2`).
- The show-password control's accessible name states the action it will perform, not the current state.

---

### `SCR-ACC-02` · Request a password reset
**Route.** `/account/reset` · **Who reaches it.** anyone; normally from `SCR-ACC-01`'s
forgot-password link · **Component basis.** `COMPONENTS.md §11`

**What the user arrives with / leaves with.** They arrive with an email address they may have typed on
the previous screen, which is carried into the field. They leave having been told the same thing
whether or not the address has an account.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Email field | as `SCR-ACC-01` | `autocomplete="email"`; prefilled from the previous screen when available | shape only; enforced on the server (`P-ACC-07`) |
| Primary action | `--fr-surface-accent`, `--fr-ink-on-accent`, min height `--fr-tap-min` | reads `Send a reset link` | disabled only while in flight |
| Back link | `--fr-accent-ink`, `--fr-text-sm` | returns to `SCR-ACC-01` | — |
| Confirmation panel | `--fr-surface-raised`, `--fr-radius-lg`, padding `--fr-space-4`, text `--fr-ink` | replaces the form on `202` | — |

**States.**

| State | What renders |
|---|---|
| **Empty** | The form, one field, the action enabled. |
| **Loading** | The action is busy and disabled; the field stays filled and readable. |
| **Error** | Field-level for a malformed address; the `COMPONENTS.md §6` banner for `RATE_LIMITED`, `DEPENDENCY_UNAVAILABLE` and `INTERNAL_ERROR`. |
| **Success** | **The form is replaced by the confirmation panel**, which says the same words for a known and an unknown address. There is no second send control on this screen — a customer who sees "sent" and presses again would be told nothing new and would consume a bucket token. |
| **Partial** | Not applicable. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | `Reset your password` |
| Body above the field | `Enter the email address on your account. If it has one, we will send a link that lets you set a new password.` |
| Email label | `Email address` |
| Primary action | `Send a reset link` |
| Confirmation panel | `If that email address has an account, a reset link is on its way to it. The link works once and expires in 30 minutes.` |
| Email empty or malformed | `Enter an email address.` |
| Rate limited | `Too many reset requests from this connection. Try again in 12 minutes.` |
| Dependency unavailable | `Password reset is unavailable right now. Try again shortly.` |
| Back link | `Back to sign in` |

**The `30` in the confirmation panel is rendered, not typed** (`P-ACC-07`). It is
`PASSWORD_RESET_TTL_SECONDS / 60` as a whole number of minutes, interpolated into the one shared
sentence that the `202` body and the reset email also use. A hard-coded `30` on this screen is a defect,
because the screen and the server would then be free to disagree about how long the link lives.

**Accessibility.** Focus order: email → primary action → back link. On success, focus moves to the
confirmation panel's heading and the panel is announced through a live region, because a customer using
a screen reader must be told the form was replaced rather than discover it by exploring.

---

### `SCR-ACC-03` · Choose a new password
**Route.** `/account/reset/confirm?token=…` · **Who reaches it.** anyone following the emailed link
· **Component basis.** `COMPONENTS.md §11`

**What the user arrives with / leaves with.** They arrive with a token in the query string. They leave
signed in with a new password, or told the link cannot be used and how to get another.

**The token is read from the query string and is never rendered on screen**, never placed in a visible
field, and never included in any client-side log or analytics call. On a successful submission the
interface replaces the URL to `/account/bookings`, so the token does not sit in the address bar or in
browser history for the next person at that machine.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| New password field | as `SCR-ACC-01` | `autocomplete="new-password"` | length on blur; enforced on the server (`P-ACC-08`) |
| Password help text | `--fr-text-xs`, `--fr-ink-muted` | visible before the field is touched | — |
| Show-password control | `--fr-accent-ink`, `--fr-text-sm` | as `SCR-ACC-01` | — |
| Primary action | `--fr-surface-accent`, `--fr-ink-on-accent` | reads `Set new password` | — |
| Request-again link | `--fr-accent-ink`, `--fr-text-sm` | shown only in the invalid-token state; opens `SCR-ACC-02` | — |

**There is no "confirm password" second field.** The show-password control does the same job with one
field instead of two, and a mismatch error on a field the customer cannot see is a worse failure than
letting them look at what they typed.

**States.**

| State | What renders |
|---|---|
| **Empty** | The form with one field and the help text. The token's validity is **not** checked before submission: a pre-check would be a second endpoint that tells an attacker whether a token is live without spending it. |
| **Loading** | The action is busy and disabled; the field stays filled. |
| **Error — password** | Field-level message, the field keeps its value, the action stays enabled. |
| **Error — token** | The form is replaced by a message naming which of the three happened — not valid, already used, or expired — and the request-again link. **The password field is removed**, because there is nothing that typing into it could achieve. |
| **Error — rate limited** | The `COMPONENTS.md §6` banner above the form: "Too many attempts from this connection. Try again in 6 minutes." **The form stays on screen with its value and the action stays enabled** — the server is the thing that says no, and a client-side countdown is a second clock that drifts from it (`SCR-ACC-01`'s stance, applied here). The number is substituted from `Retry-After` and rendered by `S7.20`. |
| **Error — dependency unavailable** | The banner: "Password reset is unavailable right now. Try again shortly." The form stays on screen. No figure is named, because a dependency outage has no computed retry instant (`S7.20`). |
| **Success** | No success screen. The customer is signed in and taken to `/account/bookings`, which is the place that proves the account is theirs again. |
| **Partial** | Not applicable. |

**Copy.**

| Where | Verbatim |
|---|---|
| Heading | `Set a new password` |
| Password label | `New password` |
| Password help | `At least 12 characters. No numbers or symbols required. Maximum 72 bytes.` — **`12` interpolates `PASSWORD_MIN_LENGTH`**; `72` is bcrypt's limit and is a literal (`P-ACC-01`) |
| Show-password control | `Show password` · `Hide password` — the same pair `SCR-ACC-01` publishes, because it is the same control on the same kind of field and a second wording would be a second convention |
| Primary action | `Set new password` |
| Token not found | `That reset link is not valid. Request a new one.` |
| Token used | `That reset link has already been used. Request a new one.` |
| Token expired | `That reset link has expired. Request a new one.` |
| Request-again link | `Request a new link` |
| Password too short | `Your password must be at least 12 characters. It does not have to contain numbers or symbols.` — **`12` interpolates `PASSWORD_MIN_LENGTH`** |
| Password too long | `Your password is too long. The limit is 72 bytes and yours is 84. Most characters count as one byte; accented and non-Latin characters count as two, three or four.` |
| Rate limited | `Too many attempts from this connection. Try again in 6 minutes.` — the figure interpolated from `Retry-After`, never typed |
| Dependency unavailable | `Password reset is unavailable right now. Try again shortly.` |
| Unhandled failure | `Something went wrong and your password was not changed. If you need help, quote a1b2c3d4.` |

**Accessibility.** Focus order: password → show-password → primary action. On the token-error state
focus moves to the message and it is announced. The heading is the page's `h1` so the screen has a
title independent of its route.

---

### `SCR-ACC-04` · My bookings
**Route.** `/account/bookings` · **Who reaches it.** a signed-in customer, manager or admin — always
showing **their own** bookings (`P-ACC-12`) · **Component basis.** `COMPONENTS.md §9` (the reference
block), `§6` (the error banner), `§0.3` (numbers), `§0.4` (money)

**What the user arrives with / leaves with.** They arrive with a session and nothing else. They leave
with a booking reference they can read out at a door, or with a route into one booking
(`SCR-ACC-05`).

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Group heading — `Upcoming` / `Past` | `--fr-font-display`, `--fr-text-lg`, `--fr-weight-bold`, `--fr-ink-strong`, `--fr-track-tight` | two sections on one page, upcoming first. **Not tabs** — a customer looking for a reference should not have to find the right tab first | — |
| Booking row container | `--fr-surface-raised`, `--fr-radius-lg`, `--fr-shadow-card`, padding `--fr-space-4`, gap `--fr-space-3` | the whole row is one link to `/bookings/{reference}` (`SCR-TKT-01`) | — |
| Movie title | `--fr-font-display`, `--fr-text-lg`, `--fr-weight-bold`, `--fr-ink-strong` | — | — |
| Showtime | `--fr-font-mono`, `--fr-text-md`, `--fr-ink` | rendered in Asia/Kolkata (`FR-ADR-018`) in `S7.19`'s **date-with-time** form — `20 Aug 2026, 2:00 pm`. The year is kept because a bookings list is read months later and out of context, and the zone is not printed because this is read on the site (`S7.19` rules 2 and the year note) | — |
| Hall name | `--fr-text-sm`, `--fr-ink-muted` | the client's word is "hall" | — |
| Seat labels | `--fr-font-mono`, `--fr-text-sm`, `--fr-ink` | e.g. `C12, C13`, **in the order `EP-ACC-07` returns them** — row letter, then seat number as an integer (`P-ACC-10`). The screen never re-sorts | — |
| Reference | `--fr-font-mono`, `--fr-text-md`, `--fr-weight-bold`, `--fr-ink-strong`, `letter-spacing: var(--fr-track-ref)` | `FR-XXXX-XXXX`. The full reference block with its perforation is on `SCR-TKT-01`; the row shows the value | — |
| Amount paid | `--fr-font-mono`, `--fr-text-md`, `--fr-ink-strong` | rendered from integer paise at render time (`FR-ADR-036`) | — |
| Row divider | `--fr-rule-quiet` | between rows within a group | — |
| Section divider | `--fr-rule` | between `Upcoming` and `Past` | — |
| Pager | `--fr-text-sm`, `--fr-accent-ink` | **one pager per group, and paging a group sends `group=`.** With no `group` the request returns the **first page of both** groups, which is the landing state. Pressing a group's pager re-requests with `group=upcoming` or `group=past` and that group's `page`, and the screen then shows **that group only**, with a control back to both. **When no `group` is named, the shared `page` applies to both arrays independently** (`P-ACC-10`) — so a route or a typed URL carrying `page=2` and no `group` shows page 2 of each, and a group with fewer pages than that renders its past-the-end zero state below rather than an error. The screen's own pagers never produce that, because pressing one always names a group; it is reachable from a typed URL and from a direct call to `EP-ACC-07` | `group`, `page` and `page_size` bounds in `P-ACC-10` |
| Pager controls | `--fr-text-sm`, `--fr-accent-ink`, hit area at least `--fr-tap-min` | two per group, each naming its own direction — the copy table publishes all four, and the two groups do not share a pair because their orderings run opposite ways (`P-ACC-11`). A control that would leave the group's range is not rendered | — |
| Pager position | `--fr-font-mono`, `--fr-text-xs`, `--fr-ink-muted`, `tabular-nums` | `Page 2 of 3`, both numbers interpolated from `page` and `ceil(total_ / page_size)` | — |
| Return control, `Show both groups` | `--fr-accent-ink`, `--fr-text-sm`, hit area at least `--fr-tap-min` | rendered only while one group is shown alone; re-requests with no `group` and `page` reset to 1 | — |

**What must not render here, at all:** a cancel control, a refund control, a "change seats" control, a
QR code, and any control that writes anything. `SRC-001 §5.4.3` is withdrawn by erratum `E-2` and
`FR-ADR-013` makes a confirmed booking final. **A cancellation control on this screen is a defect, not
a feature**, and no space is left for one.

**States.**

| State | What renders |
|---|---|
| **Empty — no bookings at all** | One line of `--fr-ink` at `--fr-text-md` on `--fr-surface-base` and a control that opens the movie listing. Not an illustration, not an apology. |
| **Empty — nothing upcoming, but past bookings exist** | The `Upcoming` heading renders with one line beneath it saying so, and the `Past` group renders normally below. **The heading is not hidden**: a customer needs to see that the system looked and found nothing, not that a section vanished. Entered when that group's `total_` is `0`. |
| **Empty — this page is past the end of that group** | **A new state, published here.** Entered when a group's array is empty and its `total_` is **greater than zero** — the group has bookings, just none on the page that was asked for (`P-ACC-10` exception 6). The heading renders, with one line beneath it and a control back to the first page; the other group renders normally. **It is a different state from the one above and must not reuse its copy**: telling a customer with two upcoming bookings that they have nothing coming up is a false statement, and `total_upcoming` is exactly what distinguishes the two. |
| **Loading** | Three `--fr-surface-inset` blocks at booking-row height, with the group headings already drawn at their final size. The layout does not resize when the data lands. |
| **Error** | The `COMPONENTS.md §6` banner replaces the list, with a retry control. The headings stay. |
| **Success** | Both groups, ordered per `P-ACC-11`. |
| **Partial** | A group whose page failed to load shows the banner in place of that group only; the other group stays on screen. A half-loaded group is never shown with some rows missing and no statement — that would read as bookings having disappeared. |
| **Session expired while on the page** | The next request returns `401`; the interface navigates to `SCR-ACC-01` with the message from `P-ACC-05` row 3. |

**Copy.**

| Where | Verbatim |
|---|---|
| Page heading | `Your bookings` |
| Group headings | `Upcoming` · `Past` |
| No bookings at all | `You have not booked anything yet.` |
| Control beside it | `See what is showing` |
| Nothing upcoming | `You have nothing coming up.` |
| Page past the end of a group | `You have upcoming bookings, but none on this page. Go back to the first page.` · `You have past bookings, but none on this page. Go back to the first page.` — **one string with the group's own word interpolated**, `upcoming` or `past`, never two strings maintained apart |
| Control beside it | `Go to the first page` |
| Pager, `Upcoming`, toward later shows | `Later showtimes` |
| Pager, `Upcoming`, back toward sooner shows | `Sooner showtimes` |
| Pager, `Past`, toward older bookings | `Older bookings` |
| Pager, `Past`, back toward recent bookings | `Newer bookings` |
| Pager position, both groups | `Page 2 of 3` — the two numbers interpolated, never typed |
| Control back to both groups, shown when one group is being paged alone | `Show both groups` |
| Reference label on a row | `Reference` |
| Amount label on a row | `Paid` |
| Seats label on a row | `Seats` |
| Load failure | `Your bookings cannot be loaded right now. Try again shortly.` |
| Retry control | `Try again` |
| Session ended | `Your session has ended. Sign in to continue.` |
| Unhandled failure | `Something went wrong. If you need help, quote a1b2c3d4.` |

**Why the two pagers use different words, which is the part that looks like an inconsistency and is
not.** The screen specified these controls and published no labels for them, so under `S1.2.1` case 3
this screen owns the words — and it was silent, which meant whoever built it would invent copy a
customer reads. They are published above, and **the two groups deliberately do not share one pair**:
`P-ACC-11` orders `upcoming` **ascending** and `past` **descending**, so the two halves of this one
screen run in opposite directions. A single shared `Next` / `Previous` pair would move the reader
forward in time in one group and backward in the other under the same word, and `Newer` / `Older`
shared across both has the same fault. **Each pager therefore names its own direction in the group's
own terms**, and no label requires the reader to work out an ordering before it means anything.

`Show both groups` is the return control the pager row specifies. It is present only while a single
group is being shown, and it returns the screen to the landing request — no `group`, and `page` reset
to 1, so the customer lands where they started rather than on page 3 of a view they cannot see.

**Accessibility.**

- Each group is a `section` with its heading as the accessible name, so a screen reader can jump
  between `Upcoming` and `Past` directly.
- Each pager control's accessible name is its visible label, and the pager exposes its position
  through the `Page 2 of 3` line rather than through a control's name — a control whose name changes
  as the page changes is announced afresh on every press.
- Each booking row is one link with an accessible name that carries what a person needs to identify it
  without entering it: `DEMO MOVIE 01, 20 Aug 2026, 2:00 pm, Hall 3, seats C12 and C13, reference
  FR-ABCD-EFGH`. The showtime is `S7.19`'s **date-with-time** form, the same function and the same
  form the row renders visually — **an accessible name is a string a customer reads and is governed by
  `S7.19` exactly as visible copy is.** It previously read `20 August 2026 at 14:00`, which broke two
  of that section's rules at once: the month spelled in full is not one of the five forms, and a
  24-hour clock never reaches a customer (rule 3). A screen reader announcing "fourteen hundred" to a
  customer who has only ever seen "2:00 pm" on the row above is the concrete cost.
- The reference is in `--fr-font-mono` with `--fr-track-ref`, and it is read character by character in
  its accessible name — the two groups of four are what makes it speakable (`COMPONENTS.md §9`).
- Focus order is document order: heading → upcoming rows → upcoming pager controls → upcoming pager
  position → past heading → past rows → past pager controls → past pager position, with
  `Show both groups` immediately after the pager of whichever group is being shown alone. **Every
  element named in that order has a published string in the copy table above** — that is the check,
  not an aspiration, and a control reachable by keyboard with no words is the defect this screen was
  corrected for once already.
- The retry control is a button, not a link, and the error region is a live region.

---

### `SCR-ACC-05` · One booking — **this is `SCR-TKT-01`, reached from the list**
**Route.** `/bookings/{reference}` · **Who reaches it.** the customer who owns it, and nobody else
(`P-ACC-12`, `P-TKT-09`) · **Specified by.** `SCR-TKT-01`, in the receipt section

**There is one booking-detail page in this product and this section does not specify it.** A customer
reaches it from a row on `SCR-ACC-04`, from the confirmation response, from a bookmark, or by typing
the reference. All four arrive at the same route and the same page.

**Why this id still exists rather than being deleted.** `SCR-ACC-04`'s rows link somewhere, and a
reader following that link needs to be told where it goes and where the specification lives. **What
this id does not carry is a second field table, a second copy table or a second route** — it had all
three, and they disagreed with `SCR-TKT-01` on the reference label, the total's label, the back link
and the not-found wording. Two specifications of one page is how two developers build two pages.

**There is no `/account/bookings/{reference}` route.** It was specified here and is withdrawn; the
account area links out to `/bookings/{reference}` rather than wrapping it.

**What this section still owns** is the **list** (`SCR-ACC-04`) — its grouping, its ordering, its
empty state and its paging. The moment a row is clicked, the receipt section owns the answer.

---

### `SCR-ACC-06` · The password-reset email
**Route.** none — it is delivered, not navigated to · **Who reaches it.** the account's own email
address, and only an address that has an account (`P-ACC-07`); it is never sent to an address that has
none · **Component basis.** none. **`tokens.css` does not apply here** — an email client does not load
the site's stylesheet, so this surface **names no design token and uses no CSS custom property**.
Naming one would be a claim that cannot be honoured. This is the same position `SCR-TKT-02` takes for
the receipt, and for the same reason.

**Who owns what, stated because two sections meet here.** `E4 P-TKT-12` owns the **sending
behaviour** — the queue message, the claim on the token row, the single-send guarantee, every retry
and dead-letter path. **This screen owns the words**, and nothing else. `P-TKT-12` enumerates what the
email carries; the strings below are those items written out. Where a string here and a description
there disagree, this is the screen spec and `P-TKT-12` is the owning P-row, so `P-TKT-12` wins on
behaviour and this row wins on the words (`S1.2`).

**What the user arrives with / leaves with.** They arrive having typed an email address into
`SCR-ACC-02` and been told the same thing whether or not it had an account. They leave with a link
that lets them set a new password once, or — if they did not ask for it — with the knowledge that
nothing has happened to their account.

**Why this is specified to the receipt's standard rather than left as a branch.** It is the only
credential-bearing message this product sends (`P-TKT-12`), and it is the sole route back into an
account whose address is taken permanently (`P-ACC-07`, `FR-ADR-012`). A vague sentence here is not a
copy defect; it is a customer who cannot tell a genuine reset from a fraudulent one.

**Fields and controls.**

| Element | Token(s) | Behaviour | Validation |
|---|---|---|---|
| Sender address | none — `SES_SENDER_ADDRESS`, required, no default (`FR-ADR-060`) | whatever identity the client has verified in SES | the process refuses to start if it is unset (`FR-ADR-053`) |
| Sender display name | none | `FrontRow` — the same name the receipt sends under, so both messages sort together in a mailbox | — |
| Recipient | none | the account's own address, read from the user row the token belongs to. **Never an address taken from the request body** | `P-TKT-12` dead-letters a message whose `user_id` does not own the token |
| Subject | none | names the product and the action, and **carries no token, no reference and no address** — a subject line is the part most likely to be shown on a lock screen | — |
| Plain-text part | none | **the authoritative part.** Every sentence below appears in it | — |
| HTML part | none | the same sentences in the same order, minimal markup | **no remote image, no web font, no tracking pixel, no external resource of any kind** |
| The link | none — the URL is rendered as text in the plain-text part and as one anchor in the HTML part | `{PUBLIC_BASE_URL}/account/reset/confirm?token=<token>` (`P-ACC-07`) | `PUBLIC_BASE_URL` is required with no default (`FR-ADR-053`) |
| The expiry figure | none | **interpolated from `PASSWORD_RESET_TTL_SECONDS / 60`** as a whole number of minutes, into the one shared sentence — see below | a literal is a defect (`P-ACC-07`) |

**The expiry is never typed, here or anywhere.** The sentence *"The link works once and expires in 30
minutes."* is **one shared string** with the minutes interpolated, and this email renders that same
string — the same one the `202` body of `EP-ACC-05` and the confirmation panel on `SCR-ACC-02` render
(`P-ACC-07`). **A literal `30` in this email is a defect**, exactly as it is on the screen, because the
email and the server would then be free to disagree about how long the link lives and the customer
would be told a lifetime the server does not honour.

**States.**

| State | What renders |
|---|---|
| **Empty** | Not applicable. An email is either sent complete or not sent. A reset email missing its link is worse than no email, because the customer stops waiting for one. |
| **Loading** | Not applicable. |
| **Error** | Not a state of this surface. A failed send renders nothing to anybody; `P-TKT-12` records what happens to the message, and rows 4 and 5 there state plainly that a customer can ask for a link and never receive one, with nobody told. |
| **Success** | The message below, both parts. |
| **Partial** | Never. |
| **Re-sent** | Does not occur. `P-TKT-12`'s claim on the token row means **one email per request**, and a second request supersedes the first token (`P-ACC-07` step 3) — so a second email carries a different link, not a repeat of the same one. |

**Copy.** Subject:

```
Reset your FrontRow password
```

Plain-text body, verbatim, with the bracketed values substituted:

```
A password reset was requested for customer@example.invalid.

Set a new password here:
https://example.invalid/account/reset/confirm?token=<the token>

The link works once and expires in 30 minutes.

If you did not ask for this, nothing has happened to your account and you do
not need to do anything.
```

The HTML part carries the same four blocks in the same order and adds nothing.

**Every sentence, and why it is worded that way.**

| Sentence | Why |
|---|---|
| `A password reset was requested for customer@example.invalid.` | **It says what happened and names the address**, which `P-ACC-07` requires, so a customer with several addresses knows which account this is about. It does not say who requested it, because the system does not know. It says "was requested", not "you requested" — attributing the request to the reader is the blame the copy rules exclude, and it is the sentence that reads as an accusation when the request was not theirs. |
| `Set a new password here:` | The action, in the imperative, immediately above the link. Not "click here" and not "please". |
| The URL on its own line | So it can be read, copied by hand, and compared against the address the customer expects — which is the only defence a reader has against a lookalike message. |
| `The link works once and expires in 30 minutes.` | **The shared string**, with the minutes interpolated. It states both limits in the order they bite. |
| `If you did not ask for this, nothing has happened to your account and you do not need to do anything.` | The reader's real question. It states the fact — nothing has changed — and then removes the obligation. **It does not tell them to contact anybody**, because there is nobody to contact: the client is the sole operator (`SRC-001 §8.2`). It does not tell them to ignore the message, because "ignore this" is advice a fraudulent message gives just as easily. |

**What this email does not carry**, stated so nothing is added out of habit:

- **No password**, current, temporary or otherwise. Nothing in this product ever mails a credential
  other than this one-use link.
- **No booking data, no booking reference and no personal detail beyond the address it is sent to**
  (`P-TKT-12`).
- **No confirmation that the address has an account**, beyond the fact that the message exists — which
  is unavoidable, since it only reaches an address that has one. `P-ACC-07`'s identical `202` is what
  keeps the *endpoint* from disclosing it.
- **No image, no logo and no tracking pixel.** A remote image is a read receipt on a credential
  message, and the HTML part loads no external resource of any kind.
- **No unsubscribe link.** This is a transactional message the customer asked for, not a mailing.
- **No second link of any kind** — no "was this you" link, no "report this" link. Every link in a
  credential message is another thing a lookalike can imitate, and neither is asked for by any source.

**Accessibility.** The HTML part is a single-column document with real paragraph and heading elements,
no layout tables and no image, so it has no alternative text to get wrong. Every fact in the HTML part
is also in the plain-text part, which is what a customer reading with a screen reader or a text-only
client receives. The link's accessible text is the URL itself rather than a word like "here", so a
screen reader user hears the address they are being sent to before they follow it — which on a
credential message is the one thing worth hearing.

---


## S6 — API endpoints

Every endpoint below returns the error envelope of `FR-ADR-052` on failure:
`{"error":{"code":"…","message":"…","details":{…},"request_id":"…"}}`. The interface branches on
`code` and never on `message`. `request_id` is shown to the customer on 5xx only.

---

Creates an account and signs the caller in with one request, so a first-time visitor returns to the
seat map immediately rather than to a second form (`P-ACC-01`).

```endpoint
{
  "id": "EP-ACC-01",
  "method": "POST",
  "path": "/api/auth/register",
  "summary": "Create a customer account and start a session",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {
      "email": "string, 3..254, trimmed, valid shape, required",
      "password": "string, at least PASSWORD_MIN_LENGTH characters (default 12) and at most 72 UTF-8 bytes, never trimmed, required"
    }
  },
  "responses": {
    "201": {"description": "Account created and session started; sets the fr_session cookie", "body": {"user_id": "integer", "email": "string, as entered", "role": "string, always customer"}},
    "409": {"description": "An account already exists for that email address"},
    "422": {"description": "A field failed validation; details names the field and, for a long password, its byte length"},
    "429": {"description": "Registration rate limit for this IP is exhausted; carries Retry-After"},
    "503": {"description": "Redis is unreachable and the rate limiter fails closed"},
    "500": {"description": "Unhandled failure; no account was created"}
  },
  "errors": ["EMAIL_ALREADY_REGISTERED", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Not idempotent by design. A repeat of the same body after a 201 returns 409 EMAIL_ALREADY_REGISTERED, because the unique index on lower(email) is the guard. Two simultaneous identical requests produce exactly one account and one 409.",
  "rate_limit": "Per IP only: 5 per hour, token bucket in Redis keyed on the real client address from the rightmost-but-one X-Forwarded-For entry. No per-user bucket exists — there is no user yet.",
  "authorisation_rule": "No authentication is required and no role is checked. The created row's role is always customer and is never read from the request body.",
  "satisfies": ["P-ACC-01", "P-ACC-03", "P-ACC-04", "P-ACC-14"],
  "brd": ["R-ACC-01", "R-ACC-03"]
}
```

---

Exchanges an email address and a password for a session cookie. The bcrypt comparison runs even when
the email is unknown, so the response time does not disclose whether an account exists (`P-ACC-03`).

```endpoint
{
  "id": "EP-ACC-02",
  "method": "POST",
  "path": "/api/auth/login",
  "summary": "Sign in and start a session",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {
      "email": "string, 3..254, trimmed, required",
      "password": "string, 1..1024, never trimmed, required — not length-validated against the password rules"
    }
  },
  "responses": {
    "200": {"description": "Signed in; sets the fr_session cookie", "body": {"user_id": "integer", "email": "string", "role": "string, one of customer, manager, admin"}},
    "401": {"description": "The email address and password do not match an account. Identical for an unknown address and a wrong password"},
    "422": {"description": "A field is missing or empty"},
    "429": {"description": "The per-email or per-IP bucket is exhausted; carries Retry-After"},
    "503": {"description": "Redis is unreachable and the rate limiter fails closed"},
    "500": {"description": "Unhandled failure"}
  },
  "errors": ["CREDENTIALS_INVALID", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Repeating the same request issues a new session cookie with a new iat and exp. The previous cookie remains valid until its own exp — there is no server-side session store to invalidate.",
  "rate_limit": "Two buckets, both must have a token: per submitted lower(email) at 10 per 15 minutes, and per real client IP at 30 per 15 minutes. Retry-After is computed from the refill rate, not a constant.",
  "authorisation_rule": "Public. The role in the response and in the token is read from the user row, never from the request.",
  "satisfies": ["P-ACC-02", "P-ACC-03", "P-ACC-05", "P-ACC-06", "P-ACC-14"],
  "brd": ["R-ACC-01"]
}
```

---

Clears the session cookie in the browser. It does not revoke the token, because the token is stateless
(`P-ACC-05`).

```endpoint
{
  "id": "EP-ACC-03",
  "method": "POST",
  "path": "/api/auth/logout",
  "summary": "Clear the session cookie",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "204": {"description": "The cookie is cleared with Set-Cookie fr_session= and Max-Age=0, carrying the same attributes it was issued with. Returned whether or not a session was present"}
  },
  "errors": [],
  "idempotency": "Fully idempotent. Calling it with no session, or twice, returns 204 both times. Signing out when not signed in is not an error.",
  "rate_limit": "none",
  "authorisation_rule": "Declared public so that a caller with an expired or malformed cookie can still clear it. A 401 here would leave a broken cookie in the browser with no way to remove it.",
  "satisfies": ["P-ACC-05"],
  "brd": ["R-ACC-01"]
}
```

---

Returns who the caller is. The interface calls it on load to decide whether to render the guest or the
customer surface; a 401 from this endpoint means "guest" and is the one 401 the interface never shows
as an error.

```endpoint
{
  "id": "EP-ACC-04",
  "method": "GET",
  "path": "/api/auth/me",
  "summary": "Return the signed-in caller's identity and role",
  "auth": "authenticated",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The caller", "body": {"user_id": "integer", "email": "string", "role": "string, one of customer, manager, admin"}},
    "401": {"description": "No session, an invalid or expired token, or a password_version mismatch. The interface reads this as guest"},
    "503": {"description": "Postgres is unreachable, so the user row behind the token cannot be confirmed"},
    "500": {"description": "Unhandled failure"}
  },
  "errors": ["AUTH_REQUIRED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "The router dependency resolves the caller from the fr_session cookie, verifies the signature and exp, and rejects the token if its pv claim does not match the user row's password_version.",
  "satisfies": ["P-ACC-05", "P-ACC-06"],
  "brd": ["R-ACC-01"]
}
```

---

Starts a password reset. The response is identical whether or not the address has an account, for the
same disclosure reason as sign-in (`P-ACC-07`).

```endpoint
{
  "id": "EP-ACC-05",
  "method": "POST",
  "path": "/api/auth/password-reset/request",
  "summary": "Send a single-use password reset link if the address has an account",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {"email": "string, 3..254, trimmed, valid shape, required"}
  },
  "responses": {
    "202": {"description": "Accepted. The body and wording are identical for a known and an unknown address. The send is asynchronous through the transactional outbox and the worker", "body": {"message": "string, the one shared sentence in P-ACC-07, whose stated lifetime is rendered from PASSWORD_RESET_TTL_SECONDS as a whole number of minutes and is never a literal"}},
    "422": {"description": "The address is missing or malformed"},
    "429": {"description": "More than 5 requests from this IP in an hour; carries Retry-After"},
    "503": {"description": "Redis is unreachable and the rate limiter fails closed"},
    "500": {"description": "Unhandled failure"}
  },
  "errors": ["VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Not idempotent, and deliberately not. Each accepted request for a known address marks every outstanding unused token for that user as used and issues one new token, so at most one live token exists per account. The most recent link is the one that works.",
  "rate_limit": "Per IP only: 5 per hour. No per-user bucket, because keying on a submitted address before authentication would let a third party exhaust a named account's bucket.",
  "authorisation_rule": "Public. No caller identity is required or used. The token is written against the user row found by lower(email) and never against anything in the request beyond that address.",
  "satisfies": ["P-ACC-07", "P-ACC-14"],
  "brd": ["R-ACC-04"]
}
```

---

Completes a password reset. The token is the credential; the old password is neither required nor
accepted (`P-ACC-08`).

```endpoint
{
  "id": "EP-ACC-06",
  "method": "POST",
  "path": "/api/auth/password-reset/confirm",
  "summary": "Set a new password using a single-use reset token",
  "auth": "public",
  "roles": ["guest", "customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {},
    "headers": {},
    "body": {
      "token": "string, exactly 43 URL-safe characters, required",
      "password": "string, at least PASSWORD_MIN_LENGTH characters (default 12) and at most 72 UTF-8 bytes, never trimmed, required"
    }
  },
  "responses": {
    "200": {"description": "The password is changed, password_version is incremented, every existing session for the account stops being accepted, and a fresh fr_session cookie is set", "body": {"user_id": "integer", "email": "string", "role": "string"}},
    "400": {"description": "The token is unknown, already used, or expired. The message names which"},
    "422": {"description": "The token is missing or the wrong length, or the new password failed the password rules"},
    "429": {"description": "The per-IP reset-confirm bucket is empty, with Retry-After in seconds. Every request to this endpoint spends a token, including one rejected for a malformed token or a failing password, so an attacker gets no free attempts"},
    "503": {"description": "Redis is unreachable and the rate limiter fails closed"},
    "500": {"description": "Unhandled failure; the password was not changed"}
  },
  "errors": ["RESET_TOKEN_INVALID", "VALIDATION_FAILED", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "Single use, enforced by a conditional update: UPDATE password_reset_token SET used_at = :now WHERE id = :id AND used_at IS NULL must affect exactly one row inside the same transaction as the password change. Two simultaneous submissions of one token produce exactly one 200 and one 400.",
  "rate_limit": "Its own bucket, RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR = 10 per hour per IP. It does NOT share the reset-request bucket: sharing would let a customer who requests a reset and then confirms it spend two of five hourly tokens and lock themselves out of recovering an account whose address is permanently taken and which has no support desk behind it. Retry-After = ceil(3600/10) = 360 seconds, rendered as 6 minutes by S7.20. Every request spends a token, including one rejected for a malformed token, so an attacker gets no free attempts; the 43-character length is still checked before any database read, so a malformed guess costs a token but no query.",
  "authorisation_rule": "Public. The token identifies the account; no session is read and no user id is accepted from the request.",
  "satisfies": ["P-ACC-08", "P-ACC-03", "P-ACC-05"],
  "brd": ["R-ACC-04"]
}
```

---

Returns the caller's own bookings in two groups. `/api/me/` always means the caller, for every role,
with no override parameter (`P-ACC-12`).

```endpoint
{
  "id": "EP-ACC-07",
  "method": "GET",
  "path": "/api/me/bookings",
  "summary": "List the caller's own bookings, upcoming and past",
  "auth": "authenticated",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {},
    "query": {
      "group": "string, one of upcoming or past, optional — when absent both groups are populated. BOTH ARRAYS ARE ALWAYS PRESENT: naming a group returns the other as [] with its total_ still populated, never omitted, so no client ever branches on whether a field exists",
      "page": "integer, 1..1000, optional, default 1. When group is absent this page number is applied to BOTH arrays independently, each against its own ordering and its own total_ count: page=2 with no group returns the second page of upcoming and the second page of past. It is never ignored and it is never a 422 on this account. The two groups have different lengths, so a page valid for one can be past the end of the other; that group's array is then empty while the other has rows, which is a 200 and not an error",
      "page_size": "integer, 1..50, optional, default 20. Applies to both arrays, as page does"
    },
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The caller's bookings. Upcoming ascending by showtime start, past descending, each with created_at and id as tie-breakers so paging is stable. When no group is named, page and page_size are applied to each array independently against its own total_, so either array may be empty while the other is full", "body": {"upcoming": "array of booking summaries, the requested page of the upcoming ordering; empty when that page is past total_upcoming", "past": "array of booking summaries, the requested page of the past ordering; empty when that page is past total_past", "page": "integer, the page applied to both arrays", "page_size": "integer, the page size applied to both arrays", "total_upcoming": "integer, the count across all pages, so a caller can tell an empty page from an empty group", "total_past": "integer, the count across all pages, so a caller can tell an empty page from an empty group", "booking.reference": "string, FR-XXXX-XXXX", "booking.movie_title": "string", "booking.hall_name": "string", "booking.showtime_starts_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30", "booking.showtime_ends_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30", "booking.seats": "array of string seat labels, ordered by row letter then seat number as an integer, per P-ACC-10 (F7, F8, F9 and never F9, F7, F8)", "booking.seat_count": "integer, 1..10", "booking.total_paise": "integer, the sum of the snapshotted per-seat prices, never a float and never a formatted string", "booking.booked_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30"}},
    "401": {"description": "No valid session"},
    "422": {"description": "A query parameter is outside its bounds"},
    "503": {"description": "Postgres is unreachable"},
    "500": {"description": "Unhandled failure"}
  },
  "errors": ["AUTH_REQUIRED", "VALIDATION_FAILED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "none",
  "authorisation_rule": "The query filters on the user id resolved by the router dependency from the session. No user id is accepted in the path, the query or the body, so there is nothing to forge. An admin calling this sees their own bookings and no one else's.",
  "satisfies": ["P-ACC-10", "P-ACC-11", "P-ACC-12"],
  "brd": ["R-ACC-02", "R-ACC-03"]
}
```

---

Returns one of the caller's own bookings by its reference. A reference that exists but belongs to
somebody else returns exactly the same 404 as one that does not exist, so the endpoint cannot be used
to probe the reference space (`P-ACC-12`).

```endpoint
{
  "id": "EP-ACC-08",
  "method": "GET",
  "path": "/api/me/bookings/{reference}",
  "summary": "Return one of the caller's own bookings by reference",
  "auth": "authenticated",
  "roles": ["customer", "manager", "admin"],
  "request": {
    "path_params": {"reference": "string, the booking reference; case-insensitive, hyphen-insensitive, whitespace-insensitive, the FR prefix optional; nothing is silently corrected"},
    "query": {},
    "headers": {},
    "body": {}
  },
  "responses": {
    "200": {"description": "The booking, with one line per booked seat carrying its snapshotted price", "body": {"reference": "string, FR-XXXX-XXXX", "movie_title": "string", "hall_name": "string", "showtime_starts_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30", "showtime_ends_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30", "seats": "array of objects with seat label, category name and price_paise as an integer, ordered by row letter then seat number as an integer, per P-ACC-10", "total_paise": "integer", "booked_at": "string, ISO-8601 with the cinema's UTC offset, e.g. 2026-08-20T14:00:00+05:30", "group": "string, upcoming or past, per P-ACC-11"}},
    "401": {"description": "No valid session"},
    "404": {"description": "No booking with that reference is on the caller's account. Identical whether the reference belongs to another customer or does not exist at all"},
    "429": {"description": "More than 20 lookups a minute for this user or 60 for this IP; carries Retry-After"},
    "503": {"description": "Postgres is unreachable"},
    "500": {"description": "Unhandled failure"}
  },
  "errors": ["AUTH_REQUIRED", "NOT_FOUND", "RATE_LIMITED", "DEPENDENCY_UNAVAILABLE", "INTERNAL_ERROR"],
  "idempotency": "safe method — no state change",
  "rate_limit": "Per user 20 per minute, per IP 60 per minute. The reference is the only thing that gets a person into a hall, so any endpoint that looks one up is an enumeration target and is limited as well as authenticated.",
  "authorisation_rule": "The query is WHERE reference = :normalised AND user_id = :caller. The ownership predicate is in the same query as the lookup, so there is no path where a row is fetched and then checked. No role is exempt: an admin and a manager are bound by the same predicate as a customer, there is no override parameter on this path, and there is no v1 endpoint anywhere by which an admin reads another customer's bookings (P-ACC-12).",
  "satisfies": ["P-ACC-10", "P-ACC-11", "P-ACC-12"],
  "brd": ["R-ACC-02", "R-ACC-03"]
}
```

---

### New error codes this epic needs

The registry in `FR-ADR-052` was written for the seat, hold, payment and dependency failures. It has no
code for a field that failed validation, for credentials that did not match, for a resource that does
not exist, or for a one-time token that has been spent. Each block below is emitted for the merge pass
to adjudicate rather than invented inline.

```newerrorcode
{"code":"VALIDATION_FAILED","http":422,"when":"a request field is missing, malformed, or outside its documented bounds, before any business rule runs","raised_by":["EP-ACC-01","EP-ACC-02","EP-ACC-05","EP-ACC-06","EP-ACC-07"],"why_needed":"FR-ADR-052 has no validation code. Without one every field error would have to reuse a code that means something else, and the interface — which branches on code, never on message — could not tell a malformed email from a lost seat. details carries the field name and, for the password, its byte length. This is almost certainly needed by every lane, not only this one."}
```

```newerrorcode
{"code":"CREDENTIALS_INVALID","http":401,"when":"a sign-in attempt does not match an account, whether because the email address is unknown or the password is wrong","raised_by":["EP-ACC-02"],"why_needed":"AUTH_REQUIRED means 'you are not signed in and this action needs a session' (FR-ADR-052 defines it as a guest trying to hold). Reusing it for a failed sign-in would make the interface show 'sign in to continue' on the sign-in screen. The two situations need different screens, so they need different codes. One code covers both failure reasons on purpose: distinguishing them would disclose which addresses have accounts (P-ACC-02)."}
```

```newerrorcode
{"code":"EMAIL_ALREADY_REGISTERED","http":409,"when":"registration is attempted for an email address that already has an account","raised_by":["EP-ACC-01"],"why_needed":"The interface must offer the sign-in tab and the reset link rather than showing a generic conflict, so it must branch on this specifically. Folding it into VALIDATION_FAILED would put a business outcome behind a shape-checking code. The disclosure this carries is unavoidable without an email-verification gate, which FR-ADR-050 rules out for v1, and it is recorded as an accepted weakness in P-ACC-01 rather than hidden."}
```

```newerrorcode
{"code":"NOT_FOUND","http":404,"when":"an addressed resource does not exist, or exists and is not the caller's","raised_by":["EP-ACC-08"],"why_needed":"FR-ADR-052 has no not-found code. On this epic it does specific security work: a booking reference belonging to another customer must produce exactly the same response as one that does not exist, because a distinguishable 403 would turn the endpoint into an oracle for probing the 30^8 reference space that FR-ADR-015 relies on. Like VALIDATION_FAILED, this is almost certainly needed project-wide."}
```

```newerrorcode
{"code":"RESET_TOKEN_INVALID","http":400,"when":"a password reset token is unknown, already used, or past its expiry","raised_by":["EP-ACC-06"],"why_needed":"The screen for a spent or expired link is not a validation screen — it removes the password field entirely and offers to send a new link, because typing into the form cannot help. One code with three messages lets the interface render that one screen and tell the customer which of the three happened. VALIDATION_FAILED would put it back on a form that cannot succeed."}
```

---

## Lane notes

### Article X candidates raised by this lane

**None.** Every question this lane hit was either ruled, covered by an `APPROVED` ADR, or a
non-reserved technical call the build session may make under Art III.9 and has logged below. Nothing
here is money, irreversible, public, secret, legal, a scope change, or a waived quality check.

Two existing open rows were touched and neither was decided:

- **`OPEN-TLS-01`** — `P-ACC-05` states that `COOKIE_SECURE` is a required variable with no default and
  is off in the deployed environment, and states the consequence (credentials and the session cookie
  cross the network in the clear). **It does not state that TLS is or will be terminated anywhere**,
  and the deployed environment is not called production.
- **`OPEN-EMAILFAIL-01`** — `P-ACC-04` and `SCR-ACC-05` state that the reference is on the confirmation
  screen and in the bookings list independently of the email, and that the dispatch record holds its
  state. **No wording is written for a customer whose receipt definitively failed and no policy is
  stated about money already taken.**

### Assumptions I had to flag

| Where | Flag | What it is, and where it bites |
|---|---|---|
| `P-ACC-06` | `ASSUMED` | **Session lifetime, `SESSION_TTL_SECONDS = 43200` — twelve hours.** No source names one. It bites at the door: a customer who booked more than 12 hours ago must sign in again to read their reference, in a cinema queue, and the mitigation is that the reference is also in the receipt email (`FR-ADR-048`). Shortening it makes that worse; lengthening it makes a shared machine worse, and lengthens the window in which a token copied off a plaintext connection can be replayed while `OPEN-TLS-01` is open. It is configuration, it is stated exactly once, and it never hardens into a rule. |
| `P-ACC-11` | `ASSUMED` | **The upcoming/past boundary is `ends_at`, not `starts_at`.** `SRC-001 §5.4.2` names the two groups and no source names the line between them. It bites for the ~2.5 hours a film is running: under this rule the booking is still "upcoming" while the customer is in the hall, which is when they are most likely to look for it. |
| `P-ACC-11` | `ASSUMED` | **The ordering and its tie-breakers.** Inferred, not ruled. The tie-breakers are not cosmetic — without a total order, paging can show one booking twice and hide another. |
| `P-ACC-03` | `ASSUMED` | **`BCRYPT_THREAD_POOL_SIZE = 2` and `BCRYPT_HASH_TIMEOUT_MS = 5000`.** No source names either. The row previously called the pool "a named configuration value" and named it nowhere, which left the setting `S7.9` requires with no name and left exception 3's timeout firing on nothing. It bites as a capacity ceiling: the pool size **is** the concurrency at which sign-in starts returning `503`, worked through in `P-ACC-03`. Phase 7's load test replaces both. |
| `P-ACC-03` | `[JUDGMENT CALL]` | **`BCRYPT_COST = 12`.** Chosen to sit near the 300 ms figure in `GOTCHAS.md`, which is itself carried forward and `[UNPROVEN HERE]`. Phase 7 measures it. On a host with roughly 1 GB of memory it is a real CPU cost and the thread pool size is its companion tuning value. |
| `P-ACC-07` | `[JUDGMENT CALL]` | **`PASSWORD_RESET_TTL_SECONDS = 1800`**, which is thirty minutes and is the figure every customer-visible sentence renders from, and the 43-character token length from 32 random bytes. |
| `P-ACC-13` | `[JUDGMENT CALL]` | **The 30-minute staleness discard** on the stored seat selection. |
| `P-ACC-01` | `[JUDGMENT CALL]` | **What `password_hash` holds for an account with no usable password** — a per-row bcrypt hash of 32 discarded random bytes, in a `NOT NULL` column. No source says. It bites on `P-ACC-03`: the alternatives, a nullable column and one shared sentinel string, both create something the sign-in path or a database reader can branch on, and the first would destroy the timing equalisation outright. Chosen because it leaves nothing to branch on rather than relying on nobody adding a branch. |
| `SCR-ACC-06` | `[JUDGMENT CALL]` | **The reset email's exact sentences**, including the subject line. `E4 P-TKT-12` enumerates what the message must carry and no source writes the strings. They are written here to the receipt's standard because this is the only credential-bearing message in the product; the expiry figure inside them is interpolated, never typed. |
| `P-ACC-10` | `[JUDGMENT CALL]` | **`page` applies to both arrays independently when no `group` is named**, each against its own `total_`, and it is neither ignored nor a `422`. No source says, because no source contemplates two paged collections behind one parameter. **Reversible** — the alternatives were to ignore `page` (rejected: silently discarding a parameter a caller sent is the failure mode that takes longest to notice) and to `422` it (rejected: nothing about the request is out of bounds). It costs one new screen state on `SCR-ACC-04`, for the page that is past the end of one group but not the other, because reusing "You have nothing coming up." there would state something false. |
| `P-ACC-05` | `[JUDGMENT CALL]` | **The `pv` password-version claim and the per-request user-row read.** It is what makes a stateless session revocable on a password change. Its cost is one primary-key read per authenticated request. |
| Carried, not mine | `PROVISIONAL` | **Four roles** (`SRC-003 C-1`) — `P-ACC-12` and every endpoint's `roles` array rest on `customer`, `manager` and `admin` existing as distinct roles. If the client collapses them, the `roles` arrays change and nothing else does. |
| Carried, not mine | `PROVISIONAL` | **Sales close 15 minutes *after* the advertised start** (`FR-ADR-042`). It reaches this lane through `P-ACC-11`: because a showtime can still be selling after it has started, classifying a booking by `starts_at` would have been wrong in a second, independent way. If the client reverses the direction, `P-ACC-11` is unaffected — it compares against `ends_at`. |

### Durations this section publishes, checked against **both halves** of `S7.20`

`S7.20` owns the rule and this section owns none of it. It has **two halves, and a string has to
satisfy both**:

1. **Derivation.** `Retry-After` is the time until the refusing bucket next holds one token, taken
   from **whichever bucket refused**. `ceil(window_seconds / capacity)` is that figure at the instant
   the bucket empties, so it is the **maximum** a bucket can ever produce and not the value — a caller
   who retries part-way through the interval is told the remainder, which is less.
   *(Corrected 2026-08-23: this clause stated the maximum as if it were the derivation, which made it
   disagree with `S7.20`, the owner this very sentence names, and with `P-ACC-14`'s own worked example
   of 60 at t=30s against a 90-second maximum.)* It is not the bucket's capacity and it is not its
   window. Where two limiters guard one endpoint, a row publishing one figure **must name its bucket**.
2. **Rendering.** `"<n> seconds"` below 120; `"<m> minutes"` with `m = ceil(seconds / 60)` at 120 and
   above; singular at 1.

Every figure below is computed from its bucket (`P-ACC-14`) and never typed into the copy. **All five
strings this section already published are conformant on both halves; one bucket had no published
string at all and now has one** (`P-ACC-12` row 5).

| String, as published here | Bucket and derivation | Rendering | Verdict |
|---|---|---|---|
| `"Too many accounts have been created from this connection. Try again in 12 minutes."` — `P-ACC-01` exception 8 | registration per IP, `RATE_LIMIT_REGISTER_IP_PER_HOUR` = 5 over 3600 s → `ceil(3600/5)` = **720** | 720 ≥ 120 → `ceil(720/60)` = 12 minutes | **conformant on both** |
| `"Too many sign-in attempts for that email address. Try again in 90 seconds."` — `P-ACC-02` exception 4, `SCR-ACC-01` copy, `P-ACC-14` worked example | sign-in per email, `RATE_LIMIT_LOGIN_USER_PER_15MIN` = 10 over 900 s → `ceil(900/10)` = **90** | 90 < 120 → seconds | **conformant on both.** This is the string the 120 threshold exists for: at a 60-second threshold it would read "2 minutes" and overstate the wait by a third |
| `"Too many sign-in attempts from this connection. Try again in 30 seconds."` — `P-ACC-02` exception 5 | sign-in per IP, `RATE_LIMIT_LOGIN_IP_PER_15MIN` = 30 over 900 s → `ceil(900/30)` = **30** | 30 < 120 → seconds | **conformant on both.** Note it is 30, the refill interval, and **not 900**, the window — the pair that caught out another lane |
| `"Too many reset requests from this connection. Try again in 12 minutes."` — `P-ACC-07` exception 4, `SCR-ACC-02` copy | reset per IP, `RATE_LIMIT_RESET_IP_PER_HOUR` = 5 over 3600 s → `ceil(3600/5)` = **720** | 720 ≥ 120 → 12 minutes | **conformant on both** |
| `"Too many attempts from this connection. Try again in 6 minutes."` — `P-ACC-08` exception 8, `SCR-ACC-03` copy, **added this pass** | reset confirm per IP, `RATE_LIMIT_RESET_CONFIRM_IP_PER_HOUR` = 10 over 3600 s → `ceil(3600/10)` = **360** | 360 ≥ 120 → `ceil(360/60)` = 6 minutes | **conformant on both.** The endpoint claimed a limit and published no `429` anywhere; the bucket, the row and the string are all new |
| `"Too many lookups. Try again in 3 seconds."` — `P-ACC-12` exception 4 | booking lookup per user, `RATE_LIMIT_LOOKUP_USER_PER_MIN` = 20 over 60 s → `ceil(60/20)` = **3** | 3 < 120 → seconds | **conformant on both** |
| `"Too many lookups. Try again in 1 second."` — `P-ACC-12` exception 5, **added in this pass** | booking lookup per IP, `RATE_LIMIT_LOOKUP_IP_PER_MIN` = 60 over 60 s → `ceil(60/60)` = **1** | 1 < 120 → seconds, **singular** | **conformant on both.** The bucket existed on `EP-ACC-08` and had no published string; one of the four `S7.20` names as reaching 1, so the singular ships |

**Why the derivation half is checked separately and first.** A wrong figure that renders correctly
reads as trustworthy, which is how a bucket's capacity or its window ends up in copy that wants its
refill interval. That defect was found in four lanes across the document and in **one string in this
lane's sibling section** — `E4`'s `"Try again in 45 seconds."`, for the same lookup buckets this
section derives 3 and 1 from. The figures here were re-derived from the variable names rather than
re-read.

Every other occurrence of *seconds* or *minutes* in this section is either a configuration value
rendered from its own named variable — `PASSWORD_RESET_TTL_SECONDS / 60` as "30 minutes", which
`P-ACC-07` already rules is interpolated and never typed — or arithmetic in a worked example. `S7.20`
governs published `Retry-After` copy, so neither is inside either half, and `P-ACC-07`'s own
interpolation rule is untouched by it.

### Where I would have had to guess and did not

Each of these is a question no frozen source, ruling or `APPROVED` ADR answers. None is reserved, so
none became an Article X row; each is either logged as a judgment call above or handed to the lane that
owns it. **They are listed because the next reader needs to know which numbers in this document were
decided here rather than inherited.**

1. **How long a session lasts.** `SRC-002 §4.8` says "JWT" and stops. `FR-ADR-050` rules the cookie's
   flags and says nothing about lifetime. I did not treat `SESSION_TTL_SECONDS = 43200` (twelve hours)
   as ruled; it is `ASSUMED`, it is stated in exactly one place, and it is flagged (`P-ACC-06`).
2. **Whether a session survives a password change.** No source says. Rather than assume either way I
   specified the mechanism (`pv`) and stated both consequences, because the alternative — a reset that
   leaves an attacker signed in — is a security outcome nobody would have chosen deliberately.
3. **What separates upcoming from past.** `SRC-001 §5.4.2` names the two groups and no source draws the
   line. Flagged `ASSUMED` with a worked example so the client can see exactly what they are reversing
   (`P-ACC-11`).
4. **Whether an account lockout exists after repeated failed sign-ins.** No source names a threshold,
   and a lockout threshold is a policy. **I did not invent one.** The token bucket is a throttle that
   refills, and the denial-of-service consequence of keying it on a submitted email address is stated
   rather than designed around (`P-ACC-02`).
5. **Whether registration collects a name.** No source asks for one. I did not add a `name` column,
   because a field nobody asked for becomes a required field somebody has to fill in. `SRC-001 §6.6`
   means adding one later is a migration, not a redesign.
6. **What the receipt email looks like, what the resend control does, and what its rate limit is.**
   `FR-ADR-048` places a resend control on this page and names no bucket; `FR-ADR-058`'s table has no
   row for it. **That is the receipt epic's to specify and I did not specify it** — `SCR-ACC-05` names
   the seam and renders the reference block to `COMPONENTS.md §9` without redefining it.
7. **Whether an admin can look up another customer's booking.** No source asks for it. I did not add an
   override parameter to `/api/me/`; I stated that no such endpoint exists in v1 and that adding one is
   a new specification with its own audit row (`P-ACC-12`).
8. **What a customer whose receipt definitively failed is told.** `OPEN-EMAILFAIL-01`, reserved, open.
   No sentence written (`P-ACC-04`, `SCR-ACC-05`).
9. **Whether the deployed environment will have TLS.** `OPEN-TLS-01`, deferred. I stated only what
   `FR-ADR-069` already holds: `COOKIE_SECURE` is environment-driven, has no default, and is off in the
   deployed environment until the row closes.
10. **The value of `PAYMENT_SIMULATED_DELAY_MS`.** `FR-ADR-041` says "a small number of seconds"
    and gives no figure. `P-ACC-15` names the term inside the two-minute budget and does not put a
    number on it — that belongs to the payment epic. **The variable is milliseconds even though the
    record's prose says seconds**: `_MS` is the name in `S7.9`'s configuration table, in `FR-ADR-053`'s
    required-variable list and in every payment row, and this section earlier wrote
    `PAYMENT_SIMULATED_DELAY_SECONDS`, which is a name that exists nowhere and would have been read as
    a thousand-fold larger delay.
11. **What an account with no usable password holds in `password_hash`.** No source says, and the
    question only arises because `E6 P-ADM-17` creates one. The answer is written into `P-ACC-01`
    rather than left to a handler, because the two obvious alternatives both weaken `P-ACC-03`'s
    timing property — which is a real security property and not a detail. Logged as a judgment call,
    not presented as ruled.
12. **The reset email's words.** `E4 P-TKT-12` lists what the message carries and writes none of it
    out; nothing else in this document did either, which left the product's only credential-bearing
    message with no verbatim copy while the receipt had a full one. `SCR-ACC-06` writes the subject
    and every sentence. **The seam is stated on both sides**: `P-TKT-12` keeps the sending behaviour,
    this section keeps the words, and neither restates the other.

### Contradictions found against a frozen source, an ADR, or the BRD

**One, and it is a gap rather than a conflict.**

**`FR-ADR-058`'s rate-limit table has no row for the receipt resend control that `FR-ADR-048`
requires.** `FR-ADR-048` states that the resend control "is rate-limited per booking"; `FR-ADR-058`
enumerates every limited endpoint and the resend is not among them. Both records are `APPROVED` and
neither is wrong — the second was written about the endpoints that existed when it was written. **The
missing bucket is a real gap on the surface this lane renders** (`SCR-ACC-05`), and it belongs to the
receipt epic to fill. Naming it here rather than filling it in, because inventing a bucket for another
lane's endpoint is exactly the convergence this lane structure exists to prevent.

**Two things that look like contradictions and are not**, recorded so a reviewer does not re-open them:

- **`SRC-001 §5.4.3` (cancel a booking) against `SRC-001 §5.4.2` (view bookings).** Not a conflict —
  `§5.4.3` is **withdrawn** by erratum `E-2`. `SRC-001 §5.4.2` stands alone and this lane implements
  only it. A bookings list with a cancel control would be a spec derived from a withdrawn clause.
- **`SRC-002 §8.4.1` names only seat selection and booking, while `P-ACC-14` limits four more
  endpoints.** Not a conflict — extending a control is stricter, and Art III.10 makes a stricter
  adoption need no signature. `FR-ADR-058` already made this call and this lane follows it.
