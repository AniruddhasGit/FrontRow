# Lens 4 — User-visible behaviour · raw sweep return

```
Run ........ 2026-08-14, GOAL_02
Method ..... independent sub-agent, read SRC-001 + SRC-002 + SRC-003 in full including both §E
Status ..... RAW. Not deduped, not merged, not adjudicated.
Format ..... <decision statement> | SOURCE: <clause id or NONE> | <RULED|PROVISIONAL|OPEN|ASSUMED>
```

Movie browsing list shows only currently-showing movies, with no upcoming-releases section | SOURCE: SRC-001 E-5 | RULED
Movie card/detail shows poster, synopsis, runtime, certification, language and genre | SOURCE: SRC-001 §5.1.1 | RULED
Default listing order is newest movie first, re-sorted by the customer's chosen filter | SOURCE: SRC-003 OPEN-TMDB-01 | RULED
Customers can filter listings by cinema, date, language and format | SOURCE: SRC-001 §5.1.3 | RULED
Whether the cinema filter is rendered at all when only one cinema exists at launch | SOURCE: SRC-003 C-2 | OPEN
Which sort options beyond "newest" are offered in the sort control | SOURCE: NONE | OPEN
All showtimes for a chosen movie and date are listed on one screen | SOURCE: SRC-001 §5.1.4 | RULED
Four visible roles — guest, customer, manager, admin — each with a distinct navigation surface | SOURCE: SRC-003 C-1 | PROVISIONAL
A guest may browse movies, showtimes and the seat map but cannot hold or book | SOURCE: SRC-003 OPEN-ROLE-01 | RULED
Booking requires a registered account, so there is no anonymous checkout path | SOURCE: SRC-003 OPEN-BOOK-02 | RULED
Where the guest is stopped — at seat click, at "continue to checkout", or at pay | SOURCE: NONE | OPEN
Whether a guest's seat selection survives the login/registration round trip | SOURCE: NONE | OPEN
No door-scanner, ticket-validation or staff check-in screen exists anywhere in the UI | SOURCE: SRC-001 E-3 | RULED
Seat map renders the real physical layout of the screen | SOURCE: SRC-001 §5.2.1 | RULED
Seat map visually distinguishes available, held and sold seats | SOURCE: SRC-001 §5.2.2 | RULED
Exact visual treatment of a seat held by another customer (colour, label, cursor, disabled state) | SOURCE: NONE | OPEN
Whether the customer's own held seats are visually distinct from other people's holds | SOURCE: NONE | OPEN
Seat map distinguishes seat categories visually because they are priced differently | SOURCE: SRC-001 §5.2.3 | RULED
Three seat categories named Standard, Premium and Recliner appear in the legend | SOURCE: SRC-003 OPEN-SEAT-01 | ASSUMED
Seat states must carry a non-colour cue as well as colour, for contrast and colour-blindness | SOURCE: NONE | OPEN
Running total price updates live as seats are selected and deselected | SOURCE: SRC-001 §5.2.4 | RULED
Seat map refreshes by polling every 3 seconds, not by websocket | SOURCE: SRC-002 §8.6.1 | RULED
Code is structured so websockets can replace polling later as a second exercise | SOURCE: SRC-002 §8.6.2 | RULED
Whether a manual "refresh" affordance is offered alongside the 3-second poll | SOURCE: NONE | OPEN
Whether polling pauses when the tab is backgrounded and what the user sees on resume | SOURCE: NONE | OPEN
Seat map must be usable for a 220-seat hall on a 375-pixel-wide phone | SOURCE: SRC-003 OPEN-SCALE-02 | ASSUMED
Any available seat may be selected — no gap rule and no paired-seat rule shown | SOURCE: SRC-003 OPEN-SEAT-03, OPEN-SEAT-04 | RULED
No accessible-seat marking appears on the seat map in v1 | SOURCE: SRC-003 OPEN-SEAT-02 | RULED
A maximum of 10 seats per booking, with the limit also enforced server-side | SOURCE: SRC-003 OPEN-BOOK-01 | RULED
What the interface does when an 11th seat is clicked (block, toast, swap) and its wording | SOURCE: NONE | OPEN
The seat hold lasts 3 minutes, taken from configuration not a constant | SOURCE: SRC-002 E-1 | RULED
Whether a countdown timer is displayed to the customer at all, and in what format | SOURCE: NONE | OPEN
Whether a warning appears at a threshold before hold expiry, and at what threshold | SOURCE: NONE | OPEN
What the customer sees and where they land when the hold expires mid-checkout | SOURCE: NONE | OPEN
Whether expiry is detected client-side by the timer or only by a server rejection | SOURCE: NONE | OPEN
Whether a hold can be extended or renewed by the customer | SOURCE: NONE | OPEN
When another customer takes a selected seat first, our customer is told immediately and clearly | SOURCE: SRC-001 §5.2.6 | RULED
The exact wording and severity class of the seat-taken, hold-expired and payment-failed messages | SOURCE: NONE | OPEN
Error and interface copy uses literal language with no analogies or metaphors | SOURCE: SRC-002 §2.2 | ASSUMED
Rate-limited users see a message derived from the 429 and its Retry-After header | SOURCE: SRC-002 §8.4.2 | RULED
When Redis is unreachable the user sees an error, never a silently degraded seat map | SOURCE: SRC-002 §7.9 | RULED
Whether any user-facing error surfaces a request id for support correlation | SOURCE: NONE | OPEN
The checkout screen states in plain words that no real payment is taken | SOURCE: SRC-003 OPEN-PAY-02 | RULED
Payment is a fake button driving pending → authorized → captured / failed states | SOURCE: SRC-003 OPEN-PAY-01 | RULED
Refreshing or double-clicking pay never produces a second booking or a second charge | SOURCE: SRC-001 §5.3.2 | RULED
No discount-code field, no booking fee and no concession pricing appear at checkout | SOURCE: SRC-003 OPEN-PRICE-02 | RULED
No separate tax line on the receipt; the price shown is the price paid | SOURCE: SRC-003 OPEN-PRICE-03 | RULED
Prices display in INR with Asia/Kolkata times, formatted from integer paise at render time only | SOURCE: SRC-003 OPEN-LOCALE-01 | RULED
Date and time presentation format (12-hour vs 24-hour, date pattern) | SOURCE: NONE | OPEN
Per-seat price is base price plus a fixed category uplift, with the rounding rule visible in totals | SOURCE: SRC-003 OPEN-PRICE-01 | RULED
The ticket is a human-readable unique booking reference, never a QR code | SOURCE: SRC-001 E-9 | RULED
The reference excludes confusable characters — no 0/O and no 1/I/l | SOURCE: SRC-003 OPEN-TICKET-01 | RULED
Exact reference length, alphabet, grouping and prefix | SOURCE: NONE | OPEN
The booking reference is shown on screen as well as emailed | SOURCE: SRC-003 OPEN-EMAIL-01 | RULED
The emailed receipt is the only proof of purchase and the only way into the hall | SOURCE: SRC-003 OPEN-TICKET-01, OPEN-BOOK-02 | RULED
The receipt carries the reference, seat numbers, hall and showtime | SOURCE: SRC-001 E-9 | RULED
What the customer is shown when SES fails after payment is captured | SOURCE: SRC-003 OPEN-EMAILFAIL-01 | OPEN
Whether the customer can resend the receipt email from their booking page | SOURCE: NONE | OPEN
Receipt email layout, sender name and branding | SOURCE: NONE | OPEN
Customers register and log in with email and password | SOURCE: SRC-001 §5.4.1 | RULED
Password minimum length, complexity rules and the wording of the validation messages | SOURCE: NONE | OPEN
Whether email verification is required before a first booking | SOURCE: NONE | OPEN
Whether a password-reset flow exists in v1 | SOURCE: NONE | OPEN
What the user sees when the JWT session expires mid-session | SOURCE: NONE | OPEN
Customers see their upcoming and past bookings with the reference on each | SOURCE: SRC-001 §5.4.2 | RULED
No cancel button exists anywhere in the customer interface | SOURCE: SRC-001 E-2 | RULED
Admin creates each movie by hand: title, poster, metadata and a display window with start and end | SOURCE: SRC-003 OPEN-ROLE-01 | RULED
Posters are uploaded by the admin to S3 and served from our own URLs, never hotlinked | SOURCE: SRC-002 E-2 | RULED
Poster file size, format, aspect ratio and the validation messages on rejection | SOURCE: NONE | OPEN
Whether the movie form previews the poster and the customer-facing card before publishing | SOURCE: NONE | OPEN
A movie is visible to customers only inside its display window and only once published | SOURCE: SRC-003 OPEN-TMDB-03 | RULED
What a customer sees for a movie whose display window ended but whose showtimes still have bookings | SOURCE: NONE | OPEN
Admin creates showtimes by choosing movie, screen, date, time and price band | SOURCE: SRC-001 §5.5.1 | RULED
Admin sets the per-category uplift percentages once, applied to every hall and show | SOURCE: SRC-003 OPEN-PRICE-01 | RULED
What the admin "cancel a show" control does to existing bookings and whether it ships in v1 | SOURCE: SRC-003 OPEN-SHOWCANCEL-01 | OPEN
Manager dashboard is strictly read-only with no write control rendered anywhere | SOURCE: SRC-003 OPEN-OPS-03 | RULED
Manager dashboard is scoped to assigned screens and shows day, week and month figures | SOURCE: SRC-003 OPEN-SCOPE-01 | RULED
Dashboard metrics are earnings, occupancy and per-movie performance | SOURCE: SRC-003 OPEN-REPORT-01 | RULED
Whether manager and admin see the same dashboard screen with different scope, or two screens | SOURCE: NONE | OPEN
Whether the dashboard exposes customer-identifying booking rows to a manager | SOURCE: NONE | OPEN
No CSV or spreadsheet export button anywhere; on-screen only | SOURCE: SRC-003 OPEN-REPORT-02 | RULED
The admin audit-log screen is a Phase 8 read surface | SOURCE: SRC-003 OPEN-OPS-03 | RULED
Sales close 15 minutes after the advertised start, and existing holders may finish checkout | SOURCE: SRC-003 OPEN-BOOK-03 | PROVISIONAL
How a past-cut-off showtime is presented — hidden, greyed, or labelled | SOURCE: NONE | OPEN
How a sold-out showtime and a fully sold seat map are presented | SOURCE: NONE | OPEN
Empty states for no movies showing, no showtimes on the chosen date, no bookings yet, and an empty dashboard period | SOURCE: NONE | OPEN
The site is a responsive mobile web app, with no native application | SOURCE: SRC-001 §6.1 | RULED
Single-language English interface, no locale switcher | SOURCE: SRC-001 §6.4 | RULED
No food-and-beverage or loyalty surfaces anywhere in the UI | SOURCE: SRC-001 §6.2, §6.3 | RULED
CSS approach for React+Vite+TypeScript — hand-written CSS or CSS modules, since any component library needs the client's prior permission | SOURCE: SRC-002 §13.1 | ASSUMED
Target accessibility standard and conformance level for contrast, focus and keyboard operation | SOURCE: NONE | OPEN
Whether contrast ratios are computed and recorded rather than asserted | SOURCE: NONE | ASSUMED
Whether the seat map is keyboard and screen-reader operable at all | SOURCE: NONE | OPEN
Footer attribution if supplied posters or titles originate from a licensed source | SOURCE: SRC-003 OPEN-ATTRIB-01 | OPEN
Whether the deployed site is reachable over HTTPS, which governs any "secure" claim shown to users | SOURCE: SRC-003 OPEN-TLS-01 | OPEN
Demo movie rows appear as obvious placeholders such as DEMO MOVIE 01, never as plausible real titles | SOURCE: SRC-003 OPEN-SEED-01 | RULED
