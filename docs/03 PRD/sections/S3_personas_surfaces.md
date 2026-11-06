# S3 — Personas, roles, and the surface inventory

---

## S3.1 The four roles

> ## ⚠ `PROVISIONAL` — one message from the client reverses this
> `[SRC: SRC-003 C-1 · SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-SCOPE-01 · SRC-003 OPEN-REPORT-01 ·
> SRC-003 OPEN-OPS-03 · SRC-001 §E E-1 · FR-ADR-009]`
>
> This is a **build-session reading that reconciles two of the client's own answers**, not a literal
> answer. `SRC-003 C-1` records it, including the reading that was rejected. **Read `C-1` before
> relying on anything in this section.**

`SRC-001 §4` named five user types. `SRC-002 §3.1` implied one. Under `CONSTITUTION.md` Art II.2 that
is a contradiction inside the client's own instructions and the build session may not pick a
favourite, so it went back as `OPEN-ROLE-01`.

**The answer created a second contradiction inside itself.** `OPEN-ROLE-01` says *"do not make more
personas… only 1 admin persona. admin can do all the stuff the managers can do."* The very next
answer, `OPEN-SCOPE-01`, describes *"2 managers per cinema hall"* who *"can see earnings movies for
the day, month, week and cannot add the new movies"*, and `OPEN-REPORT-01` gives managers a dashboard.

**Read as four roles.** The prohibition is aimed at the cinema-staff and door-scanner persona, which
the same sentence kills explicitly, and at admin *tiers* — not at managers, whom two later answers
describe in operational detail. *"Admin can do all the stuff the managers can do"* states that admin
is a superset of manager, which presupposes that manager exists.

**The rejected reading** was three roles, with the manager dashboard served to admins filtered by
hall. It satisfies `OPEN-ROLE-01` literally, and it discards "2 managers per cinema hall" entirely and
puts twelve people on one shared admin account — which destroys the business's ability to answer who
changed what, because every audit row would name the same actor.

| Role | Account | What they can do | Modelled as |
|---|---|---|---|
| **guest** | none | browse movies, showtimes and the seat map. **Cannot hold and cannot book** | the absence of a session; not a row |
| **customer** | required | hold seats, pay, view their own bookings and receipts | `user.role = 'customer'` |
| **manager** | required | **read only** — the dashboard for the screens they are assigned to | `user.role = 'manager'` + `manager_screen_assignment` |
| **admin** | required | everything, including everything a manager can do | `user.role = 'admin'` |

**Roles are one column on the user row**, not a many-to-many table (`FR-ADR-050`). The four are
mutually exclusive; admin is a superset of manager **by capability, not by composition**, so a role
table would model a combination that cannot exist.

**Four are modelled rather than three because collapsing a role later is a migration and adding one
later is a rewrite of every authorisation dependency.** The wider set is the safer error.

**If the client reverses this to three roles**, the `manager` role value, the assignment table and the
manager router are removed and the dashboard is served to admins with a screen filter. That is a
contained change, and it is why the reading was recorded rather than buried.

## S3.2 The two personas that no longer exist

`[SRC: SRC-001 §E E-1 · SRC-003 OPEN-TICKET-02 · FR-ADR-009]`

**There is no cinema-staff role and no door scanner.** `SRC-001 §4.3` — withdrawn by erratum `E-1` —
described a staff member checking customers in by scanning a ticket code, and `§5.5.3`, withdrawn by
`E-3`, had staff validating tickets at the door. **Both are dead text and neither is live authority.**

**Entry is a person at the entrance reading the booking reference from the customer's emailed receipt
and checking it by hand** (`P-TKT-06`, `P-SCP-10`). There is no scanning device, no validation
endpoint, and nothing that marks a reference as used.

## S3.3 A manager writes nothing, and that is a rule and not a default

`[SRC: SRC-003 OPEN-OPS-03 · SRC-001 §7.4 · FR-ADR-009 · FR-ADR-011]`

The client ruled: *"the admin will only be the one who does changes in movie, cancel a show or other
priviledged things..no other persona."*

**A manager endpoint that writes anything is a defect, not a feature. There is no small, safe write.**

`OPEN-SCOPE-01`'s *"add more stuff that managers can do"* is read as **more reporting only**, because
`OPEN-OPS-03` puts every write on the admin. Anything beyond reporting is a proposal for the client to
approve, never assumed scope — and this document proposes none.

## S3.4 A manager sees their own screens and nobody else's

`[SRC: SRC-001 §4.4 · SRC-003 OPEN-SCOPE-01 · SRC-003 C-2 · FR-ADR-011]`

- Scope attaches to the **screen**, not to the cinema. That matches the ruling's own words —
  *"different managers for different cinema hall"* — and it is the **stricter** option: with one
  cinema, cinema-level scoping would scope nothing and the access-control test would pass vacuously
  while protecting nothing.
- **"Two managers per hall" is an observation of the client's current staffing, not a constraint.**
  No check constraint, no trigger and no application rule enforces the number two. The schema permits
  one, three or zero. Making it a rule would turn every legitimate staffing change into a migration.
- **A manager may be assigned to more than one screen.**
- **A manager with no assignment sees an empty dashboard. That is the correct state for a new
  account, not an error, and it must not render as one.**

**How this is tested** (`CONSTITUTION.md` Art VI.5): assign manager A to screen 1, create bookings on
screens 1 and 2, then assert A's dashboard returns a **non-empty, non-zero** figure for screen 1 and a
denied result for screen 2. **Both halves are required.** A test asserting only "denied" passes
against a query that returns nothing for anybody.

## S3.5 Authorisation is applied once, on the router

`[SRC: SRC-001 §7.4 · CONSTITUTION.md Art VI.4 · FR-ADR-009 · FR-ADR-011]`

Every endpoint in `S6` carries an `authorisation_rule`. **That rule is enforced by a dependency
attached to a router, never by a check inside a handler.** A per-handler check is the pattern that
eventually misses one, and `SRC-001 §7.4` requires that staff and management functions are not
reachable by customers.

There are four routers, and the boundary between them is the authorisation model:

| Router | Prefix | Endpoints | Dependency |
|---|---|---|---|
| public | `/api/movies`, `/api/showtimes`, `/api/reference`, `/api/auth` | 12 | none — no session required |
| customer | `/api/me`, `/api/bookings`, `/api/holds`, `/api/auth/me` | 10 | a valid session, **and the resource's owner must be the caller** |
| reporting | `/api/reports` | 3 | role `manager` or `admin`; the dependency resolves the caller's assigned screen ids and **every query filters on that set**. One route inside it, `/api/reports/audit`, narrows further to `admin` |
| admin | `/api/admin` | 30 | role `admin` only. **Every privileged write in the product is behind this one prefix** |
| operational | `/health`, `/metrics` | 3 | none, and **not routed to the public through the load balancer** |

**One route is admin-only without sitting under `/api/admin`**: `EP-RPT-04` `GET /api/reports/audit`,
the change log. It is a **read**, so it belongs to the reporting router by shape, and it narrows to
`admin` because `SRC-003 OPEN-OPS-03` gives reading the audit trail to the admin alone. Recorded here
because a reviewer checking "everything admin-only is under `/api/admin`" would otherwise read it as a
misplacement.

**The manager router resolves the screen set in the dependency, never from a screen id in the
request.** A handler that reads a screen id from the request and checks it itself is the pattern this
rule exists to prevent. An admin runs the same queries with **no** screen filter — that difference,
and not an assignment row, is what makes an admin a superset of a manager.

**A manager who reaches an admin write path receives `FORBIDDEN` (403) from the router**, before any
handler runs.

## S3.6 The capability matrix

`✓` permitted · `—` not permitted · `∅` the capability does not exist in v1

| Capability | guest | customer | manager | admin | Spec |
|---|---|---|---|---|---|
| Browse published movies inside their display window | ✓ | ✓ | ✓ | ✓ | `P-BRW-01` |
| See showtimes, including one marked closed | ✓ | ✓ | ✓ | ✓ | `P-BRW-07` |
| See the seat map | ✓ | ✓ | ✓ | ✓ | `P-BRW-09` |
| Select seats in the interface — no server state, no lock | ✓ | ✓ | ✓ | ✓ | `P-SEA-01`, `P-SEA-03` |
| **Hold seats** | **—** | ✓ | ✓ | ✓ | `P-HLD-01`, `P-HLD-05` |
| Pay and confirm a booking | — | ✓ | ✓ | ✓ | `P-PAY-01` |
| See their own bookings and references | — | ✓ | ✓ | ✓ | `P-ACC-10` |
| See **another** customer's booking | — | — | — | — | `P-ACC-12` |
| Cancel a booking or obtain a refund | ∅ | ∅ | ∅ | ∅ | `P-SCP-11` |
| Read the dashboard for **assigned** screens | — | — | ✓ | ✓ | `P-RPT-02` |
| Read the dashboard for **every** screen | — | — | — | ✓ | `P-RPT-02` |
| Export any report or booking data | ∅ | ∅ | ∅ | ∅ | `P-SCP-14`, `P-RPT-10` |
| Create or edit a film | — | — | **—** | ✓ | `P-ADM-01`, `P-ADM-02` |
| Upload a poster | — | — | **—** | ✓ | `P-ADM-03` |
| Set a display window · publish · unpublish | — | — | **—** | ✓ | `P-ADM-04`, `P-ADM-05`, `P-ADM-06` |
| Create a showtime | — | — | **—** | ✓ | `P-ADM-07` |
| Set a showtime's base price | — | — | **—** | ✓ | `P-ADM-10` |
| Change a seat category's uplift | — | — | **—** | ✓ | `P-ADM-11` |
| Configure a hall's seats and categories | — | — | **—** | ✓ | `P-ADM-13` |
| Create a manager or assign a screen | — | — | **—** | ✓ | `P-ADM-17` |
| Read the change log | — | — | **—** | ✓ | `P-RPT-11` |
| Withdraw a showtime that has bookings | ∅ | ∅ | ∅ | ∅ | `P-SCP-18` — **`OPEN`** |
| Validate a ticket at the door | ∅ | ∅ | ∅ | ∅ | `P-SCP-10` |

**Every `—` in a manager column is `SRC-003 OPEN-OPS-03` doing its work.** Every `∅` is either an
exclusion in `S2.4` or an `OPEN` row, and neither may be quietly filled in.

## S3.7 What each persona arrives wanting, and leaves with

| Persona | Arrives wanting | Leaves with | Fails if |
|---|---|---|---|
| **Guest** | to know what is on and whether a good seat is free | either a decision to register, or an answer | they must register before they can see whether a seat is free |
| **Customer, first visit** | a specific seat at a specific showtime | a booking reference on screen and a receipt on its way | they lose their selection at the registration step (`P-ACC-05`) |
| **Customer, returning** | the same, faster | the same, inside two minutes (`SC-1`) | the seat map lags, or the three minutes runs out unannounced |
| **Customer, at the door** | to get in | to be let in on the reference | the receipt never arrived — **`OPEN-EMAILFAIL-01`, unruled** |
| **Manager** | last night's numbers for their halls | occupancy, takings and per-film performance for **their** screens | they can see another manager's halls, or their own dashboard returns nothing and reads as an error |
| **Admin** | a film on sale by Friday | a published movie with showtimes and prices | a change they made is not attributable to them (`P-ADM-11`) |
| **Operator** *(the same person as the admin, `R-CON-02`)* | to know the product is up, and to find an incident a customer described | one alarm, a request id, and an honest list of what nobody is watching | they believe one alarm is monitoring (`S7.14`) |

## S3.8 The route inventory

*Generated from the `endpoint` blocks in `S6`, which are also the source of
`api/contract.json`. **`generate_api.py --inventory` fails if this table and the contract
disagree** — a check added after this table silently went stale at 53 while claiming it could
not.*

**61 endpoints**, grouped by the router each sits behind (`S3.5`). An endpoint appears
once, under the **narrowest** router that admits it.

**Public — no session required** — 12

| Id | Method | Path | Who |
|---|---|---|---|
| `EP-ACC-02` | `POST` | `/api/auth/login` | anyone |
| `EP-ACC-03` | `POST` | `/api/auth/logout` | anyone |
| `EP-ACC-06` | `POST` | `/api/auth/password-reset/confirm` | anyone |
| `EP-ACC-05` | `POST` | `/api/auth/password-reset/request` | anyone |
| `EP-ACC-01` | `POST` | `/api/auth/register` | anyone |
| `EP-BRW-01` | `GET` | `/api/movies` | anyone |
| `EP-BRW-02` | `GET` | `/api/movies/{movie_id}` | anyone |
| `EP-BRW-03` | `GET` | `/api/movies/{movie_id}/poster` | anyone |
| `EP-BRW-07` | `GET` | `/api/reference` | anyone |
| `EP-BRW-04` | `GET` | `/api/showtimes` | anyone |
| `EP-BRW-05` | `GET` | `/api/showtimes/{showtime_id}` | anyone |
| `EP-BRW-06` | `GET` | `/api/showtimes/{showtime_id}/seatmap` | anyone |

**Customer — a session, and the caller's own resources** — 10

| Id | Method | Path | Who |
|---|---|---|---|
| `EP-ACC-04` | `GET` | `/api/auth/me` | any signed-in user |
| `EP-PAY-01` | `POST` | `/api/bookings` | any signed-in user |
| `EP-TKT-01` | `GET` | `/api/bookings/by-reference/{reference}` | any signed-in user |
| `EP-TKT-02` | `POST` | `/api/bookings/by-reference/{reference}/resend-receipt` | any signed-in user |
| `EP-HLD-04` | `DELETE` | `/api/holds/{hold_token}` | customer / manager / admin |
| `EP-HLD-02` | `GET` | `/api/holds/{hold_token}` | customer / manager / admin |
| `EP-HLD-03` | `DELETE` | `/api/holds/{hold_token}/seats/{seat_id}` | customer / manager / admin |
| `EP-ACC-07` | `GET` | `/api/me/bookings` | any signed-in user |
| `EP-ACC-08` | `GET` | `/api/me/bookings/{reference}` | any signed-in user |
| `EP-HLD-01` | `POST` | `/api/showtimes/{showtime_id}/holds` | customer / manager / admin |

**Reporting — manager and admin, screen-scoped** — 3

| Id | Method | Path | Who |
|---|---|---|---|
| `EP-RPT-01` | `GET` | `/api/reports/dashboard` | manager / admin |
| `EP-RPT-03` | `GET` | `/api/reports/scope` | manager / admin |
| `EP-RPT-02` | `GET` | `/api/reports/showtimes` | manager / admin |

**Admin only — every privileged write, plus the change log** — 33

| Id | Method | Path | Who |
|---|---|---|---|
| `EP-ADM-30` | `GET` | `/api/admin/admin-grants` | admin |
| `EP-ADM-31` | `POST` | `/api/admin/admin-grants` | admin |
| `EP-ADM-32` | `DELETE` | `/api/admin/admin-grants/{grant_id}` | admin |
| `EP-ADM-28` | `GET` | `/api/admin/cinemas` | admin |
| `EP-ADM-29` | `PATCH` | `/api/admin/cinemas/{cinema_id}` | admin |
| `EP-ADM-25` | `GET` | `/api/admin/lookups/{kind}` | admin |
| `EP-ADM-26` | `POST` | `/api/admin/lookups/{kind}` | admin |
| `EP-ADM-27` | `PATCH` | `/api/admin/lookups/{kind}/{id}` | admin |
| `EP-ADM-22` | `GET` | `/api/admin/managers` | admin |
| `EP-ADM-23` | `POST` | `/api/admin/managers` | admin |
| `EP-ADM-24` | `PUT` | `/api/admin/managers/{user_id}/screens` | admin |
| `EP-ADM-01` | `GET` | `/api/admin/movies` | admin |
| `EP-ADM-02` | `POST` | `/api/admin/movies` | admin |
| `EP-ADM-03` | `GET` | `/api/admin/movies/{movie_id}` | admin |
| `EP-ADM-04` | `PATCH` | `/api/admin/movies/{movie_id}` | admin |
| `EP-ADM-06` | `GET` | `/api/admin/movies/{movie_id}/poster` | admin |
| `EP-ADM-05` | `POST` | `/api/admin/movies/{movie_id}/poster` | admin |
| `EP-ADM-07` | `POST` | `/api/admin/movies/{movie_id}/publish` | admin |
| `EP-ADM-08` | `POST` | `/api/admin/movies/{movie_id}/unpublish` | admin |
| `EP-ADM-15` | `GET` | `/api/admin/screens` | admin |
| `EP-ADM-16` | `POST` | `/api/admin/screens` | admin |
| `EP-ADM-17` | `PATCH` | `/api/admin/screens/{screen_id}` | admin |
| `EP-ADM-18` | `GET` | `/api/admin/screens/{screen_id}/seats` | admin |
| `EP-ADM-19` | `POST` | `/api/admin/screens/{screen_id}/seats` | admin |
| `EP-ADM-12` | `GET` | `/api/admin/seat-categories` | admin |
| `EP-ADM-13` | `POST` | `/api/admin/seat-categories` | admin |
| `EP-ADM-14` | `PATCH` | `/api/admin/seat-categories/{seat_category_id}` | admin |
| `EP-ADM-21` | `DELETE` | `/api/admin/seats/{seat_id}` | admin |
| `EP-ADM-20` | `PATCH` | `/api/admin/seats/{seat_id}` | admin |
| `EP-ADM-09` | `GET` | `/api/admin/showtimes` | admin |
| `EP-ADM-10` | `POST` | `/api/admin/showtimes` | admin |
| `EP-ADM-11` | `PATCH` | `/api/admin/showtimes/{showtime_id}` | admin |
| `EP-RPT-04` | `GET` | `/api/reports/audit` | admin |

**Operational — not routed to the public** — 3

| Id | Method | Path | Who |
|---|---|---|---|
| `EP-XCT-01` | `GET` | `/health/live` | anyone |
| `EP-XCT-02` | `GET` | `/health/ready` | anyone |
| `EP-XCT-03` | `GET` | `/metrics` | anyone |

**No endpoint withdraws a showtime** (`P-SCP-18`, `OPEN-SHOWCANCEL-01`), **validates a ticket**
(`P-SCP-10`), **cancels a booking or issues a refund** (`P-SCP-11`), or **exports anything**
(`P-SCP-14`, `P-RPT-10`). Those absences are specified, not accidental.

## S3.9 One consequence of one person holding every role

`[SRC: SRC-003 OPEN-NAME-01 · SRC-001 §8.2 · FR-ADR-068 · CONSTITUTION.md Art IX.7]`

The client is the customer-facing business, the developer, the money-signer, the rules-signer and the
operator, **and there is no backup** — stated affirmatively, not left blank.

Two consequences that this document must not paper over:

- **There is no escalation path and there cannot be.** If the one alarm is not read, nothing else
  happens (`S7.14`).
- **The delay in which a bad decision usually becomes visible never occurs**, because the decider is
  also at the keyboard. That is why a fresh zero-context reader graded this document, and why the
  substitution is recorded in `S8.6` rather than passed off as independent review.
