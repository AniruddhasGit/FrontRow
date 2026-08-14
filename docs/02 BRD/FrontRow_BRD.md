# FrontRow — Business Requirements

```
Document .......... docs/02 BRD/FrontRow_BRD.md
Derived from ...... SRC-001 (product requirement) · SRC-002 (build mandate, business clauses only)
                    SRC-003 (client rulings, 2026-08-14) · the APPROVED records in docs/01 ADR/
Written ........... 2026-08-14
Constitution ...... frontrow-constitution@0.1.0
Authority ......... CONSTITUTION.md Art II.1. Where this document and a frozen source
                    disagree, the frozen source wins and this document is the defect.
```

> **This document says what the business needs and why. It says nothing about how any of it is
> built.** No product name, no service name, no data structure and no interface appears anywhere in
> it. A business reader must be able to check every row against what they asked for, without knowing
> anything about software. The technical answers live in `docs/03 PRD/` and the records in
> `docs/01 ADR/`.

---

# B1 — Reading rules and the provenance grammar

## B1.1 Every row carries its source

Each requirement is one row with a fixed shape:

```
R-XXX-nn · a short name                                          · STATUS
[SRC: the clause or ruling it comes from]
The requirement, in business language.
  Why the business needs it — ...
  What it costs the business if absent — ...
```

**A row with no `[SRC:]` tag is a defect, not a judgement call.** Nothing in this document is here
because it seemed sensible. Four kinds of citation are permitted and no others:

| Citation | Means |
|---|---|
| `SRC-001 §n` | the client's product requirement, frozen 2026-08-14 |
| `SRC-002 §n` | the client's build mandate — **only** where it states a business need, see B1.4 |
| `SRC-003 OPEN-XXX-nn` | the client's own ruling of 2026-08-14, the newest and most authoritative source |
| `FR-ADR-nnn` | an `APPROVED` decision record in `docs/01 ADR/all-ADRs/` |

## B1.2 Status law — the rule that matters most here

| Status | Meaning in this document |
|---|---|
| `RULED` | the client decided it, and the citation says where |
| `PROVISIONAL` | written down as a reading of two of the client's own answers. **One message from the client reverses it.** It never reads as settled fact |
| `ASSUMED` | the client said "you pick". It is the build session's choice and **it never hardens into a requirement** |
| `OPEN` | genuinely unruled. It is named, never filled in. **Escalate, never invent** |

Three readings in this document are `PROVISIONAL` and are marked on every row that rests on them —
the role set, one cinema against several, and the direction of the sales cut-off. Three subjects are
`ASSUMED` — the hall sizes, the peak-concurrency figure and the seat category names. Four questions
are `OPEN` and are listed in B5.11.

**A note on counting — raised by this document, and since resolved.** `SRC-003`'s summary table
originally recorded 34 `RULED`, 5 `ASSUMED` and 1 `DEFERRED`, while the status tags on the row
headings in the same file read 36 / 3 / 1. Both totalled 40, so nothing obvious was missing.

**This document took the tag on each row, not the summary** — and that turned out to be the correct
half. The summary had been typed rather than counted. It was corrected in place on 2026-08-14, with
the hash change adjudicated in `fingerprints.json`, and it is **not** an erratum: errata govern
client text, and no `Ruling` block was ever affected. The three `ASSUMED` subjects are
`OPEN-SCALE-02`, `OPEN-SCALE-03` and `OPEN-SEAT-01`, named above.

The rule this leaves behind, which binds every document downstream of this one: **a count stated in
prose is a claim, and it is derived from the file or it is wrong.** Every count in this document —
including both coverage tables in `B8` — is machine-derived.

## B1.3 Sixteen clauses are withdrawn or corrected, and a row derived from one is a defect

`SRC-003` filed **ten errata against `SRC-001` and six against `SRC-002`**. Twelve clauses of
`SRC-001 §1`–`§9` are withdrawn outright and one is corrected. They are listed in full in **B7.3**,
each with the erratum that withdrew it, so their absence from B5 is visible rather than silent.
**The whole of `SRC-002 §10` is withdrawn.** Nothing in this document cites it.

## B1.4 What `SRC-002` contributes, and what it does not

`SRC-002` is a *build* mandate. It says how the product is built, not what the business needs.
**It is cited here only in three places, and every other clause of it is technical and belongs in the
PRD:**

- **`§1`** — the client's own statement of why this product exists at all.
- **`§5`** — the infrastructure budget ceiling.
- **`§12`** — the phased delivery order, as revised by erratum `E-3`.

Where a business requirement rests on a technical clause of `SRC-002`, it is cited through the
`APPROVED` decision record that carries it, never through the raw clause.

## B1.5 Three clauses of `CONSTITUTION.md` are stale and are not inherited

`CONSTITUTION.md` predates `SRC-003` and Art XII.1 reserves amending it to the client, so three of
its clauses still describe a product that no longer exists. **`SRC-003` and the errata win under
Art II.1.** They are listed here so nobody reads this document as contradicting the Constitution when
it is in fact following the later ruling:

| Stale clause | What it still says | What is true, and where |
|---|---|---|
| Art I.6 — the win condition | a booking reference **and a scannable ticket**; movie data arrives from an external source **on a schedule** | no scannable ticket (`SRC-001 §E E-9`); no external source and nothing on a schedule (`SRC-001 §E E-4`, `SRC-002 §E E-2`, `§E E-4`). **The corrected win condition is written into B3.3 of this document.** |
| Art V.8 — refunds | the cancellation questions **are open** | both were ruled on 2026-08-14: no refunds, no customer cancellation (`SRC-003 OPEN-CANCEL-01`, `OPEN-CANCEL-02`) |
| Art VIII.13 — outbound paths | names the withdrawn external movie source | corrected in `FR-ADR-065`; raised for the client, not amended |

---

# B2 — Business context and objectives

## B2.1 The situation the client is in

The client operates a cinema and sells tickets only at the counter. Customers queue, seats are marked
off by hand, and **the business has no record of who bought what** (`SRC-001 §1.1`).

On weekends the business loses sales because people leave rather than wait, and **it regularly has
disputes where two customers have been sold the same seat** (`SRC-001 §1.2`). That second sentence is
the one this whole product exists to answer.

What the client wants is a website where customers browse what is playing, choose their own seats,
pay, and arrive with a ticket on their phone (`SRC-001 §1.3`).

## B2.2 The venue, as it now stands

**One theatre with six halls** (`SRC-003 OPEN-SCOPE-01`, reading `C-2`, `PROVISIONAL`). Two managers
are assigned per hall, twelve in total. The hall sizes — 90, 120, 150, 180, 200 and 220 seats — are
`ASSUMED`: the client said "pick random" (`SRC-003 OPEN-SCALE-02`), so those numbers are a working
choice and **never a requirement**.

The reading is `PROVISIONAL` because `SRC-001 §1.1` says "we operate cinemas", plural, and
`SRC-001 §5.1.3` asks customers to filter by cinema, while the later and more specific ruling
describes one theatre. `SRC-003 C-2` records the reconciliation and `FR-ADR-010` records that the
business is not designed in a way that would block a second venue.

## B2.3 The market

India. Prices are in Indian rupees. Times are India time (`SRC-003 OPEN-LOCALE-01`).

## B2.4 The objectives, from `SRC-001 §2`

| # | Objective | State |
|---|---|---|
| `§2.1` | Let customers book seats online without staff involvement | live |
| `§2.2` | **Eliminate double-booking of seats completely. The client calls this non-negotiable** | live — the central objective |
| `§2.3` | Show current listings without staff typing them in every week | **withdrawn** by `SRC-001 §E E-6`. Staff entering them by hand is now the design, not the problem |
| `§2.4` | Give management visibility into occupancy, revenue and popular showtimes | live |
| `§2.5` | Reduce queue length at the counter | live |

## B2.5 Why this product is shaped the way it is

The client is also the developer and the operator, and **this product exists so that deploying and
operating it teaches them to run infrastructure** (`SRC-002 §1.1`, `§1.3`). Where two designs are
equally correct and one forces the operator to meet a real operational concern, that one wins, and
the reason is recorded (`FR-ADR-004`).

That is a business objective, not a technical preference, and it is why some requirements in B6 read
as deliberately harder than they need to be.

---

# B3 — Success criteria, restated so each is measurable

Each criterion is written so that it can be answered yes or no by someone watching, not judged.

## B3.1 The five criteria

**`SC-1` — A customer completes a booking end to end in under two minutes.**
`[SRC: SRC-001 §3.1 · FR-ADR-046]`
Measured from the moment a signed-in customer opens the seat map to the moment the confirmation is on
screen. **Stated honestly: a first-time visitor's run includes registration and will not meet two
minutes.** That is measured and reported as a separate figure rather than quietly excluded.
**This criterion must survive into the Bible as a binary acceptance criterion.**

**`SC-2` — Zero double-booked seats under concurrent load.**
`[SRC: SRC-001 §3.2 · SRC-001 §2.2 · SRC-001 §7.1 · FR-ADR-024 · FR-ADR-034]`
Fifty simultaneous attempts to buy the same seat produce **exactly one** success and forty-nine
customers who are told the seat has gone. Exactly one owner exists for that seat in the permanent
record — **checked in the record itself, not by trusting the website's answer**. Not "at most one":
zero winners is also a failure. The guard is additionally watched failing on purpose and then
restored, because a safeguard nobody has seen fail is decoration.
**This criterion must survive into the Bible as a binary acceptance criterion. It is never waived.**

**`SC-3` — Seat availability shown to the customer is accurate within a few seconds.**
`[SRC: SRC-001 §3.3 · SRC-001 §7.3 · FR-ADR-030 · FR-ADR-045]`
The worst case is about **thirteen seconds** out of date. That is stated rather than rounded down: it
is at the edge of "a few seconds" and it is the figure to revisit if the client finds the seat map
feels wrong. Being out of date never causes a double sale — a customer who clicks a seat that has
gone is told so.

**`SC-4` — withdrawn.** `SRC-001 §3.4` ("movie listings update automatically, with staff only
approving what appears") is withdrawn by `SRC-001 §E E-7`. There is no automatic listing update to
measure.

**`SC-5` — Management can see occupancy per show without asking anyone for a report.**
`[SRC: SRC-001 §3.5 · SRC-003 OPEN-REPORT-01 · FR-ADR-043]`
A manager signs in and reads their own halls' occupancy for a chosen day, week or month, with no
request to anyone and no waiting.

## B3.2 What is deliberately not a success criterion

The **peak-concurrency figure of fifty simultaneous bookers** is `ASSUMED` — the client said "you
pick" (`SRC-003 OPEN-SCALE-03`). It measures where performance degrades and **it proves nothing about
correctness.** `SC-2` is the correctness gate and it is separate and non-negotiable
(`FR-ADR-034`).

## B3.3 The win condition, corrected

> `CONSTITUTION.md` Art I.6 still describes a scannable ticket and movie data arriving on a schedule.
> Both were withdrawn on 2026-08-14. **This is the corrected win condition, taken from `SRC-003`.**

`[SRC: SRC-003 OPEN-ROLE-01 · OPEN-HOLD-01 · OPEN-PAY-01 · OPEN-TICKET-01 · OPEN-TMDB-01 ·
OPEN-SCOPE-01 · SRC-001 §3.2 · FR-ADR-006 · FR-ADR-034]`

A visitor browses the movies currently showing, registers, picks a showtime, sees a live seat map,
holds seats for three minutes, pays through the simulated payment step, and receives an **emailed
receipt carrying a unique booking reference**; **fifty simultaneous attempts on one seat produce
exactly one winner, proved in the permanent record**; an **admin creates a movie by hand** and it
appears to customers; a **manager sees their own halls' numbers and nobody else's**; and it runs on
hosting the client set up and deployed by hand.

**Everything past that line is fast-follow.** Define victory, then stop.

---

# B4 — The user types and what each needs to accomplish

## B4.1 Four roles, and why there are four

> ## ⚠ `PROVISIONAL` — one message from the client reverses this
> `[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 C-1 · SRC-001 §E E-1 · FR-ADR-009]`

`SRC-001 §4` named five user types. `SRC-002 §3.1` implied one. That is a contradiction inside the
client's own instructions, and it went back to them as `OPEN-ROLE-01` rather than being resolved by
picking a favourite.

**The answer created a second contradiction inside itself.** `OPEN-ROLE-01` says *"do not make more
personas… only 1 admin persona. admin can do all the stuff the managers can do."* The very next
answer, `OPEN-SCOPE-01`, describes *"2 managers per cinema hall"* who *"can see earnings movies for
the day, month, week and cannot add the new movies"*, and `OPEN-REPORT-01` gives managers a
dashboard.

**Read as four roles.** The prohibition is aimed at the cinema-staff and door-scanner persona, which
the same sentence kills explicitly, and at admin tiers — not at managers, whom two later answers
describe in operational detail. *"Admin can do all the stuff the managers can do"* states that admin
is a superset of manager, which presupposes that manager exists.

**The rejected reading** was three roles, with the manager dashboard served to admins filtered by
hall. It satisfies `OPEN-ROLE-01` literally, and it discards "2 managers per cinema hall" entirely
and puts twelve people on one shared admin account — which destroys the business's ability to answer
who changed what. `SRC-003 C-1` records both readings.

| Role | Account | What they need to accomplish |
|---|---|---|
| **Guest** | none | Browse the movies currently showing, see showtimes, and see the seat map. **Cannot hold a seat and cannot book.** |
| **Customer** | required | Hold seats, pay, receive a receipt, and see their own bookings and references at any time. |
| **Manager** | required | **Read only.** See the takings, occupancy and per-movie performance for the halls they are assigned to, by day, week and month. **They change nothing.** |
| **Admin** | required | Everything, including everything a manager can do. **The only role that changes anything at all.** |

## B4.2 The two roles that no longer exist

**There is no cinema-staff role and no door scanner** (`SRC-001 §E E-1`, `SRC-003 OPEN-TICKET-02`).
`SRC-001 §4.3` described a staff member checking customers in by scanning a ticket code, and
`SRC-001 §5.5.3` had staff validating tickets at the door. Both are withdrawn. **Entry is a person
reading the booking reference from the customer's emailed receipt and checking it by hand.**

## B4.3 A manager writes nothing, and that is a rule not a default

`[SRC: SRC-003 OPEN-OPS-03 · SRC-001 §7.4 · FR-ADR-009 · FR-ADR-011]`

The client ruled: *"the admin will only be the one who does changes in movie, cancel a show or other
priviledged things..no other persona."* **A manager who can change anything is a defect, not a
feature.** There is no small, safe write.

`OPEN-SCOPE-01`'s *"add more stuff that managers can do"* is read as **more reporting only**.
Anything beyond reporting is a proposal for the client to approve, never assumed scope.

## B4.4 A manager sees their own halls and nobody else's

`[SRC: SRC-001 §4.4 · SRC-003 OPEN-SCOPE-01 · SRC-003 C-2 · FR-ADR-011]`

"Two managers per hall" describes the client's current staffing. **It is an observation, not a limit** —
the business can employ one manager for a hall, or three, without anything having to be rebuilt. A
manager with no hall assigned yet sees an empty dashboard, which is the correct state for a new
account, not an error.

---

# B5 — Business requirements

## B5.1 Browsing and discovery

**`R-BRW-01` · Anyone can browse without an account** · `RULED`
`[SRC: SRC-001 §1.3 · SRC-001 §2.1 · SRC-001 §2.5 · SRC-001 §4.1 · SRC-003 OPEN-ROLE-01 · FR-ADR-009 · FR-ADR-014]`
Anyone who arrives at the site can see what is playing, pick a showtime, and see the seat map, with
no account and no sign-in. Booking is self-service from end to end, with no staff involvement.
- **Why the business needs it** — the business currently loses weekend sales to the queue. Someone who
  must register before they can see whether a seat is free will leave, and the queue at the counter
  stays where it is.
- **What it costs if absent** — the online channel converts worse than the counter it was built to
  relieve, and `§2.1` and `§2.5` both fail.

**`R-BRW-02` · Every movie shows the details a customer decides from** · `RULED`
`[SRC: SRC-001 §5.1.1 · FR-ADR-021]`
Each movie currently showing is presented with its poster, synopsis, running time, certification,
language and genre.
- **Why the business needs it** — those six things are what a customer chooses between films on. A
  listing without them is a title and a time.
- **What it costs if absent** — customers pick the wrong film, arrive at a certification they cannot
  watch, or do not choose at all.

**`R-BRW-03` · Customers can narrow the listing** · `RULED`
`[SRC: SRC-001 §5.1.3 · SRC-003 C-2 · SRC-003 OPEN-TMDB-01 · FR-ADR-010 · FR-ADR-046]`
A customer can narrow what is shown by cinema, date, language and format.
- **Why the business needs it** — a customer who knows they want a Friday evening show in a particular
  language should reach it in one step.
- **What it costs if absent** — the customer scrolls a full listing on a phone and abandons.
- **Note** — with one cinema there is nothing to choose between, so **the cinema filter is not put in
  front of a customer while only one exists**. The capability remains, because the client may add a
  second venue and `SRC-001 §6.6` forbids designing in a way that blocks that.

**`R-BRW-04` · A chosen movie and date show every showtime for it** · `RULED`
`[SRC: SRC-001 §5.1.4 · FR-ADR-018]`
Choosing a film and a date lists every showtime for that film on that date, in the cinema's own local
time.
- **Why the business needs it** — the customer's next decision after "which film" is "which time", and
  every showtime the business is selling should be on that list.
- **What it costs if absent** — shows sell poorly because customers never saw them, and the business
  cannot tell an unpopular showtime from an invisible one.

**`R-BRW-05` · With nothing chosen, the newest film is first** · `RULED`
`[SRC: SRC-003 OPEN-TMDB-01 · FR-ADR-021]`
The default order of the listing is newest first. The customer's chosen filter overrides it.
- **Why the business needs it** — the client asked for exactly this, and a new release is what most
  visitors arrive looking for.
- **What it costs if absent** — the biggest release of the week sits below an older film for no reason
  a customer can see.

**`R-BRW-06` · Customers see only what the admin has published, inside its window** · `RULED`
`[SRC: SRC-003 OPEN-ROLE-01 · SRC-003 OPEN-TMDB-03 · FR-ADR-021]`
A movie is visible to customers only when the admin has published it **and** the current date falls
inside the display window the admin set for it. Publication and the window are two separate decisions
and both must pass.
- **Why the business needs it** — the client asked for both by name: the admin adds a film, and sets
  "a deadline of how long this will stay". A film can be finished and ready before the week it is
  shown in.
- **What it costs if absent** — a half-written listing goes live, or a finished one has to be held back
  by leaving it unfinished, which is the same control doing two jobs badly.

## B5.2 The seat map

**`R-SEAT-01` · The seat map matches the real hall** · `RULED`
`[SRC: SRC-001 §5.2.1 · FR-ADR-016 · FR-ADR-045]`
The seat map a customer chooses from is the actual layout of that hall — the same rows, the same seat
numbers, the same aisles and gaps.
- **Why the business needs it** — the customer is choosing a physical place to sit. Their seat number
  is what they read at the door.
- **What it costs if absent** — customers arrive at a seat that is not where they thought it was, which
  is a dispute at the door and a staff member's time.

**`R-SEAT-02` · Available, held and sold seats are clearly distinguished — and so are the customer's own** · `RULED`
`[SRC: SRC-001 §5.2.2 · FR-ADR-045 · FR-ADR-051]`
A customer can tell at a glance which seats are free, which someone else is holding, which are sold,
and **which ones they themselves have just taken**. The four states are told apart by more than
colour alone.
- **Why the business needs it** — `§5.2.2` asks for three states; the customer's own selection is a
  fourth that nobody wrote down, and without it a customer cannot see which seats are theirs or undo
  a choice. Colour alone fails a colour-blind customer and fails again on a phone in sunlight.
- **What it costs if absent** — customers cannot complete a selection they can see, and the ones who
  can least afford the friction are the ones who hit it.

**`R-SEAT-03` · Seat categories are visible, because they cost different amounts** · `RULED` · rests on an `ASSUMED` list
`[SRC: SRC-001 §5.2.3 · SRC-003 OPEN-SEAT-01 · FR-ADR-016 · FR-ADR-037]`
Seats fall into categories that are priced differently, and the customer can see which category a
seat is in and what it costs before they choose it.
- **Why the business needs it** — the client prices them differently. A customer who cannot see the
  difference cannot make the choice the pricing exists to offer.
- **What it costs if absent** — a customer picks a premium seat believing it is standard and disputes
  the total at checkout.
- **`ASSUMED`** — the category names **Standard, Premium and Recliner** are the build session's
  choice; the client said "you pick" (`SRC-003 OPEN-SEAT-01`). **They never harden into a
  requirement**, and adding a fourth category must stay cheap.

**`R-SEAT-04` · The total updates as seats are selected** · `RULED`
`[SRC: SRC-001 §5.2.4 · FR-ADR-038 · FR-ADR-045]`
As the customer selects and deselects seats, the running total updates, and it is the same figure the
payment step will charge.
- **Why the business needs it** — a customer decides how many seats to buy against a price. A total
  that appears only at checkout is a decision made blind.
- **What it costs if absent** — abandoned checkouts at the moment the real number appears, and disputes
  where the customer says they were shown a different figure.

**`R-SEAT-05` · Any available seat may be chosen** · `RULED`
`[SRC: SRC-003 OPEN-SEAT-02 · OPEN-SEAT-03 · OPEN-SEAT-04 · FR-ADR-016]`
There are no seats sold only in pairs, no rule preventing a customer leaving a single empty seat
between bookings, and no accessible-seat marking. Every seat is sold on its own.
- **Why the business needs it** — the client ruled all three out explicitly, on the grounds that this
  is a demonstration project. Each removal takes a real complication out of the product.
- **What it costs if absent** — inventing any of the three would add a rule that can make a valid
  selection fail at checkout, for a business need the client said they do not have.
- **Recorded, not challenged** — a real cinema in India operates under accessibility obligations, and
  the client's ruling rests on there being no real customers. **This would need revisiting before
  anyone booked a real seat** (`SRC-003 OPEN-SEAT-02`). It is a known deferral, not an oversight.

**`R-SEAT-06` · What the customer sees is accurate within seconds** · `RULED`
`[SRC: SRC-001 §3.3 · SRC-001 §7.3 · FR-ADR-030 · FR-ADR-045]`
The seat map refreshes on its own while the customer looks at it. Worst case it is about thirteen
seconds out of date, and it never lags in a way the customer notices.
- **Why the business needs it** — two customers looking at the same busy Friday showtime must not both
  believe the same seat is free for a minute at a time.
- **What it costs if absent** — a customer picks a seat, is refused, picks another, is refused again,
  and leaves. Being out of date never causes a double sale — it only wastes the customer's attempt.

**`R-SEAT-07` · Six halls, of different sizes** · `PROVISIONAL` on the venue count · `ASSUMED` on the sizes
`[SRC: SRC-003 OPEN-SCOPE-01 · OPEN-SCALE-01 · OPEN-SCALE-02 · SRC-003 C-2 · FR-ADR-010 · FR-ADR-016]`
One theatre with six halls. The seat map is designed and tested against the **largest** hall on the
**smallest** phone screen.
- **Why the business needs it** — a seat map that works only at one size is a seat map that has not
  been tested, and the largest hall is the one that sells out.
- **What it costs if absent** — the busiest hall in the business is the one whose seat map is unusable.
- **`ASSUMED`** — the sizes 90, 120, 150, 180, 200 and 220 are the build session's spread; the client
  said "pick random" (`SRC-003 OPEN-SCALE-02`). **They never harden into a requirement.**
- **`PROVISIONAL`** — one cinema against several is a reading of two of the client's own answers
  (`SRC-003 C-2`). Nothing in the design may make a second venue impossible.

## B5.3 Holding seats while the customer pays

**`R-HOLD-01` · Chosen seats are held, and released on their own if the customer does not finish** · `RULED`
`[SRC: SRC-001 §5.2.5 · FR-ADR-025 · FR-ADR-027]`
When a customer proceeds with a selection, those seats are held for them while they pay, and if they
do not finish the seats become available again without anyone doing anything.
- **Why the business needs it** — without a hold, two customers pay for the same seat at the same
  moment. Without automatic release, an abandoned checkout takes a seat out of sale for good.
- **What it costs if absent** — either the double-sale disputes the product was commissioned to end, or
  a hall that slowly becomes unsellable as abandoned checkouts accumulate.

**`R-HOLD-02` · The hold is three minutes and it cannot be extended** · `RULED`
`[SRC: SRC-003 OPEN-HOLD-01 · FR-ADR-027]`
Seats are held for **three minutes** from the moment the hold is taken. The clock does not restart,
and there is no extension. A customer whose hold runs out selects again and competes on equal terms.
- **Why the business needs it** — three minutes is what the client ruled. An extension is a way for one
  customer to take a seat off sale indefinitely.
- **What it costs if absent** — on a sold-out Friday show, seats sit unbuyable behind abandoned tabs
  while paying customers are turned away.
- **Why this row exists in this shape** — `SRC-001 §10.9` asked how long seats should be held and
  answered *"we assumed 7 minutes"*; `SRC-002 §8.1.1` then stated seven minutes as a requirement.
  **An assumption became a specification without anyone deciding it.** When it was finally put to the
  client it came back **three minutes** — a different answer. Any document stating seven minutes is a
  defect.

**`R-HOLD-03` · The customer can see how long they have** · `RULED`
`[SRC: SRC-001 §5.2.5 · SRC-001 §5.2.6 · FR-ADR-047]`
The time remaining is shown from the moment the hold starts, the customer is warned before it runs
out, and when it does they are returned to the seat map with their selection restored rather than
dropped on a failure.
- **Why the business needs it** — three minutes is short. A customer who did not know they were on a
  clock loses their seats and blames the business.
- **What it costs if absent** — a customer who was about to pay is ambushed, and the sale is lost at the
  last step.

**`R-HOLD-04` · Ten seats maximum, and a selection succeeds or fails as a whole** · `RULED`
`[SRC: SRC-003 OPEN-BOOK-01 · SRC-001 §5.2.6 · FR-ADR-026]`
A customer may hold at most **ten** seats for one showtime, counting everything they are already
holding for it. A request for a group of seats succeeds completely or not at all — never partly.
- **Why the business needs it** — the client ruled ten. A group of four that silently becomes a group of
  three is worse for the customer than a clear refusal, because they discover it at the door.
- **What it costs if absent** — families are seated apart without being told, and one account can take a
  whole hall out of sale.

**`R-HOLD-05` · If someone takes a seat first, our customer is told at once, and told which** · `RULED`
`[SRC: SRC-001 §5.2.6 · FR-ADR-026 · FR-ADR-052]`
When one or more of the seats a customer wanted has gone, they are told immediately, **named which
seats went**, and left with their remaining selection intact so they can adjust it. The message says
what happened in plain words and never blames the customer for a race they lost.
- **Why the business needs it** — `§5.2.6` asks for this by name. Losing a seat is the system working
  correctly; the customer needs to know which one so their next attempt succeeds.
- **What it costs if absent** — the customer retries blindly, loses again, and leaves — turning a
  correct outcome into a lost sale.

**`R-HOLD-06` · Holding a seat requires an account; looking does not** · `RULED`
`[SRC: SRC-003 OPEN-BOOK-02 · SRC-001 §4.1 · FR-ADR-014 · FR-ADR-046]`
A guest may browse and see the seat map. The account is required at the moment they proceed with a
selection — before any seat is taken out of sale, not at the payment step. Their selection survives
registering or signing in, so they do not start over.
- **Why the business needs it** — the client ruled it: *"no booking without an account as the recipet
  will be sent via mail."* Stopping the guest before a seat is held, rather than at payment, means
  nobody without an account can take seats out of sale.
- **What it costs if absent** — either an anonymous visitor can hold every seat in a hall for three
  minutes at a time, or the customer is bounced to a registration form after choosing and returns to
  an empty seat map, which spends the two-minute budget in `SC-1` twice over.

**`R-HOLD-07` · Sales close fifteen minutes after the advertised start** · `PROVISIONAL`
`[SRC: SRC-003 OPEN-BOOK-03 · FR-ADR-042]`
Sales for a showtime close **fifteen minutes after** its advertised start time. **Anyone already
holding seats may finish paying.** A showtime past its cut-off is still shown, marked closed, with its
seats not selectable.
- **Why the business needs it** — a cinema runs trailers, so a customer arriving at the advertised time
  has not missed anything, and the business sells tickets it would otherwise refuse.
- **What it costs if absent** — either the business turns away customers who could still be seated, or
  it sells a ticket for a film that is nearly over.
- **⚠ `PROVISIONAL` — the direction could go either way.** The question asked how long **before** a show
  sales stop; the recommendation put to the client proposed a number of minutes **after** the start.
  The client answered *"yes 15 minutes"*. **The alternative reading is fifteen minutes before the
  start**, and the two are half an hour apart. `SRC-003 OPEN-BOOK-03` records both. One message from
  the client settles it, and reversing it changes nothing but the number and its sign.

## B5.4 Payment and confirming a booking

**`R-PAY-01` · Payment is taken before a booking is confirmed** · `RULED`
`[SRC: SRC-001 §5.3.1 · SRC-001 §2.1 · FR-ADR-029 · FR-ADR-041]`
A booking is confirmed only after payment has been taken for it. There is no confirm-now-pay-later
path.
- **Why the business needs it** — the client asked for it directly. A confirmed booking with no payment
  is a seat given away.
- **What it costs if absent** — the business holds seats for people who never paid, on exactly the shows
  where the seats are worth the most.

**`R-PAY-02` · A customer is never charged twice for one attempt** · `RULED`
`[SRC: SRC-001 §5.3.2 · FR-ADR-020 · FR-ADR-041]`
Refreshing the page, clicking twice, or retrying after a slow response returns the original booking.
It never creates a second booking and never takes a second payment.
- **Why the business needs it** — the client asked for it by name, including the refresh and double-click
  cases. A double charge is the fastest way to lose a customer permanently.
- **What it costs if absent** — refunds the business has no process for, because there are no refunds
  (`R-PAY-05`), and a customer holding two bookings for one set of seats.

**`R-PAY-03` · Payment is simulated for the whole of this project, and the customer is told so** · `RULED`
`[SRC: SRC-003 OPEN-PAY-01 · OPEN-PAY-02 · FR-ADR-041]`
No real money moves at any point, and **no real payment provider is ever connected**. The checkout
screen states plainly that no real payment is taken, and it is not possible to reach the payment step
in a deployed environment without that being deliberately and visibly switched on.
- **Why the business needs it** — the client ruled it twice: *"we'll have a fake button and flip the flag
  in DB. i do not want real payment."*
- **What it costs if absent** — **a simulated payment that looks real to a customer is the worst failure
  this product can produce.** It takes their seat, takes nothing else, and they find out at the door.

**`R-PAY-04` · No card details are ever collected, stored or shown** · `RULED`
`[SRC: SRC-001 §7.4 · SRC-003 OPEN-PAY-01 · FR-ADR-041]`
The product never asks for a card number, never records one, and never displays one — not in a
support screen, not in a record, not in demonstration data.
- **Why the business needs it** — with no real provider the business never needs card details, and never
  holding them removes an entire class of obligation and risk in one decision.
- **What it costs if absent** — a business with no operations team is holding payment data it has no
  reason to hold and no capacity to protect.

**`R-PAY-05` · A confirmed booking is final** · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-CANCEL-01 · OPEN-CANCEL-02 · SRC-001 §E E-2 · FR-ADR-013]`
There is **no customer cancellation and no refund of any kind**, partial or full, for any reason.
- **Why the business needs it** — the client ruled *"no refund policy"* and *"no forget this"*. A
  cancellation that returns no money is not something a customer would use, so the whole surface is
  out.
- **What it costs if absent** — a refund rule nobody decided, applied to real money, by whoever wrote
  the screen.
- **Recorded, not challenged** — **a customer who cannot attend loses their money.** That is the ruled
  behaviour for a demonstration project and it would need revisiting before a real customer ever
  booked.
- **Excluded is not blocked** — the business keeps the ability to add cancellation later without
  rebuilding what already exists (`SRC-001 §6.6`, `FR-ADR-013`).

## B5.5 Pricing and money

**`R-PRC-01` · Prices are in Indian rupees, to the whole paisa, in India time** · `RULED` · reserved: money
`[SRC: SRC-003 OPEN-LOCALE-01 · SRC-001 §7.6 · FR-ADR-036]`
The market is India. Every price and every total is an exact whole number of paise — one hundred
paise to the rupee. Every date and time the business reasons about is India time.
- **Why the business needs it** — the client named the market and the currency, and a cinema's showtime
  is a fact about a physical place at a local clock time.
- **What it costs if absent** — totals that drift by fractions of a paisa and never quite reconcile, and
  a "today's takings" figure that starts and ends at the wrong hour.
- **This is a one-way door.** Bookings are permanent (`SRC-001 §7.6`), so re-interpreting the unit later
  would silently rewrite what every past customer paid, with no way to tell which records meant what.
  **It is never changed by inference.**

**`R-PRC-02` · One base price per showtime, plus a fixed percentage per seat category** · `RULED`, with a `PROVISIONAL` part · reserved: money
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-001 §5.2.3 · SRC-001 §5.5.1 · FR-ADR-037]`
The admin sets a **base price for a showtime**. Each seat category adds a **fixed percentage** on top
of it, and that percentage is **the same in every hall and for every film**. There is no pricing by
time of day, by day of week, or by film beyond the base price itself.
- **Why the business needs it** — the client's own words: *"the admin will set the ticket price and more
  the premium ticket the more% fix price increase across all halls or any movie show."* The uniform
  percentage is what stops six halls drifting into six different price lists within a month.
- **What it costs if absent** — either a price table nobody can keep consistent, or an evening blockbuster
  priced the same as a weekday matinee.
- **⚠ `PROVISIONAL`** — *"the admin will set the ticket price"* does not say at which level. **Per
  showtime is a reading**, chosen because a single global price would make every show cost the same.
  Reversing it to one global price is a contained change (`FR-ADR-037`).

**`R-PRC-03` · One rounding rule, written down with a worked example, produces every price** · `RULED` · reserved: money, batched for reversal
`[SRC: SRC-003 OPEN-PRICE-01 · SRC-001 §5.2.4 · FR-ADR-038]`
A percentage of an exact number of paise does not divide evenly. **The rounding rule is stated in
writing with a worked example**, it is applied **to each seat and never to the total**, and one rule
produces the figure on the seat map, the figure at checkout, the figure on the receipt and the figure
in the dashboard.
- **Why the business needs it** — an unstated rounding rule is how two screens disagree about a total.
  Rounding per seat is what makes the per-seat prices the customer was shown add up to the total they
  were shown.
- **What it costs if absent** — a customer sees three seats at one price each and a total that is a
  paisa different, and the business has no answer for which is right.
- **Batched for the client to reverse** — rounding is money, and the rule itself is reversible because
  what a past customer paid is never recomputed (`R-PRC-04`).

**`R-PRC-04` · The price quoted is the price paid, and a later change never rewrites a past booking** · `RULED`
`[SRC: SRC-001 §5.2.4 · SRC-001 §7.6 · FR-ADR-035 · FR-ADR-039]`
The price is fixed at the moment the customer's seats are held, so an admin editing a price mid-checkout
cannot change what that customer is charged. Once a booking exists, its amount and the figures that
produced it are kept, and nothing ever recalculates them.
- **Why the business needs it** — a customer shown ₹950 and charged ₹1,100 has been shown a false price.
  A receipt from August whose figure changes when a price is edited in September is not a record.
- **What it costs if absent** — the business cannot answer a single dispute about a charge, because the
  evidence moves every time someone edits a price.

**`R-PRC-05` · No tax line, no discounts, no fees** · `RULED` · reserved: money and legal
`[SRC: SRC-003 OPEN-PRICE-02 · OPEN-PRICE-03 · FR-ADR-040]`
The amount charged is the sum of the seat prices, with nothing added and nothing taken away. There is
no separate tax line, no discount code, no concession or student rate, and no booking or convenience
fee.
- **Why the business needs it** — the client answered *"no discout for now"* and, on tax, *"no"*. Every
  one of these is a money decision and none was made.
- **What it costs if absent** — a discount rule or a tax split invented by whoever built the checkout
  screen.
- **Recorded, not challenged** — a real cinema in India would show GST on a ticket. **The recorded total
  is a single figure and cannot be split into net and tax afterwards**, because nothing records what
  portion was ever meant to be tax. That is the irreversible part of this decision and it is written
  down so it is a known deferral rather than something an accountant discovers.

## B5.6 The ticket: the receipt and its reference

**`R-TKT-01` · Every confirmed booking gets a unique reference** · `RULED`
`[SRC: SRC-001 §5.3.3 · SRC-001 §E E-9 · SRC-003 OPEN-TICKET-01 · FR-ADR-015]`
Every confirmed booking carries a reference that belongs to it alone.
- **Why the business needs it** — `§5.3.3` asked for "a booking reference and a scannable ticket". The
  scannable ticket is withdrawn by erratum `E-9`; **the reference is what remains, and it is now the
  only thing that gets a customer into the hall.**
- **What it costs if absent** — the business has no way to identify a booking at the door or in a
  dispute.

**`R-TKT-02` · A receipt is emailed, and it is the customer's ticket** · `RULED`
`[SRC: SRC-001 §5.3.4 · SRC-003 OPEN-TICKET-01 · OPEN-EMAIL-01 · FR-ADR-031 · FR-ADR-048]`
On confirmation the customer is sent a receipt by email carrying the booking reference, the seat
numbers, the hall, the showtime, the film and the amount paid. The receipt is dispatched reliably: if
the sending step is unavailable, the receipt is delayed and **not lost**, and it is never sent twice
for one booking.
- **Why the business needs it** — the client ruled it: *"the receipt sent on email which has a unique ID.
  that will be shown at the entrance."* This one email is the load-bearing artefact of the entire
  product.
- **What it costs if absent** — **the customer has paid and cannot enter the hall.** A customer holding
  two receipts for one booking cannot tell which one the business knows about.

**`R-TKT-03` · The reference is on screen and in the customer's own booking list too** · `RULED`
`[SRC: SRC-003 OPEN-EMAIL-01 · SRC-001 §5.4.2 · FR-ADR-048]`
The reference is shown prominently on the confirmation screen the moment the booking is confirmed,
independently of the email, and it stays available in the customer's own booking list. The
confirmation screen states what has actually happened — that the booking is confirmed and a receipt is
on its way to a named address — and never claims an email has already been sent.
- **Why the business needs it** — the client asked for the reference on screen specifically, because the
  email is the only proof of purchase. A customer who deletes the email can sign in and find it.
- **What it costs if absent** — the whole product hangs on one email arriving, with no second route to
  the one thing the customer paid for.

**`R-TKT-04` · The reference can be read aloud and typed by a person** · `RULED`
`[SRC: SRC-003 OPEN-TICKET-01 · FR-ADR-015]`
The reference avoids characters people confuse — no zero against a letter O, no one against a letter
I or a lower-case L — and is grouped so it can be read from a phone screen and typed correctly by
someone standing at a door. A mistyped reference fails cleanly; **nothing guesses what the customer
meant.**
- **Why the business needs it** — the client ruled the reference is checked by a human at the entrance,
  not by a machine. Its whole design constraint is that a person reads it out.
- **What it costs if absent** — queues at the door while staff and customers argue about a character, and
  a system that guesses can let the wrong person into the hall.

**`R-TKT-05` · Entry is a manual human check** · `RULED`
`[SRC: SRC-003 OPEN-TICKET-02 · SRC-001 §E E-3 · FR-ADR-048]`
A person at the entrance reads the reference on the customer's receipt and checks it. There is **no
scanning device, no validation step, and nothing that marks a reference as used**.
- **Why the business needs it** — the client ruled it: *"we will have manual check up with the unique ID
  sent out to the customer."*
- **What it costs if absent** — building a scanner and a validation flow the client explicitly refused.
- **Accepted weakness, stated** — **nothing prevents the same reference being presented twice.** That is
  accepted for a demonstration project and it is a real hole in a live one
  (`SRC-003 OPEN-TICKET-02`).

**`R-TKT-06` · What the customer is told when the receipt cannot be delivered** · **`OPEN`** · reserved: product
`[SRC: SRC-003 OPEN-EMAILFAIL-01 · FR-ADR-049]`
**Not decided, and not invented here.** The customer has paid; there are no refunds; the receipt is
their only proof of purchase and their only way into the hall. If the email definitively fails, what
are they told, when, by what route — and is the booking still valid?
- **Why the business needs an answer** — three of the client's own rulings combine into a failure mode
  none of them anticipated alone, and its outcome is a paying customer standing outside a hall.
- **What it costs while it stays open** — everything that can be done without a ruling **has been
  done**: the reference is on the confirmation screen, in the customer's booking list, and the
  receipt can be re-sent. What the customer is *told* when the send has definitively failed remains
  the client's to decide. **Escalate, never invent.**

## B5.7 Customer accounts

**`R-ACC-01` · A customer registers and signs in with an email address and a password** · `RULED`
`[SRC: SRC-001 §5.4.1 · FR-ADR-050]`
Registration and sign-in use an email address and a password, on one screen, so a new customer and a
returning one arrive at the same place with the same context.
- **Why the business needs it** — an account is required to book, so registration sits directly on the
  path to every sale.
- **What it costs if absent** — friction at the one step every first-time customer must pass.

**`R-ACC-02` · A customer sees their own bookings, upcoming and past** · `RULED`
`[SRC: SRC-001 §5.4.2 · FR-ADR-048]`
A signed-in customer sees their upcoming and past bookings, each with its reference, seats, hall,
showtime and amount paid.
- **Why the business needs it** — the client asked for it, and it is the customer's second route to the
  reference when the email is gone.
- **What it costs if absent** — every lost email becomes a support request to a business with no
  support team.

**`R-ACC-03` · Every booking belongs to one registered customer** · `RULED`
`[SRC: SRC-001 §9.2 · SRC-003 OPEN-BOOK-02 · FR-ADR-014]`
One booking belongs to one customer, one showtime and one or more seats. There is no anonymous order
and no guest checkout. The receipt goes to the account's own email address.
- **Why the business needs it** — `§9.2` was listed as an assumption the client asked to have confirmed;
  `OPEN-BOOK-02` confirms it. It is what makes `R-ACC-02` and `R-TKT-03` possible at all.
- **What it costs if absent** — bookings nobody owns, which cannot be found again by the customer who
  paid for them.

**`R-ACC-04` · A customer who forgets their password can get back in** · `RULED`
`[SRC: SRC-001 §5.4.1 · SRC-003 OPEN-OPS-02 · FR-ADR-050]`
There is a way to recover access to an account without help from anyone.
- **Why the business needs it** — nothing is ever deleted (`R-ADM-07`), so an email address stays taken
  permanently. Without recovery, a forgotten password loses the customer every booking they have ever
  made and they cannot register again with the same address.
- **What it costs if absent** — an unrecoverable account, and a support request to a business with
  nobody to answer it.

**`R-ACC-05` · A customer's seat selection survives signing in** · `RULED`
`[SRC: SRC-001 §3.1 · SRC-003 OPEN-BOOK-02 · FR-ADR-046]`
A visitor who chooses seats and is then asked to sign in or register comes back to the same showtime
with the same seats still chosen. If one of them has gone in the meantime, they are told before they
proceed.
- **Why the business needs it** — `SC-1` allows two minutes end to end. A customer who has to start over
  has spent that budget twice.
- **What it costs if absent** — the highest-intent visitors on the site — the ones who have already
  chosen where to sit — abandon at the last step.

## B5.8 What the admin manages

**`R-ADM-01` · The admin creates every film by hand** · `RULED`
`[SRC: SRC-003 OPEN-ROLE-01 · OPEN-TMDB-01 · OPEN-TMDB-04 · SRC-001 §E E-4 · FR-ADR-006 · FR-ADR-021 · FR-ADR-061]`
The admin enters each film themselves — title, poster, the details customers see, and the window it
is shown in. **There is no external source of film information and no automatic import.** Posters the
admin uploads are held by the business and served from the business's own address; nothing links to
someone else's.
- **Why the business needs it** — the client ruled it: *"rather make it simple we'll no longer pull the
  movies. the admin will upload them manually."* This is the largest change of scope on the project.
- **What it costs if absent** — building and operating an integration the client explicitly removed, and
  an entire class of failure where an automatic update silently overwrites something a person typed.

**`R-ADM-02` · The admin decides when a film becomes visible** · `RULED`
`[SRC: SRC-003 OPEN-TMDB-03 · OPEN-ROLE-01 · SRC-001 §E E-8 · FR-ADR-021]`
Publishing a film and setting the dates it is shown between are two separate decisions, both the
admin's, and both must pass before a customer sees it.
- **Why the business needs it** — the client asked for "a deadline of how long this will stay". A film
  can be finished before the week it runs in, and those are different questions.
- **What it costs if absent** — half-finished listings go live, or finished ones are held back by being
  left deliberately incomplete.

**`R-ADM-03` · The admin creates every showtime, and nothing creates one automatically** · `RULED`
`[SRC: SRC-001 §5.5.1 · SRC-001 §9.4 · SRC-003 OPEN-OPS-03 · FR-ADR-021 · FR-ADR-035]`
The admin creates a showtime by choosing a film, a hall, a date, a time and a base price.
**Showtimes are always a human decision. Nothing in this system creates one on its own, ever.**
- **Why the business needs it** — `§5.5.1` asks for it and `§9.4` states it as an assumption the client
  asked to have confirmed. Scheduling is a commercial judgement about a physical room.
- **What it costs if absent** — the business finds itself committed to screenings nobody chose to run.
- **Note** — `§5.5.1` gives this to the *manager*. **It is now the admin's**, because
  `SRC-003 OPEN-OPS-03` puts every change on the admin alone.

**`R-ADM-04` · The admin configures halls, and a hall's layout is fixed once it is selling** · `RULED`
`[SRC: SRC-001 §9.3 · SRC-001 §7.6 · FR-ADR-016 · FR-ADR-022]`
The admin configures each hall's seats and categories. **Once a showtime exists on a hall, seats can
be added and seats can be taken out of service, but a seat cannot be removed, renumbered or moved to a
different category.** A hall with no showtimes yet can be changed freely.
- **Why the business needs it** — `§9.3` says layouts change rarely once a screen is configured. A seat
  renumbered after it was sold changes which seat a past customer believes they bought, and the
  business can no longer answer for its own records.
- **What it costs if absent** — historical bookings that point at seats that no longer exist, and a
  reported occupancy figure for last month that changes when a seat is retired this month.
- **Stated plainly** — this is a real operational limit and the client will feel it the first time they
  mistype a seat number after a showtime exists. The admin documentation must say so rather than let
  it be discovered.

**`R-ADM-05` · Every change belongs to the admin alone** · `RULED`
`[SRC: SRC-003 OPEN-OPS-03 · SRC-001 §7.4 · FR-ADR-009 · FR-ADR-011]`
Creating or editing a film, publishing one, setting a display window, creating a showtime, setting a
price, changing a category percentage, configuring a hall, and creating or assigning a manager are
**all the admin's and only the admin's**. Managers read. Customers reach none of it.
- **Why the business needs it** — the client ruled it in one sentence, and `§7.4` requires that staff and
  management functions are not reachable by customers.
- **What it costs if absent** — twelve people who were given a reporting account can change what
  customers are charged.

**`R-ADM-06` · Every change is recorded with who, when, and what it was before** · `RULED`
`[SRC: SRC-001 §7.6 · SRC-003 OPEN-OPS-03 · FR-ADR-019]`
Every change an admin makes is recorded alongside the change itself — who made it, when, what it was
before and what it became. The record cannot be altered or removed afterwards, and either the change
and its record both happen or neither does.
- **Why the business needs it** — the client asked to be able to read who changed a price. A record
  written after the fact is missing exactly the changes that went wrong.
- **What it costs if absent** — the business cannot answer why a price changed, who published a film, or
  who took a hall out of service.

**`R-ADM-07` · Nothing is ever deleted** · `RULED` · reserved: legal
`[SRC: SRC-003 OPEN-OPS-02 · SRC-001 §7.6 · FR-ADR-012]`
Booking records are kept **indefinitely**. Nothing prunes them, nothing expires them, and nothing
removes one as a side effect of removing something else. Films, halls and showtimes that stop being
current are **withdrawn from view rather than removed**, so every historical booking still resolves to
a real film in a real hall.
- **Why the business needs it** — the client answered *"for now forever we'll change that later if i
  ask."* It is also what makes `§7.6` — answering who booked a seat, for any seat, at any time — true
  rather than aspirational.
- **What it costs if absent** — a booking that cannot be explained because the film it was for is gone.
- **Stated plainly** — storage grows without limit by design. It is far from a problem at six halls, and
  it is the kind of thing that is invisible until it is urgent, so it belongs on the operator's list
  of figures to watch.
- **Also stated** — a record kept forever with no backup is a record kept until the first failure.
  Recoverability is `R-QLY-07` and `FR-ADR-070`.

**`R-ADM-08` · Withdrawing a showtime that already has paid bookings** · **`OPEN`** · reserved: money, irreversible
`[SRC: SRC-003 OPEN-SHOWCANCEL-01 · OPEN-OPS-03 · OPEN-CANCEL-02 · FR-ADR-023]`
**Not decided, and not invented here.** `OPEN-OPS-03` names *"cancel a show"* as something only the
admin does; `OPEN-CANCEL-02` said to forget cinema-cancelled shows and there are no refunds. Those
customers have paid. **What happens to their bookings, and to their money?**
- **Why the business needs an answer** — a genuinely cancelled screening is a real event in a real
  cinema, and every available answer is a decision about money that no model may make.
- **What it costs while it stays open** — **the admin has no way to withdraw a showtime in this version**,
  and that gap is stated to the client rather than left to be found. It is the only capability the
  client named that this version does not deliver. An unbuilt capability is recoverable; an unrefunded
  customer is not.

## B5.9 Reporting for managers and admins

**`R-RPT-01` · Managers and admins have a dashboard covering day, week and month** · `RULED`
`[SRC: SRC-003 OPEN-REPORT-01 · OPEN-SCOPE-01 · SRC-001 §2.4 · FR-ADR-043]`
Managers and admins sign in to a dashboard covering the day, the week and the month. Periods are whole
calendar periods in India time, so "today's takings" starts and ends when the business's day does.
- **Why the business needs it** — the client ruled it: *"reporting will be done to the mamagers and admins
  as they will have a dashboard"*, covering *"the day, month, week"*.
- **What it costs if absent** — management runs the cinema on impressions, which is what `§2.4` says it
  is doing today.

**`R-RPT-02` · Occupancy, takings and per-film performance, without asking anyone** · `RULED`
`[SRC: SRC-001 §5.5.2 · SRC-001 §3.5 · SRC-003 OPEN-SCOPE-01 · FR-ADR-043]`
The dashboard shows occupancy and takings per show, per day and per film, and how each film is
performing. **Nobody has to produce a report and nobody has to be asked for one.**
- **Why the business needs it** — `§5.5.2` asks for exactly these three cuts and `§3.5` says management
  should not have to ask anyone.
- **What it costs if absent** — the reporting is a person's job again, which is what the product was
  meant to remove.

**`R-RPT-03` · A manager sees their own halls and nobody else's** · `RULED`
`[SRC: SRC-001 §4.4 · SRC-003 OPEN-SCOPE-01 · SRC-003 C-2 · FR-ADR-011]`
A manager's figures cover the halls they are assigned to. An admin sees everything. **A manager
reading another hall's numbers is a breach, not a reporting feature.**
- **Why the business needs it** — `§4.4` scopes a manager's authority to their own part of the business,
  and the client described managers per hall.
- **What it costs if absent** — twelve people each see the whole business's takings, which is a decision
  the client never made.
- **How it is checked** — a manager's own halls must return **real, non-zero figures** and another
  manager's halls must be refused. Checking only that the second is refused would pass against a
  dashboard that returns nothing for anybody.

**`R-RPT-04` · Takings mean money actually taken, and reported figures do not move** · `RULED` · batched for reversal
`[SRC: SRC-001 §5.5.2 · SRC-001 §7.6 · FR-ADR-039 · FR-ADR-043]`
Takings are money **actually collected**, not seats held and not bookings that failed to pay. A show's
takings are counted against **the date of the show**, because the manager is reading how each show
performed. Occupancy is measured against the hall's seat count **as it was when the showtime was
created**, so retiring a seat next month never changes last month's reported figure.
- **Why the business needs it** — a figure that fluctuates as customers browse is not a takings figure,
  and a report whose history changes cannot be acted on.
- **What it costs if absent** — management acts on numbers that disagree with the numbers they saw last
  week, and stops trusting the dashboard.
- **Batched for the client to reverse** — counting a ticket bought on Monday for Friday's show against
  Friday is the reading that serves a manager reading per-show performance. An accountant would
  reasonably want it counted on Monday. **The client owns which.**

**`R-RPT-05` · No export** · `RULED`
`[SRC: SRC-003 OPEN-REPORT-02 · FR-ADR-043]`
The dashboard is on screen only. There is no download to a spreadsheet or any other file.
- **Why the business needs it** — the client answered *"No"*. It also keeps customer-level booking data
  off any download path, which for a business with no operations team is a real reduction in exposure.
- **What it costs if absent** — a file of customer booking data that leaves the business's control the
  moment it is created.

## B5.10 Quality the business expects

**`R-QLY-01` · A seat cannot be sold twice, under any load** · `RULED` · **never waivable**
`[SRC: SRC-001 §2.2 · SRC-001 §3.2 · SRC-001 §7.1 · SRC-001 §1.2 · FR-ADR-024]`
**A seat is never sold to two customers. Not rarely, not under normal load — never.** The guarantee is
enforced in two independent places, so that if the faster of the two is ever wrong, the slower one
still refuses. **The second of those may not be waived, for any reason, at any confidence.**
- **Why the business needs it** — the client calls it *non-negotiable* (`§2.2`) and says a seat sold
  twice is a failure of the whole system regardless of load (`§7.1`). It is the dispute the business
  has today (`§1.2`) and the reason this product was commissioned.
- **What it costs if absent** — two customers at one seat, in public, in front of a queue — the exact
  failure the product exists to end, now happening faster and at greater volume than at the counter.

**`R-QLY-02` · The proof is a deliverable, and the safeguard is watched failing** · `RULED` · **never waivable**
`[SRC: SRC-001 §3.2 · SRC-003 OPEN-SCALE-03 · FR-ADR-034]`
`SC-2` is demonstrated, not asserted: fifty simultaneous attempts on one seat, exactly one winner,
checked in the permanent record and not only in the website's answer. **Then the safeguard is removed
on purpose, the failure is watched happening, and it is put back and verified.**
- **Why the business needs it** — a safeguard nobody has watched fail is decoration. A check that passes
  because it never actually ran passes just as convincingly as one that works.
- **What it costs if absent** — the business believes it has solved its central problem and finds out
  otherwise from a customer.
- **`ASSUMED`** — the fifty-simultaneous-bookers load figure is the build session's choice; the client
  said "you pick" (`SRC-003 OPEN-SCALE-03`). **The correctness gate is not assumed and is separate.**

**`R-QLY-03` · The site stays usable through the busiest period** · `RULED`
`[SRC: SRC-001 §7.2 · SRC-003 OPEN-SCALE-03 · FR-ADR-034]`
The site stays usable on Friday and Saturday evenings, which is when the business takes its money.
- **Why the business needs it** — the client named those two evenings. An outage at any other time is an
  inconvenience; an outage then is the week's takings.
- **What it costs if absent** — the product fails precisely when it is worth the most, and the counter
  queue it was built to relieve is the fallback.

**`R-QLY-04` · Pages feel immediate, and the seat map in particular does not lag** · `RULED`
`[SRC: SRC-001 §7.3 · FR-ADR-030 · FR-ADR-045]`
Pages respond without a visible wait, and the seat map — the screen customers spend the most time on —
must not lag.
- **Why the business needs it** — the client singled the seat map out. It is the screen where the customer
  decides, and a slow one loses the decision.
- **What it costs if absent** — customers abandon at the screen closest to the sale.

**`R-QLY-05` · A booking takes under two minutes** · `RULED`
`[SRC: SRC-001 §3.1 · FR-ADR-046]`
See `SC-1`. Measured for a signed-in customer from the seat map to the confirmation, with the
first-time visitor's figure reported separately and honestly.
- **Why the business needs it** — the product's purpose is to be faster than standing in a queue.
- **What it costs if absent** — the online channel is not obviously better than the counter, so the queue
  does not shorten.

**`R-QLY-06` · Passwords are handled properly, and management functions are unreachable by customers** · `RULED`
`[SRC: SRC-001 §7.4 · FR-ADR-009 · FR-ADR-050]`
Customer passwords are stored so that they cannot be read back, and the checks that keep customers out
of management functions are applied in **one place** rather than repeated at every screen.
- **Why the business needs it** — the client asked for both. A check repeated in fifty places is a check
  that eventually misses one.
- **What it costs if absent** — a customer reaching an admin function is a business-ending event for a
  cinema that has no operations team.

**`R-QLY-07` · A restart mid-booking loses nobody money and nobody's seat** · `RULED`
`[SRC: SRC-001 §7.5 · FR-ADR-029 · FR-ADR-033 · FR-ADR-070]`
If the system restarts in the middle of a booking, no customer loses money and no customer ends up
holding a seat they did not get. Records are recoverable after a mistake, and **a recovery that has
never been performed does not count as one** — it is rehearsed, dated and recorded.
- **Why the business needs it** — the client asked for it directly. Money taken with no seat, or a seat
  given with no money, are both failures the customer discovers at the door.
- **What it costs if absent** — a restart during Friday evening leaves a set of customers who paid for
  nothing, and no way to tell which ones.

**`R-QLY-08` · The business can answer "who booked this seat and when" for any seat** · `RULED`
`[SRC: SRC-001 §7.6 · SRC-001 §1.1 · FR-ADR-012 · FR-ADR-019 · FR-ADR-039]`
For any seat, at any time, the business can say who booked it, when, and what they paid.
- **Why the business needs it** — `§1.1` says the business has no record of who bought what today, and
  `§7.6` states the requirement. It is the answer to every dispute at the door and every question about
  a charge.
- **What it costs if absent** — every dispute is settled by whoever argues hardest.

**`R-QLY-09` · The site works well on a phone, and every customer has an email address** · `RULED`
`[SRC: SRC-001 §9.1 · SRC-001 §6.1 · FR-ADR-044 · FR-ADR-051]`
The business assumes every customer has a smartphone and an email address. **The site works well on a
phone**, including the largest hall's seat map on the smallest common screen, and it is usable by
someone operating it without a mouse or without sight.
- **Why the business needs it** — `§9.1` is the client's own stated assumption, confirmed by `§6.1`'s
  ruling that a website which works well on a phone is enough. The receipt is emailed, so the email
  address is not optional.
- **What it costs if absent** — the product is built for a device the customer does not use to buy
  tickets, and the ticket is sent to an address they do not have.
- **Recorded, not claimed** — a recognised accessibility standard is adopted as the target and every
  colour contrast figure is **calculated and written down rather than asserted**. No conformance is
  claimed, because that would need testing this project has not done. **One deliberate deviation is
  recorded**: the three-minute hold is a time limit that cannot be extended, because extending it
  would let one customer take a seat off sale indefinitely (`FR-ADR-051`).

**`R-QLY-10` · When something goes wrong, the customer is told what happened in plain words** · `RULED`
`[SRC: SRC-001 §5.2.6 · SRC-001 §8.2 · FR-ADR-052]`
Every failure a customer can hit says what happened and what to do next, literally, with no figures of
speech. Nothing internal to the business is shown. On a genuine system failure the customer is given a
short code they can quote, which the one person operating the business can trace.
- **Why the business needs it** — `§5.2.6` requires it for the seat race; every other failure was
  unspecified and would otherwise be invented by whoever wrote each screen. One person operates this
  business and a customer's report is often the first they hear of a problem.
- **What it costs if absent** — customers who cannot tell a system fault from their own mistake, and an
  operator with no way to find the incident the customer is describing.

## B5.11 The four questions that are still open

**No model decides these, at any confidence.** Each is named, owned by the client, and deliberately
not answered. **An open question filled in with something sensible is the cardinal failure of this
project.**

| ID | The question | Class | Carried by |
|---|---|---|---|
| `OPEN-TLS-01` | Securing the connection needs a domain name; the client is looking for one. Until then the deployed environment carries no real customer data and is never called production. | reserved: product · `DEFERRED` | `FR-ADR-069`, `R-CON-08` |
| `OPEN-ATTRIB-01` | The client supplies the posters and titles themselves. If that material comes from a source with a credit condition, the obligation applies. **Where does it come from?** | reserved: legal | `FR-ADR-007`, `R-CON-09` |
| `OPEN-SHOWCANCEL-01` | An admin withdraws a showtime that already has paid bookings. What happens to those bookings and to the money? | reserved: money, irreversible | `FR-ADR-023`, `R-ADM-08` |
| `OPEN-EMAILFAIL-01` | The receipt is the customer's only proof of purchase and only way into the hall. What happens when it definitively fails to arrive after payment? | reserved: product | `FR-ADR-049`, `R-TKT-06` |

**Standing constraint while `OPEN-ATTRIB-01` is open:** no licensed image or synopsis enters this
product. Demonstration content uses obvious placeholders, so the product can be built and shown end to
end without waiting for the answer.

---

# B6 — Constraints the business imposes

**`R-CON-01` · The infrastructure budget is effectively zero** · `RULED`
`[SRC: SRC-001 §8.1 · SRC-002 §5 · SRC-002 §5.1 · FR-ADR-064]`
The business will not pay for hosting. Everything runs on the smallest practical footprint, inside the
hosting provider's no-cost allowance, and nothing is designed that would require paying for it.
- **Why the business needs it** — the client stated it plainly and it is the hardest constraint on the
  whole project.
- **What it costs if absent** — a monthly bill for a demonstration project, which is the reason the
  project would stop.
- **The consequence, stated rather than absorbed** — the total working memory available to everything
  this product runs is about **one gigabyte**, shared with the machine's own software. **If something
  will not fit, the client is told, with the number, rather than quietly worked around**
  (`FR-ADR-064`). Every figure currently written down for this is **an estimate, never a measurement** —
  nothing has been run yet, and the estimates are replaced with measured numbers at the end of the
  first phase.

**`R-CON-02` · One person operates this, and there is no operations team** · `RULED`
`[SRC: SRC-001 §8.2 · SRC-003 OPEN-NAME-01 · FR-ADR-052 · FR-ADR-056 · FR-ADR-068]`
There is no operations team. **One person is the client, the developer, the money-signer and the
operator, and there is no backup** — stated affirmatively, not left blank. Everything must therefore be
understandable and recoverable by that one person.
- **Why the business needs it** — the client said so, and named themselves as the only decider.
- **What it costs if absent** — a product that needs a team the business does not have.
- **Two consequences that follow, stated plainly** — **there is no escalation path and there cannot be.**
  If the one alert is not read, nothing else happens. And because the same person is client, builder
  and approver, **the delay in which a bad decision usually becomes visible never occurs** — which is
  why every irreversible decision on this project is graded by a fresh, independent reader, and why
  that substitution is recorded rather than passed off as review.

**`R-CON-03` · No expensive vendor lock-in** · `RULED`
`[SRC: SRC-001 §8.3 · FR-ADR-001]`
The business will not become dependent on an expensive managed service. The list of what the product
may be built from is fixed, and adding to it requires the client's permission first — which has been
sought and granted exactly once, for sending email.
- **Why the business needs it** — the client asked for it, and every service added is a cost and a
  commitment the business cannot easily reverse.
- **What it costs if absent** — a bill and a dependency the business did not choose and cannot leave.

**`R-CON-04` · Alerting reaches one person and watches one thing** · `RULED`
`[SRC: SRC-003 OPEN-OPS-01 · SRC-001 §8.2 · FR-ADR-068]`
There is **one** alert, delivered to the operator's own address: the product has stopped running.
**Everything else is unwatched, and the list of what nobody is watching is written down honestly** —
including, worst of all, **a customer whose receipt failed repeatedly and who has therefore paid and
cannot enter the hall.**
- **Why the business needs it** — the client ruled one alert. One alert is honest; presenting one alert
  as monitoring is not.
- **What it costs if absent** — the business believes it is being watched when it is not. **A product
  that is running but broken is invisible today**: the alert fires when nothing is running, not when
  everything is running and every request fails.
- **The single most valuable thing the client could add** is an alert on repeatedly failed receipts. It
  is recommended in writing and **not adopted**, because adding alerts the client did not ask for is
  both inventing scope and doing the client's own work for them.

**`R-CON-05` · Delivery is phased, and the client is told what to test at the end of each phase** · `RULED`
`[SRC: SRC-002 §12 · SRC-002 §12.1 · SRC-003 OPEN-SCOPE-01 · SRC-002 §E E-3 · FR-ADR-006]`
Nothing is built all at once. **Eight phases**, and each closes only when the client has been told what
to test:

| Phase | What the business gets |
|---|---|
| 1 | the skeleton, deployed by the client against something trivial so the process is learned first |
| 2 | the record structure and the admin's ability to set up halls, showtimes and prices |
| 3 | public browsing, listings and the seat map to look at |
| 4 | holding seats, confirming a booking, and **the concurrency proof** |
| 5 | the receipt email |
| 6 | **the admin's film management** *(this replaced the withdrawn automatic import)* |
| 7 | measurement, limits, the load test and the operating manual |
| 8 | **the manager and admin dashboard** *(new, added by `SRC-003`)* |

- **Why the business needs it** — the client asked for it, so they can deploy something trivial before
  something valuable, and so nothing is delivered that they have not been told how to check.
- **What it costs if absent** — a large delivery the client cannot verify, in a project whose stated
  purpose is that the client learns by doing each step.

**`R-CON-06` · Nothing in this system runs on a schedule** · `RULED`
`[SRC: SRC-003 OPEN-PROC-01 · OPEN-TMDB-01 · SRC-002 §E E-4 · FR-ADR-005]`
There is **no scheduled job of any kind**, and no later design may introduce one.
- **Why the business needs it** — with the automatic film import removed there is nothing left to run on
  a schedule, and every long-running process costs memory the business does not have.
- **What it costs if absent** — memory spent on something that runs nothing, and an idle capability that
  invites work to be invented for it.
- **The discipline this imposes** — anything that would otherwise be "the nightly job will fix it" has to
  be correct when it is written. That is stricter, and it is deliberate.

**`R-CON-07` · The client builds and operates the hosting, and is given a specification rather than an answer** · `RULED`
`[SRC: SRC-002 §1.1 · SRC-002 §1.3 · FR-ADR-003 · FR-ADR-004]`
The build session writes the application. **The client builds and operates the hosting themselves.**
For each thing the client must build they are given what to build, what the application expects of it,
how to tell when it is right, and the two or three mistakes people commonly make — **and not the
answer.**
- **Why the business needs it** — this is the client's own stated purpose for the project: *"I am
  building it so that deploying and operating it teaches me real infrastructure skills."*
- **What it costs if absent** — the client is handed a working configuration, reads it, and the failure
  that would have taught them never happens. **Work done for them is a lesson taken from them.**
- **The obligation this creates in return** — every hosting dependency is announced **in advance, with the
  phase it is needed by**, never on the day it blocks.
- **What follows from it, stated every time it matters** — **this product has never been observed running
  on its hosting.** Every statement about how it will behave there is reasoned, not observed, and is
  labelled that way.

**`R-CON-08` · The deployed environment is not production, and carries no real customer data** · **`OPEN` / `DEFERRED`** · reserved: product
`[SRC: SRC-003 OPEN-TLS-01 · FR-ADR-069]`
Until the connection to the site is secured — which needs a domain name the client is still looking
for — **the deployed environment is never called production in any document, and no real customer data
goes into it.** Only obvious demonstration data.
- **Why the business needs it** — a name is a control. An environment carrying customer credentials over
  an unsecured connection must not be treated as finished, and calling it production is how it would
  be.
- **What it costs while it stays open** — **credentials cross the network unprotected in that
  environment.** That is the largest accepted weakness on the project, it has a named owner, and it is
  why nothing real goes in.
- **A second, independent reason to close it** — receipts sent from an unverified sender are far more
  likely to be treated as junk, and **a receipt in a junk folder is a receipt that did not arrive**,
  which lands straight in `OPEN-EMAILFAIL-01`.

**`R-CON-09` · Demonstration content is obviously demonstration content** · `RULED`
`[SRC: SRC-003 OPEN-SEED-01 · SRC-003 OPEN-ATTRIB-01 · FR-ADR-007 · FR-ADR-067]`
The sample data the business is shown contains **no invented film titles, no invented cinema or brand
name, no images from anywhere, and no realistic personal details**. Everything seeded is plainly
labelled as a placeholder. **The client supplies the real titles and posters**, as they said they
would.
- **Why the business needs it** — the client asked for exactly this. Content invented by a machine is
  content the client will see and may take as real, and a placeholder image from an unknown source is
  precisely the licence problem `OPEN-ATTRIB-01` is about.
- **What it costs if absent** — the business demonstrates a product full of made-up films, and takes on a
  licence question nobody asked about.
- **The consequence, accepted** — **the demonstration looks obviously like a demonstration.** If the
  client wants it to look real, they supply the content.

**`R-CON-10` · The product contains no artificial-intelligence feature** · `RULED` · reserved: legal
`[SRC: SRC-003 OPEN-MODEL-01]`
The product has no artificial-intelligence feature and sends no customer data to any model.
- **Why the business needs it** — the client ruled it: *"nothing like AI for now."*
- **What it costs if absent** — customer data leaving the business's control, and a set of obligations the
  client never agreed to.
- **A distinction worth stating** — this governs **the product**. That the product is *built* by reading
  this repository is a separate matter, and it is why the repository holds no credential and no real
  customer data.

**`R-CON-11` · What only the client may decide** · `RULED`
`[SRC: SRC-003 OPEN-NAME-01 · SRC-003 OPEN-LOCALE-01 · OPEN-PAY-01 · OPEN-CANCEL-01 · OPEN-PRICE-03 · OPEN-OPS-02]`
Money, anything irreversible or public, secrets, legal and data-protection questions, what the product
is and what "done" means, changes of scope, and **waiving any quality check** are the client's alone.
No model decides them at any confidence. **Adopting a stricter option is not a waiver and needs no
signature.**
- **Why the business needs it** — every one of these is a decision whose consequences the business, not
  the builder, carries.
- **What it costs if absent** — a money rule, a refund, or a waived safety check decided by whoever was
  at the keyboard that day, with no record.
- **Where irreversibility bites hardest, named** — the currency's smallest unit (`R-PRC-01`), the absence
  of a tax split (`R-PRC-05`), the permanence of every booking (`R-ADM-07`), and any refund
  (`R-PAY-05`). Each of these, once real bookings exist, cannot be undone.

---

# B7 — Explicitly out of scope

## B7.1 The rule that governs this whole section

**Excluded is not blocked.** `[SRC: SRC-001 §6.6 · FR-ADR-010 · FR-ADR-013 · FR-ADR-046]`

> *"We may ask for these later, so please do not design in a way that blocks them."*

Nothing in this section may be turned into an impossibility. **An exclusion that hardens into
something the business can never add is a defect, not a simplification.** Three places where this rule
is already doing visible work:

- the business keeps the ability to add a **second venue** without rebuilding what exists, even though
  there is one theatre today (`R-SEAT-07`, `R-BRW-03`);
- the business keeps the ability to add **cancellation** later without a rebuild, even though there is
  none now (`R-PAY-05`);
- the **cinema filter** is not shown to customers while one cinema exists, and appears on its own if a
  second ever does (`R-BRW-03`).

## B7.2 Out of scope — the client's own list, and everything `SRC-003` removed

| ID | Not being built | `[SRC:]` |
|---|---|---|
| `R-OUT-01` | A native mobile application. A website that works well on a phone is enough | `SRC-001 §6.1` · `FR-ADR-044` |
| `R-OUT-02` | Food and beverage ordering | `SRC-001 §6.2` |
| `R-OUT-03` | Loyalty points or membership tiers | `SRC-001 §6.3` |
| `R-OUT-04` | A multi-language interface | `SRC-001 §6.4` · `FR-ADR-044` |
| `R-OUT-05` | Integration with any existing point-of-sale system | `SRC-001 §6.5` |
| `R-OUT-06` | **Any external source of film information, and any automatic import.** The admin enters every film by hand | `SRC-003 OPEN-TMDB-01` · `FR-ADR-006` |
| `R-OUT-07` | **Any scheduled job at all** | `SRC-003 OPEN-PROC-01` · `FR-ADR-005` |
| `R-OUT-08` | A separate section for upcoming releases. Customers see only what is currently showing | `SRC-003 OPEN-TMDB-02` · `FR-ADR-021` |
| `R-OUT-09` | A scannable code on the ticket | `SRC-003 OPEN-TICKET-01` · `FR-ADR-015` |
| `R-OUT-10` | Any scanning device or validation step at the door, and any record of a ticket having been used | `SRC-003 OPEN-TICKET-02` · `FR-ADR-048` |
| `R-OUT-11` | Customer cancellation, and refunds of any kind | `SRC-003 OPEN-CANCEL-01` · `OPEN-CANCEL-02` · `FR-ADR-013` |
| `R-OUT-12` | **A real payment provider, ever, at any point in this project** | `SRC-003 OPEN-PAY-01` · `FR-ADR-041` |
| `R-OUT-13` | Accessible-seat marking, seats sold only in pairs, and any rule about leaving a gap | `SRC-003 OPEN-SEAT-02` · `OPEN-SEAT-03` · `OPEN-SEAT-04` · `FR-ADR-016` |
| `R-OUT-14` | Any export of reporting or booking data to a file | `SRC-003 OPEN-REPORT-02` · `FR-ADR-043` |
| `R-OUT-15` | A cinema-staff role and a door scanner | `SRC-003 OPEN-ROLE-01` · `SRC-001 §E E-1` · `FR-ADR-009` |
| `R-OUT-16` | Discount codes, concession or student pricing, booking fees, and a separate tax line | `SRC-003 OPEN-PRICE-02` · `OPEN-PRICE-03` · `FR-ADR-040` |
| `R-OUT-17` | Any artificial-intelligence feature | `SRC-003 OPEN-MODEL-01` |
| `R-OUT-18` | Withdrawing a showtime that has paid bookings — **not excluded, unruled.** See `R-ADM-08` | `SRC-003 OPEN-SHOWCANCEL-01` · `FR-ADR-023` |

## B7.3 Withdrawn and corrected clauses — stated, never silently absent

**Twelve clauses of `SRC-001 §1`–`§9` are withdrawn and one is corrected.** They have no requirement
row in B5 and this table is why. **A row derived from any of them would be a defect.**

| Clause | What it said | Status | Erratum |
|---|---|---|---|
| `SRC-001 §2.3` | show listings without staff typing them in every week | **withdrawn** — staff entering them is now the design | `SRC-001 §E E-6` |
| `SRC-001 §3.4` | movie listings update automatically, staff only approving | **withdrawn** | `SRC-001 §E E-7` |
| `SRC-001 §4.3` | a cinema-staff user who checks customers in by scanning a code | **withdrawn** — four roles, no staff role | `SRC-001 §E E-1` |
| `SRC-001 §5.1.2` | show upcoming releases separately | **withdrawn** | `SRC-001 §E E-5` |
| `SRC-001 §5.4.3` | a customer cancels a booking within an allowed window | **withdrawn** — no cancellation, no refunds | `SRC-001 §E E-2` |
| `SRC-001 §5.5.3` | staff validate tickets at the door | **withdrawn** — a manual human check instead | `SRC-001 §E E-3` |
| `SRC-001 §5.5.4` | the administrator approves imported films | **withdrawn** — nothing is imported; the admin authors and publishes (`R-ADM-02`) | `SRC-001 §E E-8` |
| `SRC-001 §5.6.1` | film information comes from a public database daily | **withdrawn** | `SRC-001 §E E-4` |
| `SRC-001 §5.6.2` | imported films need staff approval before customers see them | **withdrawn** | `SRC-001 §E E-4` |
| `SRC-001 §5.6.3` | importing must never create showtimes on its own | **withdrawn** — and its substance survives independently: nothing creates a showtime automatically, carried by `R-ADM-03` from `§9.4` | `SRC-001 §E E-4` |
| `SRC-001 §5.6.4` | if the external source is unavailable the site keeps working | **withdrawn** — there is no external source, so the failure cannot occur | `SRC-001 §E E-4` |
| `SRC-001 §9.5` | payment is handled by a third-party provider | **withdrawn** — simulated only, no provider ever (`R-PAY-03`) | `SRC-001 §E E-10` |
| `SRC-001 §5.3.3` | issue a booking reference **and a scannable ticket** | **corrected, not withdrawn** — a unique booking reference on an emailed receipt, checked by a person. Carried by `R-TKT-01` | `SRC-001 §E E-9` |

**Two clauses whose ownership moved rather than being withdrawn**, recorded so their rows are not read
as contradicting the source:

| Clause | As written | As it now stands |
|---|---|---|
| `SRC-001 §4.4` | the **manager** creates showtimes, sets pricing, and views occupancy | the manager **views occupancy only** (`R-RPT-03`). Creating showtimes and setting prices moved to the admin (`R-ADM-03`, `R-ADM-05`) under `SRC-003 OPEN-OPS-03` |
| `SRC-001 §5.5.1` | the **manager** creates showtimes with a price band | the **admin** does (`R-ADM-03`), for the same reason |

**The whole of `SRC-002 §10` is withdrawn** by `SRC-002 §E E-2`, and `SRC-002 §4.6`, `§8.1.1`,
`§8.5.1` and `§12.7` are corrected by errata `E-4`, `E-1`, `E-5` and `E-3`. Those are technical clauses
and none of them carries a row here.

---

# B8 — Coverage, both ways

> **The Definition of Done requires both counts to be zero, and both are printed here rather than
> claimed.** The first table proves nothing in the source was missed. The second proves nothing was
> added that no source asked for.

## B8.1 No gap — every live clause of `SRC-001 §1`–`§9` has a row

**63 clauses in `§1`–`§9`. 12 withdrawn (B7.3). 51 live clauses, and every one is covered.**

| Clause | Covered by |
|---|---|
| `§1.1` | `R-QLY-08`, `R-BRW-01` |
| `§1.2` | `R-QLY-01`, `R-QLY-03` |
| `§1.3` | `R-BRW-01`, `R-TKT-02` |
| `§2.1` | `R-BRW-01`, `R-PAY-01` |
| `§2.2` | `R-QLY-01` |
| `§2.3` | **withdrawn — `E-6`** |
| `§2.4` | `R-RPT-01` |
| `§2.5` | `R-BRW-01` |
| `§3.1` | `R-QLY-05`, `R-ACC-05` |
| `§3.2` | `R-QLY-01`, `R-QLY-02` |
| `§3.3` | `R-SEAT-06` |
| `§3.4` | **withdrawn — `E-7`** |
| `§3.5` | `R-RPT-02` |
| `§4.1` | `R-BRW-01`, `R-HOLD-06` |
| `§4.2` | `R-ACC-01`, `R-ACC-02`, `R-PAY-01` |
| `§4.3` | **withdrawn — `E-1`** |
| `§4.4` | `R-RPT-03` |
| `§4.5` | `R-ADM-01` … `R-ADM-05` |
| `§5.1.1` | `R-BRW-02` |
| `§5.1.2` | **withdrawn — `E-5`** |
| `§5.1.3` | `R-BRW-03` |
| `§5.1.4` | `R-BRW-04` |
| `§5.2.1` | `R-SEAT-01` |
| `§5.2.2` | `R-SEAT-02` |
| `§5.2.3` | `R-SEAT-03`, `R-PRC-02` |
| `§5.2.4` | `R-SEAT-04`, `R-PRC-03`, `R-PRC-04` |
| `§5.2.5` | `R-HOLD-01`, `R-HOLD-03` |
| `§5.2.6` | `R-HOLD-05`, `R-QLY-10` |
| `§5.3.1` | `R-PAY-01` |
| `§5.3.2` | `R-PAY-02` |
| `§5.3.3` | `R-TKT-01` *(corrected by `E-9`)* |
| `§5.3.4` | `R-TKT-02` |
| `§5.4.1` | `R-ACC-01`, `R-ACC-04` |
| `§5.4.2` | `R-ACC-02`, `R-TKT-03` |
| `§5.4.3` | **withdrawn — `E-2`** |
| `§5.5.1` | `R-ADM-03`, `R-PRC-02` |
| `§5.5.2` | `R-RPT-02`, `R-RPT-04` |
| `§5.5.3` | **withdrawn — `E-3`** |
| `§5.5.4` | **withdrawn — `E-8`** |
| `§5.6.1` | **withdrawn — `E-4`** |
| `§5.6.2` | **withdrawn — `E-4`** |
| `§5.6.3` | **withdrawn — `E-4`** *(substance carried by `R-ADM-03` from `§9.4`)* |
| `§5.6.4` | **withdrawn — `E-4`** |
| `§6.1` | `R-OUT-01`, `R-QLY-09` |
| `§6.2` | `R-OUT-02` |
| `§6.3` | `R-OUT-03` |
| `§6.4` | `R-OUT-04` |
| `§6.5` | `R-OUT-05` |
| `§6.6` | B7.1 |
| `§7.1` | `R-QLY-01` |
| `§7.2` | `R-QLY-03` |
| `§7.3` | `R-QLY-04`, `R-SEAT-06` |
| `§7.4` | `R-QLY-06`, `R-PAY-04`, `R-ADM-05` |
| `§7.5` | `R-QLY-07` |
| `§7.6` | `R-QLY-08`, `R-ADM-06`, `R-ADM-07`, `R-PRC-04` |
| `§8.1` | `R-CON-01` |
| `§8.2` | `R-CON-02`, `R-QLY-10` |
| `§8.3` | `R-CON-03` |
| `§9.1` | `R-QLY-09` |
| `§9.2` | `R-ACC-03` |
| `§9.3` | `R-ADM-04` |
| `§9.4` | `R-ADM-03` |
| `§9.5` | **withdrawn — `E-10`** |

**Gap count: 0.** No live clause of `SRC-001 §1`–`§9` is without a row.

## B8.2 No creep — every row traces to a source

| Group | Rows | Every row cites |
|---|---|---|
| `R-BRW` | 6 | `SRC-001 §1`, `§4`, `§5.1` · `SRC-003` · an `APPROVED` record |
| `R-SEAT` | 7 | `SRC-001 §3`, `§5.2`, `§7.3` · `SRC-003` · an `APPROVED` record |
| `R-HOLD` | 7 | `SRC-001 §4.1`, `§5.2` · `SRC-003` · an `APPROVED` record |
| `R-PAY` | 5 | `SRC-001 §2.1`, `§5.3`, `§7.4` · `SRC-003` · an `APPROVED` record |
| `R-PRC` | 5 | `SRC-001 §5.2`, `§5.5.1`, `§7.6` · `SRC-003` · an `APPROVED` record |
| `R-TKT` | 6 | `SRC-001 §5.3`, `§5.4.2` · `SRC-003` · an `APPROVED` record |
| `R-ACC` | 5 | `SRC-001 §3.1`, `§5.4`, `§9.2` · `SRC-003` · an `APPROVED` record |
| `R-ADM` | 8 | `SRC-001 §5.5.1`, `§7.4`, `§7.6`, `§9.3`, `§9.4` · `SRC-003` · an `APPROVED` record |
| `R-RPT` | 5 | `SRC-001 §2.4`, `§3.5`, `§4.4`, `§5.5.2`, `§7.6` · `SRC-003` · an `APPROVED` record |
| `R-QLY` | 10 | `SRC-001 §1`, `§2.2`, `§3`, `§5.2.6`, `§6.1`, `§7`, `§8.2`, `§9.1` · `SRC-003` · an `APPROVED` record |
| `R-CON` | 11 | `SRC-001 §8` · `SRC-002 §1`, `§5`, `§12` · `SRC-003` · an `APPROVED` record |
| `R-OUT` | 18 | `SRC-001 §6` · `SRC-003` · an `APPROVED` record |
| **Total** | **93** | |

**Creep count: 0.** Every row carries at least one citation to `SRC-001`, `SRC-002` (within the three
business sections named in B1.4), `SRC-003`, or an `APPROVED` record. **No row exists because it
seemed sensible.**

## B8.3 Where the ground is soft — read these before relying on them

| Row(s) | Status | What is not settled |
|---|---|---|
| B4.1, `R-ADM-05`, `R-RPT-03` | `PROVISIONAL` | **Four roles, not one.** Two of the client's own answers had to be reconciled. `SRC-003 C-1` names the rejected three-role reading |
| `R-SEAT-07`, `R-BRW-03` | `PROVISIONAL` | **One cinema with six halls**, against `SRC-001`'s plural. `SRC-003 C-2` records the reconciliation |
| `R-HOLD-07` | `PROVISIONAL` | **Sales close fifteen minutes *after* the advertised start.** The alternative reading is fifteen minutes *before*, and the two are half an hour apart |
| `R-SEAT-07` | `ASSUMED` | **Hall sizes** — the client said "pick random" |
| `R-QLY-02`, `R-QLY-03` | `ASSUMED` | **Peak concurrency of fifty bookers** — the client said "you pick". It measures performance and proves nothing about correctness |
| `R-SEAT-03` | `ASSUMED` | **Seat category names** — the client said "you pick" |
| `R-TKT-06`, `R-ADM-08`, `R-CON-08` | `OPEN` | Three of the four questions in B5.11 sit directly on a row. **Escalate, never invent** |
| `R-CON-09` | `RULED`, with an `OPEN` constraint on top | The row itself is ruled. The fourth open question, `OPEN-ATTRIB-01`, is the standing constraint it carries: **no licensed image or synopsis enters this product until the client says where the material comes from** |

**A `PROVISIONAL` reading and an `ASSUMED` choice are not requirements.** Neither ever becomes a
`MUST`. This project has already produced the failure that rule exists to prevent: an assumption of
seven minutes in a question became a specification in the next document, and when it was finally put
to the client it came back as three (`R-HOLD-02`).

---

*End of document. Every row above cites its source; where a citation is missing, the row is the
defect and not the source.*
