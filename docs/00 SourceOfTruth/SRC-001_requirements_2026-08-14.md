# SRC-001 — FrontRow requirements, as given by the client

```
Source type ....... Client requirement brief (written)
Received .......... 2026-08-14
Author ............ the client (cinema operator)
Original file ..... CLIENT_ASK.md
Status ............ FROZEN — never edited
Citation form ..... SRC-001 §n
```

> **FROZEN INPUT. DO NOT EDIT.** Every requirement in `02 BRD`, `03 PRD`, `05 Bible` and
> `06 DataModel` cites a clause of this file. If this file changes, everything derived from it is
> invalidated and must be re-derived — never silently reused (`CONSTITUTION.md` Art II.4).
>
> The **only** permitted modification is a clearly-marked `ERRATUM` block appended at the foot,
> which governs over the text it corrects. No errata exist yet.
>
> Clause anchors `§n` were added when the text was filed. **No wording was changed.**
>
> This document is the client's *product* requirement. The client's *build mandate* — stack,
> constraints, work zones, and the DevOps-learning purpose — is a separate frozen source,
> `SRC-002`. Where the two conflict, `CONSTITUTION.md` Art II.1 governs.

---

## §1 — Business context

**§1.1** We operate cinemas and currently sell tickets only at the counter. Customers queue, seats
are marked off manually, and we have no record of who bought what.

**§1.2** On weekends we lose sales because people leave rather than wait, and we regularly have
disputes where two customers are sold the same seat.

**§1.3** We want a website where customers can browse what is playing, choose their own seats, pay,
and arrive with a ticket on their phone.

## §2 — Business objectives

**§2.1** Allow customers to book seats online without staff involvement.

**§2.2** Eliminate double-booking of seats completely. This is non-negotiable.

**§2.3** Show accurate, current movie listings without staff typing them in every week.

**§2.4** Give management visibility into occupancy, revenue, and popular showtimes.

**§2.5** Reduce queue length at the counter.

## §3 — Success criteria

**§3.1** A customer can complete a booking end to end in under two minutes.

**§3.2** Zero double-booked seats under concurrent load.

**§3.3** Seat availability shown to the customer is accurate within a few seconds.

**§3.4** Movie listings update automatically, with staff only approving what appears.

**§3.5** Management can see occupancy per show without asking anyone for a report.

## §4 — Users

**§4.1 Guest visitor** — Browse movies and showtimes without an account.

**§4.2 Registered customer** — Book seats, pay, view and cancel their bookings, see ticket history.

**§4.3 Cinema staff** — Check in customers by scanning or entering a ticket code.

**§4.4 Cinema manager** — Create showtimes, set pricing, view occupancy for their cinema.

**§4.5 System administrator** — Manage cinemas, screens, seat layouts, users, and approve new movie
listings.

## §5 — What we want the system to do

### §5.1 Browsing

**§5.1.1** Show movies currently playing, with poster, synopsis, runtime, certification, language,
and genre.

**§5.1.2** Show upcoming releases separately.

**§5.1.3** Filter by cinema, date, language, and format.

**§5.1.4** Show all showtimes for a chosen movie and date.

### §5.2 Seat selection

**§5.2.1** Show a visual seat map matching the real layout of the screen.

**§5.2.2** Clearly distinguish available, held, and sold seats.

**§5.2.3** Distinguish seat categories, since we price them differently.

**§5.2.4** Show the total price updating as seats are selected.

**§5.2.5** Hold selected seats temporarily while the customer completes payment, then release them
automatically if the customer does not finish.

**§5.2.6** If another customer takes a seat first, tell our customer immediately and clearly.

### §5.3 Booking and payment

**§5.3.1** Collect payment before the booking is confirmed.

**§5.3.2** Never charge a customer twice for the same booking attempt, including if they refresh or
click twice.

**§5.3.3** Issue a booking reference and a scannable ticket.

**§5.3.4** Send a confirmation by email.

### §5.4 Customer account

**§5.4.1** Register and log in with email and password.

**§5.4.2** View upcoming and past bookings.

**§5.4.3** Cancel a booking within an allowed window.

### §5.5 Staff and management

**§5.5.1** Manager creates showtimes by choosing a movie, screen, date, time, and price band.

**§5.5.2** Manager sees occupancy and revenue per show, per day, and per movie.

**§5.5.3** Staff validates tickets at the door.

**§5.5.4** Administrator approves which automatically imported movies become visible.

### §5.6 Movie data

**§5.6.1** Movie information should come from a public movie database automatically, on a daily
schedule, so staff do not type it in.

**§5.6.2** Imported movies must not appear to customers until a staff member approves them.

**§5.6.3** Importing must never create showtimes on its own. Showtimes are always a human decision.

**§5.6.4** If the external source is unavailable, the site must keep working normally.

## §6 — What we are not asking for right now

**§6.1** Native mobile applications. A website that works well on a phone is enough.

**§6.2** Food and beverage ordering.

**§6.3** Loyalty points or membership tiers.

**§6.4** Multi-language interface.

**§6.5** Integration with any existing point of sale system.

**§6.6** We may ask for these later, so please do not design in a way that blocks them.

## §7 — Quality expectations

**§7.1 Correctness** — A seat sold twice is a failure of the whole system, regardless of load.

**§7.2 Availability** — The site should stay usable during our busiest period, which is Friday and
Saturday evenings.

**§7.3 Speed** — Pages should feel immediate. Seat maps in particular must not lag.

**§7.4 Security** — Customer passwords and payment details must be handled properly. Staff and
management functions must not be reachable by customers.

**§7.5 Recoverability** — If a server restarts mid-booking, no customer should lose money or end up
with a seat they did not get.

**§7.6 Auditability** — We must be able to answer "who booked this seat and when" for any seat.

## §8 — Constraints

**§8.1** Budget for infrastructure is effectively zero. The system must run on the smallest
practical hosting footprint.

**§8.2** We have no dedicated operations team, so the system must be observable and recoverable by
one person.

**§8.3** We do not want vendor lock-in to any expensive managed service.

## §9 — Assumptions we are making

> "Please confirm or correct these."

**§9.1** Customers have a smartphone and an email address.

**§9.2** One booking belongs to one customer, one showtime, and one or more seats.

**§9.3** Seat layouts change rarely once a screen is configured.

**§9.4** Showtimes are scheduled ahead of time by staff, not generated automatically.

**§9.5** Payment is handled by a third party provider, not by us directly.

## §10 — Open questions for the client

> "Answer these before the BRD is written. Where an answer is unknown, say so and the BRD will
> record it as an assumption."
>
> **Filing note (build session, not client text):** each question below is mirrored as a row in
> `CONSTITUTION.md` Article X with the id shown in brackets. Until a row is adjudicated its status
> is `OPEN`, and an `OPEN` row may never be filled in with a plausible guess (Art VII).

### Scope and scale

**§10.1** How many cinemas, and how many screens per cinema, at launch? `[OPEN-SCALE-01]`

**§10.2** What is the largest screen, in number of seats? `[OPEN-SCALE-02]`

**§10.3** What is the realistic peak, in customers booking at the same minute? `[OPEN-SCALE-03]`

**§10.4** Which country and city do we launch in, and which currency? `[OPEN-LOCALE-01]`

### Seat and screen setup

**§10.5** Do screens have different seat categories, for example recliner, premium, and standard?
`[OPEN-SEAT-01]`

**§10.6** Are there wheelchair accessible seats that must be marked and reserved as such?
`[OPEN-SEAT-02]`

**§10.7** Are there seats that must be sold as a pair, for example couple seats? `[OPEN-SEAT-03]`

**§10.8** Should we prevent a customer from leaving a single empty seat between bookings?
`[OPEN-SEAT-04]`

### Booking rules

**§10.9** How long should selected seats be held while the customer pays? We assumed 7 minutes.
`[OPEN-HOLD-01]`

**§10.10** What is the maximum number of seats in one booking? `[OPEN-BOOK-01]`

**§10.11** Can a guest book without creating an account, or is login required? `[OPEN-BOOK-02]`

**§10.12** How long before showtime do we stop selling tickets? `[OPEN-BOOK-03]`

**§10.13** Can a customer cancel, and if so up to when, and is the refund full or partial?
`[OPEN-CANCEL-01]`

**§10.14** What happens if a show is cancelled by the cinema? Automatic refunds? `[OPEN-CANCEL-02]`

### Pricing

**§10.15** Does price vary by seat category, by time of day, by day of week, or by movie?
`[OPEN-PRICE-01]`

**§10.16** Do we need discount codes, student pricing, or convenience fees? `[OPEN-PRICE-02]`

**§10.17** Is tax shown separately on the ticket? `[OPEN-PRICE-03]`

### Payment

**§10.18** Which payment provider do you want, and do you already have an account? `[OPEN-PAY-01]`

**§10.19** For the first version, is a simulated payment step acceptable so we can build and test
the rest of the flow? `[OPEN-PAY-02]`

### Movie data

**§10.20** Which region should movie listings be pulled for? `[OPEN-TMDB-01]`

**§10.21** Should upcoming releases be visible to customers before tickets go on sale?
`[OPEN-TMDB-02]`

**§10.22** Who approves an imported movie, the manager or the administrator? `[OPEN-TMDB-03]`

**§10.23** Do you need to override imported details, for example a different poster or a local
title? `[OPEN-TMDB-04]`

### Tickets and entry

**§10.24** Should the ticket be a QR code, a numeric reference, or both? `[OPEN-TICKET-01]`

**§10.25** Does staff need an offline way to validate tickets if the internet drops at the door?
`[OPEN-TICKET-02]`

### Reporting

**§10.26** What does management need to see daily, and what weekly? `[OPEN-REPORT-01]`

**§10.27** Do you need an export, for example to a spreadsheet? `[OPEN-REPORT-02]`

### Operations

**§10.28** Who receives alerts if the system goes down? `[OPEN-OPS-01]`

**§10.29** How long must booking records be kept? `[OPEN-OPS-02]`

**§10.30** Do you need staff activity logs, for example who changed a price? `[OPEN-OPS-03]`

---

## §E — Errata

*(none filed)*

An erratum is appended here when a later client ruling corrects a clause above. The clause text is
never struck where it stands; the erratum governs over it. Each erratum names the clause it
corrects, the ADR that filed it, and the date.
