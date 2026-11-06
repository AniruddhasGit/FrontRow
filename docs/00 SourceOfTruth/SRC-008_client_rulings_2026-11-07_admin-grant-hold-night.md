# SRC-008 — FrontRow client rulings, sixth batch: admin grants by email, the hold default, approvals for the night run

```
Source type ....... Client rulings, typed in chat and structured answers
Received .......... 2026-11-07 (the night of 2026-11-06), build session chat
Author ............ Aniruddha Jathar (the client)
Status ............ FROZEN — never edited
Citation form ..... SRC-008 <ROW-ID>
Supersedes ........ SRC-003 C-1 where it fixes how an admin account comes to exist; the S-SCP-06 register clause;
                    the S-SEA-07 'boot exits non-zero when SEAT_HOLD_TTL_SECONDS is absent' clause
```

> **FROZEN INPUT. DO NOT EDIT.** Ruling blocks are the client's words verbatim, or the option they
> selected. Anything under `Filed as` is the build session's reading and is **not** client text.
> The only permitted modification is a clearly marked `ERRATUM` appended at the foot.

## ROLE-1 · Admins are granted by email, by an existing admin · `RULED` · reserved (scope)

**Asked:** the register request carrying `role: admin`. S-SCP-06 (refuse with an error) and S-ACC-01 (ignore it and
create a customer) disagreed.

**Ruling (typed):** *"no only an existing admin can make someone an admin by typing their email into a section in
setting, this way that email whenever they sign up or login they are given admin access. this asnwer overrides the
older ruling and make change sin the docs aswell for this statement on mine."*

**Filed as:**
- **A request can never make an admin.** A role sent by anyone in a register or login request is still ignored; the
  account is a customer (S-ACC-01 stands). The S-SCP-06 "refuse" clause is superseded.
- **New: an admin-only Settings section, "Admin access".** An existing admin types an email address to grant admin. The
  list shows every granted email, and an admin can remove one. Every grant and removal is a privileged write and
  writes its audit row in the same transaction (the invariant).
- **Effect:** when someone signs up or signs in with a granted email (compared case-insensitively, trimmed), their
  account's role becomes `admin`.
  - **This is done on the server, at that moment.** An account that already exists becomes admin at its next sign-in.
- **Not ruled, so not built:** whether removing a grant demotes an account that is already admin.
  - Built conservatively: removal stops future promotion and does **not** demote (no silent loss of access).
  - The question is logged for the client.
- **Manager accounts:** whether a granted manager becomes admin (and loses their manager scope) is not ruled either.
  - Built conservatively: a grant promotes customers only; a manager account is left as it is, and the list says so.
- **Supersedes** `SRC-003 C-1`'s implication that admins exist only by seed. The four roles stay four.

## HOLD-1 · A missing hold setting defaults to 180 seconds · `RULED`

**Asked:** S-SEA-07 says boot must exit when `SEAT_HOLD_TTL_SECONDS` is absent; PRD S7.9 and the code default it to 180.

**Ruling (selected):** *"Default to 180 seconds."*

**Filed as:** `config.py` keeps its default of 180 (the ruled 3 minutes, `SRC-003 OPEN-HOLD-01`). The S-SEA-07 clause
"boot exits non-zero when SEAT_HOLD_TTL_SECONDS is absent" is superseded. An explicitly set value outside the allowed
range is still refused at boot.

## NIGHT-1 · Approvals for the overnight run · `RULED` · reserved (irreversible, public)

**Ruling (selected, four answers):**
- *"Yes, re-seed and deploy"*: re-seed the live Neon database to the CR-003 layouts (this removes the 11,003 demo
  bookings), then one batched Render deploy.
- *"Approve CR-002"*: the acceptance-criterion wording fixes.
- *"Amend both to USD"*: the 15 acceptance criteria that still say ₹, and `CONSTITUTION.md`'s INR.
- *"Yes, run all of it"*: Docker tests, building the missing pieces, the phone fixes, halls 4–6, re-seeding Neon,
  committing and pushing to both repositories, and one Render deploy at the end.

**And (typed):** *"yes the windows will not sleep until the thing is not build once everything is build and the
github is uptodate and the website is on render then you can sleep the laptop."*

**Filed as:**
- Sleep on mains power stays off for the run. The laptop is put to sleep only after the build is done, both
  repositories are pushed and the Render site is updated.
- None of this waives a quality check:
  - tests are written first;
  - no test is skipped or deleted to reach green;
  - the 50-request concurrency proof stays green;
  - any red gate is reported, not hidden.

---

## ADDENDUM (same session, before freezing) · ROLE-1 clarified, and WAIT-1 · `RULED`

**Ruling (selected), on ROLE-1's two unruled points:**
- Removing an email: *"Yes, demote to customer."*
- A granted email on a manager account: *"Becomes admin."*

**Filed as (replaces ROLE-1's two "built conservatively" bullets above):**
- **Removing a grant demotes at once.** An admin account whose email is removed from the list becomes a customer
  immediately, in the same transaction as the removal and its audit row.
- **The seeded admin is not on the list and cannot be demoted this way.** This is the build session's reading, so
  the system is never left with no admin. Likewise, an admin cannot remove their own email.
- **A granted email on a manager account makes it admin** at its next sign-in. Its hall assignments are kept, unused.

## WAIT-1 · The cold-start screen lets visitors explore a hall · `RULED`

**Ruling (typed):** *"the render page when idle takes time to load yes. Make them be able to explore the theatre hall
view we made available to see and on the screen it will display the timer of 90 sec and reson as to why it is taking
time, make it look beautiful and premium."* **Hall (selected):** *"Hall 6 Grand."*

**Filed as:**
- While the Render API wakes from idle, the site shows the baked Grand hall, free to explore by drag or touch.
- The cinema screen shows a 90-second countdown and, in plain words, why: the free server sleeps when unused and is
  starting up.
- The normal site appears the moment the API answers.
