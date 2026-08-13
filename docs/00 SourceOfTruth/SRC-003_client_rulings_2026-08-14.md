# SRC-003 — FrontRow client rulings

```
Source type ....... Client rulings, in answer to CONSTITUTION.md Article X
Received .......... 2026-08-14
Author ............ Aniruddha Jathar (the client)
Original file ..... docs/00 SourceOfTruth/OPEN_QUESTIONS_2026-08-14.md (working file, not frozen)
Status ............ FROZEN — never edited
Citation form ..... SRC-003 <ROW-ID>
Rows .............. 40 of 40 answered
```

> **FROZEN INPUT. DO NOT EDIT.** The `Ruling` block of every row below is the client's own words,
> reproduced verbatim. Anything under `Filed as` is the build session's reading of that answer and
> is **not** client text — where a reading was required, it says so and gives the alternative it
> rejected.
>
> The only permitted modification is a clearly-marked `ERRATUM` appended at the foot.

> **One redaction, deliberate.** `OPEN-OPS-01`'s answer contained the client's personal email
> address. **This repository is public.** The address is held outside git — in the CloudWatch alarm
> and SNS subscription the client configures, and in `.env` locally. The ruling is recorded; the
> address is not. Nothing downstream needs the literal string.

---

## Status summary

| Status | Count |
|---|---|
| `RULED` — a real answer, binding | 34 |
| `ASSUMED` — client said "you pick"; build session chose; never hardens into a rule | 5 |
| `DEFERRED` — client is still deciding | 1 |
| **Total** | **40** |

**Ten errata are filed against `SRC-001` and six against `SRC-002`** as a result of these rulings.
Both are listed at the foot of this document and appended to the sources themselves.

---

## ⚠ Two contradictions inside these answers, and how they were read

Recorded here rather than resolved silently, per `CONSTITUTION.md` Art VII.3. **Both readings are
`PROVISIONAL` and one message from the client reverses either.**

### C-1 — do managers exist?

`OPEN-ROLE-01` says *"do not make more personas… only 1 admin persona. admin can do all the stuff
the managers can do."* `OPEN-SCOPE-01` then says *"different managers for different cinema hall…
2 managers per cinema hall… can see earnings movies for the day, month, week and cannot add the new
movies."* `OPEN-REPORT-01` says *"reporting will be done to the mamagers and admins as they will
have a dashboard."*

**Read as: four roles — guest, customer, manager, admin.** The reading that satisfies every answer
is that `OPEN-ROLE-01`'s prohibition is aimed at the **cinema staff / door scanner** persona, which
it kills explicitly in the same sentence, and at admin *tiers* — not at managers, which two later
answers describe in operational detail. `"admin can do all the stuff the managers can do"` states
that admin is a superset of manager, which presupposes manager exists.

**A manager is read-only.** They see their own hall's numbers. They create nothing, publish nothing,
price nothing — `OPEN-OPS-03` puts every privileged write on the admin alone.

**Rejected reading:** three roles, with the manager dashboard served to admins filtered by hall.
That satisfies `OPEN-ROLE-01` literally but discards `OPEN-SCOPE-01`'s "2 managers per cinema hall"
entirely, and twelve people sharing one admin account is a real access-control problem.

### C-2 — is there one cinema or several?

`OPEN-SCOPE-01` says *"the theatre has 6 cinema halls"* — singular theatre, six halls. `SRC-001 §1.1`
says *"We operate cinemas"*, plural, and `§5.1.3` asks customers to filter by cinema.

**Read as: one cinema at launch, with six screens, and the schema keeps the cinema entity anyway.**
A `cinema` table with one row costs almost nothing and `SRC-001 §6.6` forbids designing in a way
that blocks a later ask. Manager scoping attaches to the **screen**, matching the ruling's own
words, not to the cinema.

---

# Part 1 — the blocking eight

## `OPEN-NAME-01` — ratification · `RULED`

**Ruling (verbatim).**
> Aniruddha Jathar is my name and i will always be the one building

**Filed as.** Ratifier is **Aniruddha Jathar**. **No backup decider**, stated affirmatively rather
than left blank.

**Consequence, stated plainly.** With one person as client, developer, money-signer and rules-signer,
the decision queue never forms — there is nobody the queue is *for*. The compensating control in
`CONSTITUTION.md` Art IX.7 is now load-bearing rather than a formality: a fresh zero-context session
grades every irreversible call, because it is the only second opinion this project has.

`CONSTITUTION.md` moves from **UNADOPTED** to **ADOPTED** on this ruling. The
"recorded while ungoverned" caveat applies to no ADR, because none had been filed.

## `OPEN-LOCALE-01` — market and currency · `RULED` · reserved (money)

**Ruling (verbatim).**
> India launched currency is rupees

**Filed as.** Country **IN**. Currency **INR**. Minor unit **paise**, ratio **100**. Money is stored
as an integer number of paise. Timezone **Asia/Kolkata**.

**Irreversibility note.** The minor-unit ratio is a one-way door once bookings exist. It is recorded
here as the single value that may never be changed by inference.

## `OPEN-ROLE-01` — the role set · `RULED`, with reading `C-1` · **PROVISIONAL**

**Ruling (verbatim).**
> no make it simple i am learning devops no scanner and stuff at the entrance we will make a receipt
> after purchase which will have a unique ID to make the person enter the cenima hall. the guest is
> someone who has no account can browse but will need to amkee a account if want to purchase a
> ticket. and a admin who has the whole access. do not make more personas. thats it. the admin can
> add movie names and pictures and other stuff which the people can view on the website. and also
> have a dealine of how long this will stay and other things that need to be done so that customer
> can see the movies on front end. only 1 admin persona. admin can do all the stuff the managers can
> do.

**Filed as.** Four roles:

| Role | Account | Can |
|---|---|---|
| **guest** | none | browse movies and showtimes; see the seat map; **cannot** hold or book |
| **customer** | required to book | hold seats, pay, view their own bookings and receipts |
| **manager** | required | **read only** — the dashboard for the screens they are assigned to |
| **admin** | required | everything, including everything a manager can do |

**No cinema-staff role. No door scanner.** Entry is a manual check of the unique booking id on the
emailed receipt.

**Also ruled here, and it is a scope change:** the admin *creates movies by hand* — title, poster,
and "a deadline of how long this will stay", i.e. a display window with a start and an end. This is
what replaces the TMDB import. See `OPEN-TMDB-01`.

## `OPEN-SCOPE-01` — the four orphaned requirements · `RULED`

**Ruling (verbatim).**
> different managers for different cinema hall. can see earnings movies for the day, month, week and
> cannot add the new movies,the theatre has 6 cinema halls. and there are 2 managers per cinema hall.
> and other analytics things add more stuff that managers can do.

**Filed as.**
- **One theatre, six halls (screens).** Two managers assigned per hall — twelve manager accounts.
- A manager's dashboard is scoped to their assigned screens and covers **day, week and month**:
  earnings, occupancy, and per-movie performance for those screens.
- A manager **cannot** add movies, and by `OPEN-OPS-03` cannot perform any privileged write at all.
- Staff door-validation: **dropped** (`OPEN-ROLE-01`).
- Customer cancellation: **dropped** (`OPEN-CANCEL-01`, `OPEN-CANCEL-02`).
- Management reporting: **in scope**, as the manager and admin dashboard.

**"add more stuff that managers can do" is read as read-only analytics only**, because `OPEN-OPS-03`
puts every write on the admin. Additional manager capability beyond reporting is **not** invented
here — Art VII.3 forbids it. Concrete additions are listed in the PRD as candidates for the client
to approve, not as ruled scope.

**Revised phase plan.** Phases 1–5 unchanged. **Phase 6 becomes admin movie management** (create,
poster upload, display window, publish) in place of the TMDB sync. **Phase 7** unchanged. **Phase 8
is new: the manager and admin dashboard.**

## `OPEN-QUEUE-01` — SQS, and ElasticMQ locally · `RULED`

**Ruling (verbatim).**
> yes allowed to have ELASTICmq.

**Filed as.** **AWS SQS** in AWS, with a dead letter queue. **ElasticMQ** in `docker-compose.yml` for
local development only — never deployed. Permission for the new dependency is hereby on the record
(`SRC-002 §13.1` satisfied). The worker code targets one queue interface and does not know which is
behind it.

## `OPEN-EMAIL-01` — SES · `RULED`

**Ruling (verbatim).**
> yes will use this.

**Filed as.** **Amazon SES** is added to the approved service list, amending `SRC-002 §4`. It starts
sandboxed; the client requests production access.

**This is now load-bearing, not a nicety.** `OPEN-BOOK-02` makes the emailed receipt the customer's
only proof of purchase and `OPEN-TICKET-01` makes the unique id on it the thing that gets them into
the hall. **If SES fails, the customer has paid and cannot enter.** The PRD must specify what the
customer sees when the email cannot be sent, and the booking page must show the id on screen as well.

## `OPEN-PROC-01` — three processes, not four · `RULED`

**Ruling (verbatim).**
> sure.

**Filed as.** API + worker + a static frontend container. **The scheduler is deleted** — and
`OPEN-TMDB-01` removes the last thing it would have run, so no EventBridge rule is needed either.
Nothing in this system runs on a schedule.

## `OPEN-PAY-02` — simulated payment · `RULED` · reserved (money)

**Ruling (verbatim).**
> yes this is fine.

**Filed as.** A simulated provider behind a real interface, with real states
`pending → authorized → captured` and `failed`. Confirmed again at `OPEN-PAY-01`: *"we'll have a fake
button and flip the flag in DB. i do not want real payment."*

**The safety rule stands:** the simulated provider is unreachable in a deployed environment without a
deliberate, visible flag, and the checkout screen states that no real payment is taken.

---

# Part 2 — scale

## `OPEN-SCALE-01` — cinemas and screens · `RULED`

**Ruling (verbatim).**
> i answered this above.

**Filed as.** From `OPEN-SCOPE-01`: **one theatre, six halls.** See reading `C-2`.

## `OPEN-SCALE-02` — largest screen · `ASSUMED`

**Ruling (verbatim).**
> pick random.

**Filed as (`ASSUMED`, never a constraint).** Six halls of **90, 120, 150, 180, 200 and 220 seats**.
Designed and tested against the 220 on a 375-pixel-wide phone. A spread rather than one number,
because a seat map that only works at one size is not tested.

## `OPEN-SCALE-03` — peak concurrency · `ASSUMED`

**Ruling (verbatim).**
> you pick

**Filed as (`ASSUMED`).** Load test at **50 concurrent bookers**, reporting where it degrades. This
changes nothing about correctness — 50 simultaneous requests for one seat still produce exactly one
winner, and that is a separate, non-waivable gate.

---

# Part 3 — seats

## `OPEN-SEAT-01` — seat categories · `ASSUMED`

**Ruling (verbatim).**
> you pick

**Filed as (`ASSUMED`).** Three categories — **Standard, Premium, Recliner** — held in a table, not
an enum, so a fourth costs no migration. Pricing follows `OPEN-PRICE-01`: a base price plus a fixed
percentage uplift per category.

## `OPEN-SEAT-02` — accessible seating · `RULED` · was reserved (legal)

**Ruling (verbatim).**
> no forget that this is demo project.

**Filed as.** No accessible-seat marking in v1.

**Recorded because it matters later, not as a challenge to the ruling:** this is acceptable *because
this is a demonstration project with no real customers*. A real cinema in India operates under
accessibility obligations, and this decision would need revisiting before anyone could book a real
seat. Written down so it is a known deferral rather than an oversight.

## `OPEN-SEAT-03` — paired seats · `RULED`

**Ruling (verbatim).**
> no such thing

**Filed as.** Every seat is sold individually. **The lock stays per seat**, which keeps the hardest
part of this system at its simplest form.

## `OPEN-SEAT-04` — single-seat gaps · `RULED`

**Ruling (verbatim).**
> no such rule.

**Filed as.** No gap rule. Any available seat may be selected.

---

# Part 4 — booking rules

## `OPEN-HOLD-01` — hold duration · `RULED` — **closes the trap**

**Ruling (verbatim).**
> make this 3 minutes.

**Filed as.** The seat hold TTL is **3 minutes**, from a configuration value, not a constant.
**Erratum `E-1` is filed against `SRC-002 §8.1.1`**, which said 7 minutes.

This closes the one trap `GOTCHAS.md` recorded as already present on this project: the client's own
assumption in `SRC-001 §10.9` had hardened into a requirement in `SRC-002 §8.1.1` without ever being
ruled. It has now been ruled, and it came out different from the assumption — which is the argument
for the whole mechanism.

**Consequence worth naming:** 3 minutes is tight for a real payment flow. It is comfortable for a
simulated one, and it makes the expiry path easy to exercise while testing.

## `OPEN-BOOK-01` — maximum seats per booking · `RULED`

**Ruling (verbatim).**
> 10 maxx

**Filed as.** Maximum **10** seats per booking, enforced server-side, not only in the interface.

## `OPEN-BOOK-02` — account required · `RULED`

**Ruling (verbatim).**
> no booking without an account as the recipet will be sent via mail.

**Filed as.** Browsing is open to guests. **Booking requires a registered account.** A booking always
belongs to a user row; there is no anonymous order.

## `OPEN-BOOK-03` — sales cut-off · `RULED`, with an interpretation · **PROVISIONAL**

**Ruling (verbatim).**
> yes 15 minutes

**Filed as.** Sales close **15 minutes after the advertised start time**, and anyone already holding
seats may finish checking out.

**The interpretation, stated because it could go either way.** The question asked "how long *before*
a show starts"; the recommendation proposed "20 minutes *after* the start, because of trailers". The
answer `"yes 15 minutes"` reads as agreement with the recommendation's shape and a different number.
**The alternative reading is 15 minutes *before* the start.** One message settles it. Flagged in the
handoff for reversal.

## `OPEN-CANCEL-01` — cancellation and refunds · `RULED` · reserved (money)

**Ruling (verbatim).**
> no refund policy

## `OPEN-CANCEL-02` — cinema-cancelled shows · `RULED` · reserved (money, irreversible)

**Ruling (verbatim).**
> no forget this.

**Filed as, for both.** **No refunds, and no customer-initiated cancellation in v1.** A booking is
final once confirmed. **Erratum `E-2` is filed against `SRC-001 §5.4.3`.**

**Reading recorded:** `"no refund policy"` alone would still permit cancelling without a refund, but
combined with `"no forget this"` the whole cancellation surface is out. A cancellation that returns
no money is not a feature a customer would use.

**The schema still carries a booking status and a cancelled-at column.** Adding those after real
bookings exist is a migration on live data, and `SRC-001 §6.6` forbids designing in a way that blocks
a later ask. No endpoint exposes them in v1.

---

# Part 5 — pricing

## `OPEN-PRICE-01` — how price is calculated · `RULED` · reserved (money)

**Ruling (verbatim).**
> the admin will set the ticket price and more the premium ticket the more% fix price increase across
> all halls or any movie show.

**Filed as.** A two-part model:

1. The admin sets a **base price** for a showtime, in paise.
2. Each seat category carries a **fixed percentage uplift**, set once by the admin and applied
   **uniformly across every hall and every show** — that is what *"across all halls or any movie
   show"* rules out: per-hall or per-movie category pricing.

Seat price = `round(base_price × (1 + uplift_percent / 100))`. **The rounding rule is stated in the
PRD with a worked example**, because a percentage of an integer number of paise does not divide
evenly and an unstated rounding rule is how two screens disagree about a total.

**Reading recorded:** base price is per showtime, not global. `"the admin will set the ticket price"`
does not say which level, and a single global ticket price would make an evening blockbuster cost the
same as a weekday matinee. Per-showtime is the narrower, more useful reading. **Reversible.**

## `OPEN-PRICE-02` — discounts · `RULED` · reserved (money)

**Ruling (verbatim).**
> no discout for now

**Filed as.** No discount codes, no concession pricing, no booking fee.

## `OPEN-PRICE-03` — tax on the receipt · `RULED` · reserved (money, legal)

**Ruling (verbatim).**
> no

**Filed as.** No separate tax line. The price shown is the price paid.

**Recorded, not challenged:** a real cinema in India would show GST on a ticket. Acceptable here for
the same reason as `OPEN-SEAT-02` — no real money moves. The stored total is a single figure and
cannot be split later, which is why this is written down.

---

# Part 6 — payment

## `OPEN-PAY-01` — real provider · `RULED` · reserved (money)

**Ruling (verbatim).**
> we'll have a fake button and flip the flag in DB. i do not want real payment.

**Filed as.** **No real payment provider, ever, in this project's scope.** The interface keeps its
states so the flow is realistic and the code is honest, but nothing integrates with a gateway.

`SRC-001 §9.5` — *"Payment is handled by a third party provider"* — is **withdrawn**. Erratum `E-10`.

**Consequence:** the system never handles card data at all, which removes an entire class of risk.
`CONSTITUTION.md` Art V.7 stays in force anyway — no card-shaped data in a log, a column, a fixture
or a seed script, so nobody later adds one out of habit.

---

# Part 7 — movie data

## `OPEN-TMDB-01` — **TMDB is removed from the project** · `RULED` — largest scope change

**Ruling (verbatim).**
> rather make it simple we'll no longer pull the movies. the admin will upload them manually and then
> they will get sorted based on the customers filter, but by default the latest movie will be on top.

**Filed as.** **No TMDB. No external movie API. No scheduled sync.** The admin creates each movie by
hand: title, poster, and the metadata customers see. Listings sort by the customer's chosen filter,
defaulting to **newest first**.

**What this deletes.** The whole of `SRC-002 §10`. The API key, the `region` parameter, rate-limit
backoff, upsert-by-TMDB-id, the pending/publish import state, the three trigger routes, and the
"TMDB unreachable" failure path. Errata `E-2` through `E-6` against `SRC-002`; `E-4` through `E-8`
against `SRC-001`.

**What survives.** **S3 still holds posters** — the admin uploads them instead of a job downloading
them, and `SRC-002 §10.6.3`'s rule that we serve our own URLs and never hotlink still applies.
**Phase 6 becomes admin movie management.**

**TMDB attribution.** `SRC-002 §10.2` required a footer credit as a licence condition. With no TMDB
integration the condition does not arise from the API. **But the client said they will supply posters
and titles themselves**, and if any of that material comes from TMDB the attribution obligation
returns. Raised as **`OPEN-ATTRIB-01`**, a new Article X row — this is a licence question and not the
build session's to close.

## `OPEN-TMDB-02` — upcoming releases · `RULED`

**Ruling (verbatim).**
> no.

**Filed as.** No "upcoming" section. Customers see only what is currently showing. **Erratum `E-5`
against `SRC-001 §5.1.2`.**

## `OPEN-TMDB-03` — who publishes a movie · `RULED`

**Ruling (verbatim).**
> i have defined how the admin will work on the top.

**Filed as.** The **admin**, per `OPEN-ROLE-01` and `OPEN-OPS-03`. Managers cannot.

## `OPEN-TMDB-04` — overriding imported data · `RULED` — moot

**Ruling (verbatim).**
> yeah for this the admin will add the new movies posters and other stuff which will be displayed to
> the customers. that's easier to make.

**Filed as.** Moot. With no import there is nothing to overwrite; the admin's entry is the only
source. The whole class of "a nightly job silently destroys a human's edit" disappears with it.

---

# Part 8 — tickets and entry

## `OPEN-TICKET-01` — what the customer arrives with · `RULED`

**Ruling (verbatim).**
> the receipt sent on email which has a unique ID. that will be shown at the entrance.

**Filed as.** **No QR code.** A booking receipt is emailed, carrying a **unique booking reference**,
the seat numbers, the hall, and the showtime. That reference is what gets the customer in.

**Erratum `E-9` against `SRC-001 §5.3.3`** ("a scannable ticket") and **`E-5` against `SRC-002
§8.5.1`** (the worker generates a QR code). The worker now sends the receipt email and nothing else.

**Design consequence:** the reference is read aloud and typed by a human, so it avoids characters
people confuse — no `0`/`O`, no `1`/`I`/`l`. Format specified in the PRD.

## `OPEN-TICKET-02` — offline validation · `RULED`

**Ruling (verbatim).**
> we will have manual check up with the unique ID sent out to the customer with the booking recipet
> and seat number and all that stuff.

**Filed as.** Entry is a manual, human check of the emailed receipt. **No validation endpoint, no
used-ticket state, no scanning device** in v1.

**Consequence, stated:** nothing prevents the same reference being presented twice. That is accepted
for a demonstration project and is a real hole in a live one. Recorded as an accepted weakness in
`docs/07 Architecture/for_humans/03_the_deliberate_gaps.md`.

---

# Part 9 — reporting

## `OPEN-REPORT-01` — the dashboard · `RULED`

**Ruling (verbatim).**
> reporting will be done to the mamagers and admins as they will have a dashboard.

**Filed as.** A dashboard for managers and admins. Managers see their assigned screens; admins see
everything. Periods **day, week, month**, from `OPEN-SCOPE-01`. Metrics: earnings, occupancy, and
per-movie performance. **Phase 8.**

## `OPEN-REPORT-02` — export · `RULED`

**Ruling (verbatim).**
> No

**Filed as.** No CSV or spreadsheet export. On screen only. This also keeps customer-level booking
data off any download path.

---

# Part 10 — operations

## `OPEN-OPS-01` — alerting · `RULED` · **address redacted from git**

**Ruling (verbatim, address removed).**
> yes follow recommendation. my email id: [REDACTED — see the note at the head of this file]

**Filed as.** A CloudWatch alarm on running-task-count below 1, delivering through SNS to the
client's personal email address. The address lives in the SNS subscription the client creates and in
local `.env`. **It is not committed, because this repository is public.**

**Zone C.** The client builds the alarm, the topic and the subscription. A row exists in
`docs/30 Deployment/AWS_PREP_QUEUE.md` and a specification is owed under `SRC-002 §6.4`.

## `OPEN-OPS-02` — retention · `RULED` · reserved (legal)

**Ruling (verbatim).**
> for now forever we'll change that later if i ask.

**Filed as.** Nothing is ever deleted. No pruning job, no retention window, no cascade that destroys
a booking record. Revisited only on an explicit client request.

## `OPEN-OPS-03` — activity log · `RULED`

**Ruling (verbatim).**
> the admin will only be the one who does changes in movie , cancel a show or other priviledged
> things..no other persona.

**Filed as.** **Every privileged write belongs to the admin role alone.** Managers are read-only.
Audit rows are written for every admin action in the same transaction as the change, from Phase 2
onward. The screen that reads them is Phase 8.

Note this ruling mentions *"cancel a show"* as an admin capability. **`OPEN-CANCEL-02` said to forget
cinema-cancelled shows.** Read as: no *customer-facing* cancellation flow and no refunds, and the
admin's ability to withdraw a showtime is a scheduling action, not a refund action. Raised as
**`OPEN-SHOWCANCEL-01`** rather than assumed — what happens to bookings on a withdrawn showtime is a
money question and the build session may not close it.

---

# Part 11 — raised while drafting the Constitution

## `OPEN-TLS-01` — HTTPS · `DEFERRED`

**Ruling (verbatim).**
> I will look if i can get a free domain somewhere.

**Filed as.** **Not settled.** Until a domain and an ACM certificate exist:
- the session cookie's `Secure` flag stays environment-driven and off in the deployed environment;
- the deployed environment is **never called production** in any document (Art VIII.14);
- this remains an open row.

## `OPEN-SEED-01` — seed data · `RULED`

**Ruling (verbatim).**
> nope do not generate anything just generate a few fake records which we will ingest to showcase the
> bookings. I will bring poster and movie titles and we'll fill them with dummy data for demo. dummy
> data for about a month would be nice.

**Filed as.** The seed script generates **structural** data only — one theatre, six halls with seat
layouts, showtimes and bookings spanning **about one month**, enough to make a dashboard show real
shapes. **No invented movie titles and no invented posters**; the client supplies those. Movie rows
are seeded with obvious placeholders (`DEMO MOVIE 01`) that could never be mistaken for real content.

## `OPEN-AWSREAD-01` — AWS access boundary · `RULED`

**Ruling (verbatim).**
> yes follow recommendation.

**Filed as.** Development environment only. The build session may run **`describe`, `list` and
`get`** to verify what the client built against the specification, and **creates, modifies and
deletes nothing**, at any confidence, until the client says otherwise in writing.

**Still unstated, and not assumed:** the account id and region the credentials belong to. Carried as
a minor gap; the build session will read them from the credentials at first use rather than guess,
and record what it found.

## `OPEN-MODEL-01` — AI and data · `RULED` · reserved (legal)

**Ruling (verbatim).**
> nothing like AI for now.

**Filed as.** The product contains no AI feature and sends no customer data to any model. This
governs the **product**, not the build method — the project is built by LLMs reading this repository,
which is a separate matter and is why the repository holds no credential and no real customer data.

---

# New Article X rows raised by these rulings

Filed rather than answered, because each is reserved or a licence question.

| ID | Question | Class |
|---|---|---|
| `OPEN-ATTRIB-01` | If the posters and titles the client supplies come from TMDB or any other licensed source, the attribution obligation `SRC-002 §10.2` described still applies even though the API integration is gone. Where does the material come from? | reserved: legal |
| `OPEN-SHOWCANCEL-01` | `OPEN-OPS-03` names *"cancel a show"* as an admin action; `OPEN-CANCEL-02` said to forget cinema-cancelled shows. If an admin withdraws a showtime that already has bookings, what happens to those bookings and to the money? | reserved: money, irreversible |
| `OPEN-EMAILFAIL-01` | The emailed receipt is now the customer's only proof of purchase and their only way into the hall. What happens when SES fails after payment is captured? | reserved: product |

---

# Errata filed against `SRC-001`

| # | Clause | Correction | Ruling |
|---|---|---|---|
| `E-1` | `§4` — five user types | Four: guest, customer, manager (read-only), admin. No cinema-staff role. | `OPEN-ROLE-01` |
| `E-2` | `§5.4.3` — cancel a booking | Withdrawn. No cancellation, no refunds in v1. | `OPEN-CANCEL-01`, `-02` |
| `E-3` | `§5.5.3` — staff validate tickets at the door | Withdrawn. Manual check of the emailed reference. | `OPEN-ROLE-01`, `OPEN-TICKET-02` |
| `E-4` | `§5.6` — movie data from a public database, automatically | Withdrawn in full. The admin enters movies by hand. | `OPEN-TMDB-01` |
| `E-5` | `§5.1.2` — show upcoming releases separately | Withdrawn. | `OPEN-TMDB-02` |
| `E-6` | `§2.3` — listings without staff typing them in | Withdrawn. Staff do enter them; that is now the design. | `OPEN-TMDB-01` |
| `E-7` | `§3.4` — listings update automatically | Withdrawn. | `OPEN-TMDB-01` |
| `E-8` | `§5.5.4` — administrator approves imported movies | Withdrawn; nothing is imported. The admin authors and publishes. | `OPEN-TMDB-01` |
| `E-9` | `§5.3.3` — a scannable ticket | A unique booking reference on an emailed receipt, checked by a human. | `OPEN-TICKET-01` |
| `E-10` | `§9.5` — payment handled by a third party | Withdrawn. Simulated only; no provider, ever. | `OPEN-PAY-01` |

# Errata filed against `SRC-002`

| # | Clause | Correction | Ruling |
|---|---|---|---|
| `E-1` | `§8.1.1` — hold TTL of 7 minutes | **3 minutes**, from configuration. | `OPEN-HOLD-01` |
| `E-2` | `§10` — the whole TMDB section | Withdrawn in full. | `OPEN-TMDB-01` |
| `E-3` | `§12.7` — Phase 6, TMDB sync and publishing | Phase 6 becomes admin movie management. A new Phase 8 adds the dashboard. | `OPEN-TMDB-01`, `OPEN-SCOPE-01` |
| `E-4` | `§4.6` — a scheduler process or EventBridge Lambda | Withdrawn. Nothing runs on a schedule. | `OPEN-PROC-01`, `OPEN-TMDB-01` |
| `E-5` | `§8.5.1` — the worker generates a QR code | The worker sends the receipt email carrying a unique reference. No QR. | `OPEN-TICKET-01` |
| `E-6` | `§4` — the approved service list | **Amazon SES is added**, on the client's ruling. | `OPEN-EMAIL-01` |

---

## §E — Errata against this document

*(none filed)*
