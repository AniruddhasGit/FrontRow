# CR-012: The demo has a crowd: hundreds of ratings and reviews per film, and shows that sell

| | |
|---|---|
| **Raised** | 2026-11-23, by the owner, in a working session |
| **Status** | **Deployed** (commit `0a8124b`, 2026-11-23); the six-month booking expiry (owner ruling, below) is built locally and needs one more deploy, which applies migration 0008. Demo copy only: the seat fill runs only when `DEMO_SHOWTIMES_AHEAD_DAYS` > 0 (AWS leaves it 0). The rating visibility rule applies everywhere, and changes nothing for real customers. |
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

## Owner rulings (2026-11-23)

1. **Storage: keep six months.** Their words: "we will keep the old bookings for 6 months so we can make like a analytics page for the admin/manager. so they can track how each movie is doing and which are like the fastest filling seats and all other sorts of stuff."
2. **Badge: keep it.** The "Saw it at FrontRow" badge stays on the crowd's reviews too. No change was made.

## What ruling 1 built

| Piece | Behaviour |
|---|---|
| **Booking expiry** (migration `0008` `demo_delete_bookings`, `schedule.delete_demo_bookings`) | <ul><li>**What goes:** the crowd's bookings of shows that started more than 180 days ago (`schedule.KEEP_DAYS`). For each one, its `booking_seat` and `receipt_dispatch` rows, the booking itself, then its payment, child rows first, one statement each.</li><li>**Only demo rows, by two marks that must both hold:** the payment's `idempotency_key` is `'demo-' \|\| reference` (written only by `insert_demo_bookings`), and the booker is a crowd account (`customer-51@` onward at a `.invalid` domain).</li><li>**Left alone:** a booking that an idempotency record, reward entry or notification references, meaning someone used a crowd login by hand.</li><li>**Batching:** at most 2,000 bookings per call, oldest first. A day's worth is about 900.</li><li>**Rights:** a SECURITY DEFINER function that refuses any cutoff less than 180 days ago. `frontrow_app` still has no DELETE grant.</li></ul> |
| **Where it runs** | In the existing hourly listing check, behind `DEMO_HISTORY_DAYS` > 0 (0 on AWS: nothing runs), just before the history deletion, so shows the crowd alone had booked then go with the history. |
| **History window** | `max(DEMO_HISTORY_DAYS, 180)`, so the live value of 150 can no longer delete anything inside six months. Real customers' bookings, and every show they reference, are never deleted. |

**Render env:** no change is needed: 150 now acts as 180. To make the setting say what it does, set `DEMO_HISTORY_DAYS=180` on the Render API service, and in `../frontrow/scripts/render_deploy.py` line 133. That file is in the Render repo, not this one, and is not changed here.

## Storage: worst number first (reasoned from the local run, not measured on Neon)

- **Growth while it lasts:** the local backfill (23,608 seats with their bookings, payments and receipts, plus 6,964 ratings) grew the database by about 11 MB, so about 0.4 KB per sold seat with its share of the booking rows. The demo sells about 24 shows × ~160 seats × 85% ≈ 3,300 seats a day, which is about **1.3 MB a day**.
- **Steady state at 180 days:**
  - crowd bookings: ~235 MB;
  - per-seat show rows (`showtime_seat`) for 180 days of history plus 21 days ahead: ~50 MB;
  - today's other data: ~45 MB;
  - the ratings' future tail: ~2 MB.
- **Total: about 330 MB of Neon's 512 MB free plan**, reached about six months after the first deploy, then flat.
