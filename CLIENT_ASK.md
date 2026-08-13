# Client Requirement Brief — Online Movie Ticket Booking Platform

**Prepared by:** The Client
**Purpose:** Source document for writing a Business Requirements Document (BRD)
**Status:** Draft. Open questions in Section 10 must be answered before the BRD is finalised.

---

## 1. Business context

We operate cinemas and currently sell tickets only at the counter. Customers queue,
seats are marked off manually, and we have no record of who bought what. On weekends we
lose sales because people leave rather than wait, and we regularly have disputes where
two customers are sold the same seat.

We want a website where customers can browse what is playing, choose their own seats,
pay, and arrive with a ticket on their phone.

---

## 2. Business objectives

1. Allow customers to book seats online without staff involvement.
2. Eliminate double-booking of seats completely. This is non-negotiable.
3. Show accurate, current movie listings without staff typing them in every week.
4. Give management visibility into occupancy, revenue, and popular showtimes.
5. Reduce queue length at the counter.

---

## 3. Success criteria

- A customer can complete a booking end to end in under two minutes.
- Zero double-booked seats under concurrent load.
- Seat availability shown to the customer is accurate within a few seconds.
- Movie listings update automatically, with staff only approving what appears.
- Management can see occupancy per show without asking anyone for a report.

---

## 4. Users

| User type | What they need to do |
|---|---|
| Guest visitor | Browse movies and showtimes without an account |
| Registered customer | Book seats, pay, view and cancel their bookings, see ticket history |
| Cinema staff | Check in customers by scanning or entering a ticket code |
| Cinema manager | Create showtimes, set pricing, view occupancy for their cinema |
| System administrator | Manage cinemas, screens, seat layouts, users, and approve new movie listings |

---

## 5. What we want the system to do

### 5.1 Browsing
- Show movies currently playing, with poster, synopsis, runtime, certification, language, and genre.
- Show upcoming releases separately.
- Filter by cinema, date, language, and format.
- Show all showtimes for a chosen movie and date.

### 5.2 Seat selection
- Show a visual seat map matching the real layout of the screen.
- Clearly distinguish available, held, and sold seats.
- Distinguish seat categories, since we price them differently.
- Show the total price updating as seats are selected.
- Hold selected seats temporarily while the customer completes payment, then release them
  automatically if the customer does not finish.
- If another customer takes a seat first, tell our customer immediately and clearly.

### 5.3 Booking and payment
- Collect payment before the booking is confirmed.
- Never charge a customer twice for the same booking attempt, including if they refresh
  or click twice.
- Issue a booking reference and a scannable ticket.
- Send a confirmation by email.

### 5.4 Customer account
- Register and log in with email and password.
- View upcoming and past bookings.
- Cancel a booking within an allowed window.

### 5.5 Staff and management
- Manager creates showtimes by choosing a movie, screen, date, time, and price band.
- Manager sees occupancy and revenue per show, per day, and per movie.
- Staff validates tickets at the door.
- Administrator approves which automatically imported movies become visible.

### 5.6 Movie data
- Movie information should come from a public movie database automatically, on a daily
  schedule, so staff do not type it in.
- Imported movies must not appear to customers until a staff member approves them.
- Importing must never create showtimes on its own. Showtimes are always a human decision.
- If the external source is unavailable, the site must keep working normally.

---

## 6. What we are not asking for right now

- Native mobile applications. A website that works well on a phone is enough.
- Food and beverage ordering.
- Loyalty points or membership tiers.
- Multi-language interface.
- Integration with any existing point of sale system.

We may ask for these later, so please do not design in a way that blocks them.

---

## 7. Quality expectations

- **Correctness:** A seat sold twice is a failure of the whole system, regardless of load.
- **Availability:** The site should stay usable during our busiest period, which is Friday
  and Saturday evenings.
- **Speed:** Pages should feel immediate. Seat maps in particular must not lag.
- **Security:** Customer passwords and payment details must be handled properly. Staff and
  management functions must not be reachable by customers.
- **Recoverability:** If a server restarts mid-booking, no customer should lose money or
  end up with a seat they did not get.
- **Auditability:** We must be able to answer "who booked this seat and when" for any seat.

---

## 8. Constraints

- Budget for infrastructure is effectively zero. The system must run on the smallest
  practical hosting footprint.
- We have no dedicated operations team, so the system must be observable and recoverable
  by one person.
- We do not want vendor lock-in to any expensive managed service.

---

## 9. Assumptions we are making

1. Customers have a smartphone and an email address.
2. One booking belongs to one customer, one showtime, and one or more seats.
3. Seat layouts change rarely once a screen is configured.
4. Showtimes are scheduled ahead of time by staff, not generated automatically.
5. Payment is handled by a third party provider, not by us directly.

Please confirm or correct these.

---

## 10. Open questions for the client

Answer these before the BRD is written. Where an answer is unknown, say so and the BRD
will record it as an assumption.

### Scope and scale
1. How many cinemas, and how many screens per cinema, at launch?
2. What is the largest screen, in number of seats?
3. What is the realistic peak, in customers booking at the same minute?
4. Which country and city do we launch in, and which currency?

### Seat and screen setup
5. Do screens have different seat categories, for example recliner, premium, and standard?
6. Are there wheelchair accessible seats that must be marked and reserved as such?
7. Are there seats that must be sold as a pair, for example couple seats?
8. Should we prevent a customer from leaving a single empty seat between bookings?

### Booking rules
9. How long should selected seats be held while the customer pays? We assumed 7 minutes.
10. What is the maximum number of seats in one booking?
11. Can a guest book without creating an account, or is login required?
12. How long before showtime do we stop selling tickets?
13. Can a customer cancel, and if so up to when, and is the refund full or partial?
14. What happens if a show is cancelled by the cinema? Automatic refunds?

### Pricing
15. Does price vary by seat category, by time of day, by day of week, or by movie?
16. Do we need discount codes, student pricing, or convenience fees?
17. Is tax shown separately on the ticket?

### Payment
18. Which payment provider do you want, and do you already have an account?
19. For the first version, is a simulated payment step acceptable so we can build and
    test the rest of the flow?

### Movie data
20. Which region should movie listings be pulled for?
21. Should upcoming releases be visible to customers before tickets go on sale?
22. Who approves an imported movie, the manager or the administrator?
23. Do you need to override imported details, for example a different poster or a local title?

### Tickets and entry
24. Should the ticket be a QR code, a numeric reference, or both?
25. Does staff need an offline way to validate tickets if the internet drops at the door?

### Reporting
26. What does management need to see daily, and what weekly?
27. Do you need an export, for example to a spreadsheet?

### Operations
28. Who receives alerts if the system goes down?
29. How long must booking records be kept?
30. Do you need staff activity logs, for example who changed a price?
