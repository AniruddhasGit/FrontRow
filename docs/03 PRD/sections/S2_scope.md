# S2 — Scope, carried from the frozen BRD

The BRD decided what the business needs. This section carries that boundary into the specification
without re-deciding any of it, and turns each exclusion into a row a reviewer can check.

---

## S2.1 The win condition, corrected

> `CONSTITUTION.md` Art I.6 still describes **a scannable ticket** and **movie data arriving from an
> external source on a schedule**. Both were withdrawn on 2026-08-14. Amending the Constitution is
> reserved to the client (Art XII.1), so the stale clause is raised and not edited. **This is the
> corrected win condition, taken from BRD `B3.3`.**

`[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-HOLD-01 · SRC-003 OPEN-PAY-01 · SRC-003 OPEN-TICKET-01 ·
SRC-003 OPEN-TMDB-01 · SRC-003 OPEN-SCOPE-01 · SRC-001 §3.2 · FR-ADR-006 · FR-ADR-034]`

A visitor browses the movies currently showing, registers, picks a showtime, sees a live seat map,
holds seats for three minutes, pays through the simulated payment step, and receives an **emailed
receipt carrying a unique booking reference**; **fifty simultaneous attempts on one seat produce
exactly one winner, proved in the database and not in the website's answer**; an **admin creates a
movie by hand** and it appears to customers; a **manager sees their own halls' numbers and nobody
else's**; and it runs on AWS from containers the client deployed by hand.

**Everything past that line is fast-follow.** Define victory, then stop.

## S2.2 The five success criteria, as this document must make testable

| # | Criterion | Where it becomes binary | Source |
|---|---|---|---|
| `SC-1` | a signed-in customer completes a booking in under two minutes, seat map to confirmation. **A first-time visitor's run includes registration and will not meet it** — that figure is measured and reported separately, not quietly excluded | `P-ACC-06` | `SRC-001 §3.1` · `FR-ADR-046` |
| `SC-2` | **zero double-booked seats under concurrent load.** Fifty simultaneous attempts on one seat: **exactly one 201**, forty-nine `SEAT_UNAVAILABLE` 409s, one owner in the database. (201, not 200 — `EP-HLD-01` creates a hold. `CONSTITUTION.md` Art IX.3's illustrative "one 200" is an example of the *shape* of a binary criterion, not this endpoint's status.) **Not "at most one" — zero winners is also a failure.** Then the guard is dropped on purpose, watched failing, restored and verified | `P-HLD-13` | `SRC-001 §3.2` · `§2.2` · `§7.1` · `FR-ADR-024` · `FR-ADR-034` |
| `SC-3` | seat availability is accurate within a few seconds — **worst case about thirteen seconds**, stated rather than rounded down. Being out of date never causes a double sale | `P-BRW-09`, `S7.6` | `SRC-001 §3.3` · `§7.3` · `FR-ADR-030` |
| `SC-4` | **withdrawn.** `SRC-001 §3.4` was withdrawn by erratum `E-7`. There is no automatic listing update to measure | — | `SRC-001 §E E-7` |
| `SC-5` | a manager reads their own halls' occupancy for a chosen day, week or month, with no request to anyone | `P-RPT-01`, `P-RPT-04` | `SRC-001 §3.5` · `SRC-003 OPEN-REPORT-01` · `FR-ADR-043` |

**`SC-2` is never waived.** Waiving any quality check is reserved to the client (Art III.8), and
adopting a stricter option is not a waiver and needs no signature (Art III.10).

## S2.3 The eight phases, and what closes each

`[SRC: SRC-002 §12 · SRC-002 §12.1 · SRC-002 §E E-3 · SRC-003 OPEN-SCOPE-01 · FR-ADR-006]`

| Phase | What ships | Closes when |
|---|---|---|
| 1 | skeleton, config loading, health endpoints, structured logging, local `docker-compose` | the client has deployed it to ECS and been told what to test |
| 2 | data model, migrations, seed data, admin CRUD for halls, showtimes and pricing | the admin can configure a hall and price a showtime |
| 3 | public browsing, listings, the seat-map read path, caching | a guest can reach a live seat map |
| 4 | seat locking, booking confirmation, idempotency, **the concurrency proof** | `SC-2` is green **and the red-proof drill has been watched** |
| 5 | the SQS worker and the receipt email | a receipt arrives carrying a reference |
| 6 | **admin movie management** *(this replaced the withdrawn automatic import)* | an admin authors a movie by hand and a customer sees it |
| 7 | metrics, rate limiting, the load test, the runbook | the client can run the load test themselves |
| 8 | **the manager and admin dashboard** *(new, added by `SRC-003`)* | a manager sees their own halls and is denied another's |

**A phase closes only when the client has been told what to test** (`SRC-002 §12.1`). Every P-row in
this document names its phase.

## S2.4 What is not built

Eighteen rows, one per BRD `R-OUT` row. **Excluded is not blocked** (`SRC-001 §6.6`): no row here may
harden into something the business can never add, and each says what keeps it possible.

---

### `P-SCP-01` · No native mobile application · `RULED`
`[SRC: SRC-001 §6.1 · FR-ADR-044]`
`[BRD: R-OUT-01]`

**Not built.** No iOS or Android application, no app-store artefact, no native wrapper.

**What the system does instead.** One responsive web interface, designed and tested at the hardest
case it has: **the largest hall's seat map on a 375-pixel-wide screen** (`S7.13`). The client stated
the substitute themselves — "a website that works well on a phone is enough".

**What keeps it possible.** The interface is a separate static container talking to a JSON API over
`/api` (`S6`). A native client would consume the same contract. Nothing in the API assumes a browser.

**Phase.** n/a.

---

### `P-SCP-02` · No food and beverage ordering · `RULED`
`[SRC: SRC-001 §6.2]`
`[BRD: R-OUT-02]`

**Not built.** No concessions catalogue, no add-to-order, no non-ticket line on any total.

**What the system does instead.** A booking's amount is the sum of its seat prices and nothing else
(`P-PAY-07`). The stored total is a single figure.

**What keeps it possible.** Nothing in the money path forbids a second kind of line item later — but
note the constraint this creates: **the stored total cannot be split retrospectively**, because
nothing records what portion was ever meant to be what. Adding an order line later means adding it
going forward, not reinterpreting history. Recorded so it is a known limit rather than a discovery.

**Phase.** n/a.

---

### `P-SCP-03` · No loyalty points and no membership tiers · `RULED`
`[SRC: SRC-001 §6.3]`
`[BRD: R-OUT-03]`

**Not built.** No points balance, no tier on a user, no earn or burn, no member price.

**What the system does instead.** Every customer is priced identically: base price plus the category
uplift, uniform across every hall and every show (`P-PAY-05`).

**What keeps it possible.** The user row and the price computation are separate; a tier would be a
new input to one function (`FR-ADR-038`), not a second pricing path.

**Phase.** n/a.

---

### `P-SCP-04` · No multi-language interface · `RULED`
`[SRC: SRC-001 §6.4 · FR-ADR-044]`
`[BRD: R-OUT-04]`

**Not built.** No locale switch, no translation layer, no per-user language preference.

**What the system does instead.** One interface language. Movies still carry a `language` field
because it is something a customer filters on (`P-BRW-03`) — **that is the film's language, not the
interface's**, and the two are unrelated.

**What keeps it possible.** No user-facing string is assembled from fragments or interpolated
mid-sentence, so extracting them later is mechanical rather than a rewrite.

**Phase.** n/a.

---

### `P-SCP-05` · No point-of-sale integration · `RULED`
`[SRC: SRC-001 §6.5]`
`[BRD: R-OUT-05]`

**Not built.** No connection to any counter system, no import or export of counter sales, no shared
inventory with a till.

**What the system does instead.** Seats sold online are the only seats this system knows about. **A
seat sold at the counter is invisible to it**, and the seat map will show that seat as available.
Stated plainly because it is a real operational consequence: while both channels exist, the online map
is authoritative only for online sales.

**What keeps it possible.** The booking table already carries an owner and a source-agnostic seat
occupancy row; a counter sale would be another writer against the same unique constraint on
`(showtime_id, seat_id)`, which is what makes it safe to add.

**Phase.** n/a.

---

### `P-SCP-06` · No external source of film information, and no automatic import · `RULED`
`[SRC: SRC-003 OPEN-TMDB-01 · SRC-001 §E E-4 · SRC-002 §E E-2 · FR-ADR-006]`
`[BRD: R-OUT-06]`

**Not built.** No external movie API, no API key, no `region` parameter, no rate-limit backoff, no
upsert-by-external-id, no pending/publish import state, no three trigger routes, and **no "the
external source is unavailable" failure path** — the failure cannot occur because the dependency does
not exist.

**What the system does instead.** The admin authors every movie by hand: title, poster, the details
customers see, and the display window (`P-ADM-01`). This is the largest change of scope on the
project.

**What keeps it possible.** The movie row's fields are the same fields an import would have populated.
An importer would be a writer against the existing admin surface, not a second model.

**Also removed with it.** The whole class of failure where a scheduled job silently overwrites
something a person typed.

**Phase.** n/a — Phase 6 became admin movie management in its place.

---

### `P-SCP-07` · No scheduled job of any kind · `RULED`
`[SRC: SRC-003 OPEN-PROC-01 · SRC-002 §E E-4 · FR-ADR-005]`
`[BRD: R-OUT-07]`

**Not built.** No scheduler process, no cron container, no EventBridge rule, no periodic task inside
the API or the worker. **No later design may introduce one.**

**What the system does instead.** Everything that would otherwise have been swept by a job is either
self-expiring or done on the read path:

| What a job would have done | What happens instead |
|---|---|
| release expired seat holds | the Redis key's TTL expires on its own — no cleanup job (`SRC-002 §8.1.4`, `P-HLD-05`) |
| prune old idempotency records | nothing is ever deleted (`FR-ADR-012`) |
| drain the receipt outbox | the worker's existing consume loop relays it (`FR-ADR-031`) |
| refresh a dashboard rollup | the figures are computed on the read path (`P-RPT-02`) |
| expire a movie's display window | the window is evaluated at read time against the current instant (`P-BRW-06`) |

**The discipline this imposes**, stated because it is the point: anything that would otherwise have
been "the nightly job will fix it" has to be correct when it is written. That is stricter and it is
deliberate.

**What keeps it possible.** Three long-running processes exist, not four (`FR-ADR-005`); adding a
fourth is a task-definition change, not an application redesign. It would also cost memory the budget
does not have (`S7.12`).

**Phase.** n/a.

---

### `P-SCP-08` · No separate section for upcoming releases · `RULED`
`[SRC: SRC-003 OPEN-TMDB-02 · SRC-001 §E E-5 · FR-ADR-021]`
`[BRD: R-OUT-08]`

**Not built.** No "coming soon" listing, no pre-sale, no notify-me.

**What the system does instead.** Customers see only what is currently showing: published, and inside
its display window, evaluated against the current instant (`P-BRW-06`). A movie the admin has authored
but whose window has not opened is invisible to customers and visible to the admin.

**What keeps it possible.** The display window already has a start. A future-dated movie is already
representable — it is simply not rendered. Showing it would be a listing change, not a data change.

**Phase.** n/a.

---

### `P-SCP-09` · No scannable code on the ticket · `RULED`
`[SRC: SRC-003 OPEN-TICKET-01 · SRC-001 §E E-9 · SRC-002 §E E-5 · FR-ADR-015]`
`[BRD: R-OUT-09]`

**Not built.** No QR code, no barcode, no image generated anywhere, in the email or on screen.

**What the system does instead.** A **unique booking reference**, `FR-XXXX-XXXX`, designed to be read
aloud from a phone screen and typed by a person at a door (`P-TKT-01`). Its alphabet excludes the
characters people confuse.

**What keeps it possible.** The reference is a stable value on the booking row. Encoding it into an
image later changes the receipt template and nothing else.

**Phase.** n/a.

---

### `P-SCP-10` · No scanner, no validation endpoint, and no used-ticket state · `RULED`
`[SRC: SRC-003 OPEN-TICKET-02 · SRC-001 §E E-3 · FR-ADR-048]`
`[BRD: R-OUT-10]`

**Not built.** No scanning device, no door application, no endpoint that validates a reference, no
`used_at` column, no check-in record, and **no cinema-staff role** (`P-SCP-15`).

**What the system does instead.** Entry is a person at the entrance reading the reference from the
customer's receipt and checking it by hand.

**Accepted weakness, stated rather than buried.** **Nothing prevents the same reference being
presented twice.** That is accepted for a demonstration project and it is a real hole in a live one
(`SRC-003 OPEN-TICKET-02`).

**What keeps it possible.** The booking row is the record a validation endpoint would read and a
`used_at` column would sit on. Adding one is an additive migration.

**Phase.** n/a.

---

### `P-SCP-11` · No customer cancellation and no refund of any kind · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-CANCEL-01 · SRC-003 OPEN-CANCEL-02 · SRC-001 §E E-2 · FR-ADR-013]`
`[BRD: R-OUT-11]`

**Not built.** No cancellation control, no cancellation endpoint, no refund of any kind — partial or
full, for any reason. No refund table, no refund amount, no cancellation reason, no policy
configuration. **The payment path has no reverse**: a captured simulated payment is never unwound.

**What the system does instead.** A confirmed booking is final (`P-PAY-08`).

**Recorded, not challenged.** **A customer who cannot attend loses their money.** That is the ruled
behaviour for a demonstration project and it would need revisiting before a real customer ever booked.

**What keeps it possible.** The schema carries a booking `status` and a `cancelled_at` timestamp, and
**no v1 endpoint exposes either** (`FR-ADR-013`). `status` is written once at confirmation;
`cancelled_at` stays null for every row v1 creates. Adding those columns after real bookings exist
would be a migration on live data with a backfill nobody can verify.

**One thing that must be revisited first if cancellation is ever added**: the unique constraint on
`(showtime_id, seat_id)` is **total**, not partial. With no cancellation that is the simpler and
stricter form. A cancelled booking under a total constraint would hold its seat forever.

**Phase.** n/a.

---

### `P-SCP-12` · No real payment provider, ever, at any point in this project · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-PAY-01 · SRC-003 OPEN-PAY-02 · SRC-001 §E E-10 · FR-ADR-041]`
`[BRD: R-OUT-12]`

**Not built.** No gateway integration, no merchant account, no webhook receiver, no card number field,
no CVV field, no expiry field, and **no placeholder for one**. No card data in a log, a column, a test
fixture or a seed script.

**What the system does instead.** A simulated provider behind a real interface with real state
transitions — `pending → authorized → captured` and `failed` — and an artificial delay bounded well
below the three-minute hold (`P-PAY-03`). The checkout screen states plainly that no real payment is
taken, as a persistent full-width element that is never a footnote and never dismissible.

**The safety rule, and why it is the sharpest one in this document.** `PAYMENT_PROVIDER` has **no
default** (`FR-ADR-041`, `S7.9`). A default would let a deployment become a fake shop silently, and
**a simulated payment that looks real to a customer is the worst failure this product can produce** —
it takes their seat, takes nothing else, and they find out at the door.

**What keeps it possible.** The interface is shaped so a real provider drops in behind it without a
schema change. `FR-ADR-041` rules a real provider out entirely, so this is a property of the design
and not a plan.

**Phase.** n/a.

---

### `P-SCP-13` · No accessible-seat marking, no paired seats, and no gap rule · `RULED`
`[SRC: SRC-003 OPEN-SEAT-02 · SRC-003 OPEN-SEAT-03 · SRC-003 OPEN-SEAT-04 · FR-ADR-016]`
`[BRD: R-OUT-13]`

**Not built.** No wheelchair-accessible seat flag, no seat sold only in a pair, and no rule preventing
a customer leaving a single empty seat between bookings.

**What the system does instead.** Every seat is sold individually and any available seat may be chosen
(`P-SEA-03`). **The lock stays per seat**, which keeps the hardest part of this system at its simplest
form — a paired seat would turn the lock from per-seat into per-group, which is a materially harder
concurrency problem.

**Recorded, not challenged.** A real cinema in India operates under accessibility obligations, and
this ruling rests on there being no real customers. **This would need revisiting before anyone booked
a real seat** (`SRC-003 OPEN-SEAT-02`). It is a known deferral, not an oversight.

**What keeps it possible.** A seat row already carries a category by foreign key; a flag or a grouping
would be an additive column. The gap rule is the expensive one to add later — it is a rule that can
make a valid selection fail at confirmation time, so it would have to be enforced where the map is
drawn as well as at checkout.

**Phase.** n/a.

---

### `P-SCP-14` · No export of reporting or booking data to a file · `RULED`
`[SRC: SRC-003 OPEN-REPORT-02 · FR-ADR-043]`
`[BRD: R-OUT-14]`

**Not built.** No CSV, no spreadsheet, no PDF, no download control, no print-to-file path, and no
endpoint that returns a file.

**What the system does instead.** The dashboard is on screen only (`P-RPT-05`).

**Why this is more than a missing feature.** It keeps customer-level booking data off any download
path. For a business with no operations team, a file of booking data that leaves the business's
control the moment it is created is a real exposure, and not creating it removes the exposure rather
than managing it.

**What keeps it possible.** The dashboard's figures come from one query layer; an export would
serialise the same result differently.

**Phase.** n/a.

---

### `P-SCP-15` · No cinema-staff role and no door scanner · `RULED` · rests on a `PROVISIONAL` reading
`[SRC: SRC-003 OPEN-ROLE-01 · SRC-001 §E E-1 · FR-ADR-009]`
`[BRD: R-OUT-15]`

**Not built.** There is no cinema-staff role. `SRC-001 §4.3` — a staff member checking customers in by
scanning a ticket code — is withdrawn, and `§5.5.3` with it.

**What the system does instead.** Four roles: guest, customer, manager, admin (`S3.1`). Entry is a
manual human check (`P-SCP-10`).

**⚠ The role set is `PROVISIONAL`** (`SRC-003 C-1`). The client's own answers had to be reconciled.
What is **not** provisional is the removal of the staff role — the ruling kills the door-scanner
persona explicitly, in the same sentence.

**What keeps it possible.** The role is a value on the user row and an authorisation dependency on a
router. Adding one is additive; the reason four were modelled rather than three is that **collapsing a
role later is a migration and adding one later is a rewrite of every authorisation dependency**, so
the wider set is the safer error.

**Phase.** n/a.

---

### `P-SCP-16` · No discounts, no concession pricing, no fees, and no separate tax line · `RULED` · reserved: money and legal
`[SRC: SRC-003 OPEN-PRICE-02 · SRC-003 OPEN-PRICE-03 · FR-ADR-040]`
`[BRD: R-OUT-16]`

**Not built.** No discount code field, no student or concession rate, no booking fee, no convenience
fee, no separate tax line, and **no space left on any screen for one**.

**What the system does instead.** The amount charged is the sum of the seat prices, with nothing added
and nothing taken away (`P-PAY-07`). The price shown is the price paid.

**Recorded, not challenged, and this is the irreversible part.** A real cinema in India would show GST
on a ticket. **The stored total is a single figure and cannot be split into net and tax afterwards**,
because nothing records what portion was ever meant to be tax. That is written down so it is a known
deferral rather than something an accountant discovers.

**What keeps it possible.** Going forward, a tax or fee would be a second stored component alongside
the seat total. Historical bookings would remain single figures and would have to stay that way.

**Phase.** n/a.

---

### `P-SCP-17` · No artificial-intelligence feature · `RULED` · reserved: legal
`[SRC: SRC-003 OPEN-MODEL-01]`
`[BRD: R-OUT-17]`

**Not built.** No recommendation model, no natural-language surface, no model call anywhere in the
product, and **no customer data sent to any model**.

**What the system does instead.** Listings sort by the customer's chosen filter, defaulting to newest
first (`P-BRW-05`). That is an ordering, not a recommendation.

**A distinction worth stating.** This governs **the product**. That the product is *built* by LLMs
reading this repository is a separate matter, and it is why the repository holds no credential and no
real customer data.

**What keeps it possible.** Nothing in the design forecloses it, and adding one would be a reserved
decision (`S7.17`), not a technical one.

**Phase.** n/a.

---

### `P-SCP-18` · Withdrawing a showtime that already has paid bookings — **not excluded, unruled** · **`OPEN`** · reserved: money, irreversible
`[SRC: SRC-003 OPEN-SHOWCANCEL-01 · SRC-003 OPEN-OPS-03 · SRC-003 OPEN-CANCEL-02 · FR-ADR-023]`
`[BRD: R-OUT-18]`

**This row is not an exclusion. It is an open question, and it is listed here so its absence from the
admin surface is visible rather than silent.**

`SRC-003 OPEN-OPS-03` names *"cancel a show"* as something only the admin does. `OPEN-CANCEL-02` said
to forget cinema-cancelled shows, and there are no refunds. **Those customers have paid.** What
happens to their bookings, and to their money, is a decision about money that no model may make.

**What v1 does.** **The admin has no way to withdraw a showtime.** No endpoint, no control, no screen
(`P-ADM-09`). That gap is stated to the client rather than left to be found. It is the only capability
the client named that this version does not deliver.

**Why that is the right shape while the row is open.** An unbuilt capability is recoverable. An
unrefunded customer is not.

**What may not be written here.** No withdrawal flow, no refund behaviour, no customer notification,
and no policy — not as a default, not as a placeholder, not as a suggestion in a comment. **Escalate,
never invent.**

**Phase.** blocked, pending `OPEN-SHOWCANCEL-01`.

---

## S2.5 The rule that governs the whole section

**Excluded is not blocked** (`SRC-001 §6.6`, `FR-ADR-010`, `FR-ADR-013`, `FR-ADR-046`).

> *"We may ask for these later, so please do not design in a way that blocks them."*

**An exclusion that hardens into an architectural impossibility is a defect, not a simplification**
(`CONSTITUTION.md` Art I.3). Four places where this rule is already doing visible work in the
specification rather than only in prose:

- the `cinema` entity stays in the schema with exactly one row, so a second venue is an insert and not
  a migration against live bookings (`FR-ADR-010`);
- booking `status` and `cancelled_at` exist and no endpoint exposes them (`P-SCP-11`);
- the **cinema filter capability exists and is not rendered** while one cinema exists, and appears on
  its own if a second ever does (`P-BRW-03`);
- the payment interface keeps real state transitions so a provider could drop in behind it, even
  though `P-SCP-12` rules one out entirely.

**And one place where the rule has a limit, stated because the limit is real**: `P-SCP-16` and
`P-SCP-02` both note that the stored total is a single figure. Adding a tax line or an order line
later works **going forward only**. History cannot be reinterpreted, and pretending otherwise would be
the kind of quiet promise this document exists to avoid.
