# CR-012: The demo has a crowd: hundreds of ratings and reviews per film, and shows that sell

| | |
|---|---|
| **Raised** | 2026-11-23, by the owner, in a working session |
| **Status** | **Built locally, not deployed.** The owner runs the two scripts against Neon and deploys. Demo copy only: the seat fill runs only when `DEMO_SHOWTIMES_AHEAD_DAYS` > 0 (AWS leaves it 0). The rating visibility rule applies everywhere, and changes nothing for real customers. |
| **Amends** | Nothing in the frozen sources. SRC-003's "nothing runs on a schedule" is kept: no timer, job or poll of any kind. The rating write gate (a paid booking whose show has started) is unchanged for every real customer. |

## What the owner asked for (their words)

- "add rating stars of positive negative like real world simulation and reviews for all the movies in 100's and comments and keep them circulating, make sure they are generic and not movie specific or the fake comments would give away"
- "there should always be seats which are already booked ... closer the movie show date is the lesser seats will be available on average 80-90% seats should be booked so that we can run proper sales on the manager/admin side later as well for analytics"

## What was built

| Piece | Behaviour |
|---|---|
| **The crowd** (`scripts/demo_reviews.py`) | 700 demo customer accounts, `customer-51@` to `customer-750@` at the seed's `.invalid` domain, with the seed's own password hash copied from `customer-01` and a made-up handle as the display name (or none). The seed's `customer-01..50` logins are never used. |
| **Ratings and reviews** (`scripts/demo_reviews.py`) | <ul><li>**Who:** every published, released film, 120 to 450 ratings visible on the run day, plus 25–45% more dated over the next 120 days.</li><li>**Scores:** each film has its own quality (an average of 5.5–8.8), with a realistic spread that includes 1–4s.</li><li>**Text:** 25–40% carry text whose tone follows the score, built from 125 positive, 75 mixed and 76 negative generic sentences, one to three per review.</li><li>**Helpful votes:** from other crowd accounts.</li><li>**Determinism:** everything is seeded by the film's title.</li><li>**Idempotent:** a film that already has crowd ratings is skipped.</li></ul> |
| **Circulating** (`catalogue.rating_shown`) | Every rating read counts and shows a rating only from its `created_at` on: the listing card, the film page's breakdown, the review list and its Helpful counts (votes too), and the Helpful write. Future-dated rows appear day by day and the averages drift, with no job. The listing cache holds a count for at most its 60 s TTL. A customer's own write is stamped with the clock, so it shows at once. A re-rate pulls a future `created_at` back to now. |
| **Seats sold** (`backend/app/domain/demo_fill.py`) | <ul><li>**Target:** a show's share sold at T is `final(show) × ramp(days to start)`. `final` averages 82–85%: more at weekends and in the evening, less in the morning, about 1 show in 12 near sold out and about 1 in 14 weak. The ramp gives ~10% three weeks out, ~34% one week out, ~72% two days out, and 100% at the start.</li><li>**Seats:** they go in groups of 1–6 side by side in one row (mostly pairs), centre and premium seats first.</li><li>**Bookings:** each group is a real booking: captured payment, confirmed booking, priced `booking_seat` rows, and a suppressed receipt. So the reports count it.</li><li>**Locks:** each seat's hold lock is taken first, so a held seat is skipped, and the UNIQUE guard stays.</li><li>**Trigger:** the listing's existing hourly schedule check (`schedule:topup:checked`), right after the top-up, so new shows get their bookings too. At most 4,000 seats per call, nearest shows first.</li></ul> |
| **Backfill** (`scripts/demo_bookings.py`) | The same function with no cap, over shows from 14 days back to 22 days ahead. Run it once. |

## Judgment calls

- **The raters are not made verified viewers.** That would need about 10,000 bookings on past shows of the demo films, which have only a few days of history, and the future-dated ratings would need bookings on shows that have not happened yet. It would also put those sales into the reports. Explained in the script's docstring.
- **Rate limit: once an hour for all shows, not once per show per hour.** The one listing-read key already gates every show. A per-show key on the seat-map read would add a Redis write to a request that is polled every 3 seconds.

## Storage: worst number first (reasoned, not measured on Neon)

Demo bookings are permanent ("bookings are permanent" is kept), and `demo_delete_history` still deletes old shows' `showtime_seat` rows but keeps any showtime a booking references, so once every show has bookings **the old showtime rows stay too** (small: one row each). Growth is about 24 shows × ~150 seats × 85% ≈ 3,000 `booking_seat` rows a day, plus ~900 bookings, payments and receipts. That is roughly **1 MB a day**, or about 0.36 GB a year, on Neon's 0.5 GB free plan. **A ruling is needed** (reserved: deleting data) before about month 9: either let the demo also delete its own crowd's bookings older than `DEMO_HISTORY_DAYS`, or accept the growth.
