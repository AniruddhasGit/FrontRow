# CR-006: The demo never runs out of shows, and deletes its own old history

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session |
| **Status** | **Accepted by the owner** 2026-11-22 (their own words, below). Applies to the **Render demo copy only**: both behaviours are configuration values that default to 0 (off), and the AWS copy leaves them 0. |
| **Amends** | S-ADM-09 (one more showtime writer), S-XCT-09 and S-ADM-19 (one named deletion), for the demo copy only. "Bookings are permanent" is kept. SRC-003's "nothing runs on a schedule" is kept: there is no timer of any kind. |

## What the owner asked for (their words)

- "write the code to keep refreshing the dates, so they never expire and the same 10 movies that i give will keep on repeating"
- "to not run out of neon storage i dont mind if we deleted the history ... keep 4-5 months then delete freeing up my free tier neon"
- Choices made in the session: top-up on visit (not a long seed, not a manual re-run), and the demo films' posters ship with the website.

## What was built

| Piece | Behaviour |
|---|---|
| **Schedule top-up** (`backend/app/domain/schedule.py` `top_up`) | <ul><li>**Trigger:** a public listing read, at most once an hour (Redis key `schedule:topup:checked`), and only when `DEMO_SHOWTIMES_AHEAD_DAYS` > 0.</li><li>**When it acts:** the last showtime starts less than (horizon − 7) days from now.</li><li>**What it does:** the last 7 days are copied forward week by week. Each copy keeps its hall, local slot, price and format, and moves to the next published film by id, so the films rotate. Its end keeps the copied show's changeover after the new film's runtime. Seat sets are written by the admin path's own `write_seat_set`, and each film's `display_until` is pushed to cover its new shows.</li><li>**Lapsed schedule:** the first copy jumps whole weeks so it lands in the current week, never the past.</li><li>**Concurrency:** a Postgres advisory lock makes concurrent visitors one top-up.</li></ul> |
| **History deletion** (`schedule.delete_history`, migration `0004` `demo_delete_history`) | <ul><li>**Same hourly check:** when `DEMO_HISTORY_DAYS` > 0, the per-seat rows (`showtime_seat`) of showtimes that started more than that many days ago are deleted, and so are those old showtimes that no booking references. The seat rows are where the space goes (~160 per show).</li><li>**Kept:** bookings, booking seats, payments, receipts and idempotency records are never deleted, so "bookings are permanent" and S-PAY-06/S-XCT-36 still hold on the demo.</li><li>**Through one function only:** a single `SECURITY DEFINER` function that refuses a cutoff less than 30 days ago. `frontrow_app` still has **no DELETE grant**, and every foreign key stays `RESTRICT`.</li></ul> |
| **Demo posters** | A film whose `poster_object_key` starts with `/art/` is redirected to that static file (`frontend/public/art/films/…`), not to the bucket. The redirect keeps the same shape, so the client is unchanged. |

## Values

| Setting | Render demo | AWS | Local compose |
|---|---|---|---|
| `DEMO_SHOWTIMES_AHEAD_DAYS` | 21 | 0 | 21 |
| `DEMO_HISTORY_DAYS` | 150 (about 5 months, the owner's "4-5 months") | 0 | 0 |

**Storage at 150 days, ASSUMED from the local measurement and not observed on Neon:**
- About 72 showtimes a day and about 160 seat rows each.
- That gives about 1.7 million `showtime_seat` rows at steady state. The local database is 42 MB at 196k rows, so the steady state is roughly **350 MB**, under Neon's 0.5 GB but not by much.
- If Neon's usage page shows it climbing past about 400 MB, lower `DEMO_HISTORY_DAYS` to 90.

## Not audited, and why

The top-up and the deletion have no actor, and S-ADM-02 forbids an audit row without one. Each run writes one log line (`demo schedule topped up` / `demo history deleted`, with counts) instead.

## Tests

- `backend/tests/brw/test_cr006_schedule.py`:
  - the week copied forward and rotated, only once an hour;
  - off by default;
  - a lapsed schedule restarts in the current week;
  - history deleted with its bookings and nothing newer, by the restricted role;
  - the function refusing a cutoff less than 30 days ago.
- `backend/tests/adm/test_s_adm_19.py::test_the_one_demo_exception_stays_the_only_one`:
  - `demo_delete_history` is the only `SECURITY DEFINER` function;
  - it is called only from `schedule.py`;
  - there is no DELETE grant on the booking tables.

## Addendum, 2026-11-22: the owner's nine demo films

The owner supplied eleven AI-generated films, each with a poster and a widescreen still. The names and faces are invented.
The films are: Outpost 77, The Iron Garden, Echoes of the Desolate, Deep Sea Reckoning, The First Chronicle,
Neon Reverie, The Last Stage, Apartment 4B, Voidbound, Aria and the Star Whales and Echoes of the Steppe.

A second batch of nine followed the same day (20 films in all): The Dragon's Oath, The Astral Grimoire, The Redwood
Covenant, The Marigold Reunion, The Edge of the Map, Paws & Claws: The Great Alley Caper, Caldera, Iron Horizon and
Silent Sky. Shipped ahead of CR-007/CR-008: the image commit alone was cherry-picked onto the Render copy (`frontrow`), the web
service alone was deployed, the images were checked live, then `demo_films.py` ran on Neon: 20 published, 486 future
showtimes rotated across them.

- **Images:** posters are 1000×1500 WebP, about 210–370 KB. Stills are cropped to the screen's 2.39:1 and are
  1920×803 WebP, about 90–240 KB. Both ship with the website under `frontend/public/art/films/`.
- **Posters:** a film's `poster_object_key` of `/art/films/<slug>.webp` makes the poster route redirect there.
- **Screen stills:** the 3D screen follows that redirect and loads `<slug>-still.webp`. Any other poster has no
  still, and the screen keeps the title card.
- **Loading the films:** `scripts/demo_films.py` was run once on each database, as the owner role. It is idempotent.
  - It upserts the nine films with English, PG/PG-13/R and real genres.
  - It renames the two formats to 2D and IMAX and withdraws the DEMO vocabulary.
  - It unpublishes the four DEMO MOVIE placeholders, which are kept so that past bookings still name their film.
  - It deals every future unbooked showtime across the nine films in turn, so each plays daily.
- **Afterwards:** the schedule top-up keeps rotating the published films.
