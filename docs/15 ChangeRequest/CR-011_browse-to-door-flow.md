# CR-011: The customer flow - top 10 sidebar, All films with filters, a BookMyShow-style film page, reviews, the door

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session |
| **Status** | **Asked for by the owner** 2026-11-22. In progress. Local commits; the owner decides when it ships. |
| **Amends** | CR-005 (the landing book flow), CR-008 T10/T12 (landing rows, ratings), S-XCT-47 and S-SCP-10 (the word "recommend" is allowed for "You might also like", on the owner's request). |

## What the owner asked for (their words)

"How the flow should go like the person shows up and is logged out, then they are able to browse a few films like 10 max in the left side bar which are top 10 rated one, then to explore more movies they'll have to hit on all films then they'll be able to see all the films and on top they can have the filters like date and search title and genre and language and ratings,

once the person selects the movie and they go in then they'll see the movies description and poster and shows on which screens and reviews and comments stars in the movie recommendations stuff on page which looks like this: https://in.bookmyshow.com/movies/pune/party-animals/ET00519397

and then there will be a door which is half open which has enter written on top like a theatre door, and as soon as the person hits that door then the animation that we already have kicks in where it looks like as if you are walking into the hall and then you'll be able to see all the seats and do the seat bookings from there as it should work as we already have it built then pay and then be able to see the bookings or be able to go back to the all films to browse more stuff."

Reference read: the BookMyShow movie page has a hero (poster, rating and votes, "Rate now", formats, languages, runtime, genres, certificate, release date, "Book tickets"), About the movie, Cast and Crew (sideways carousels there - here they wrap, per CR-008 T16), Top reviews with helpful votes, and "You might also like".

## Decisions (the lead's, the owner may override)

- "Reviews and comments" = reviews (stars + text) by customers with a paid booking for the film whose show has started, editable by their author, plus a "Helpful" vote per customer per review. No open comment threads (they would need moderation).
- "Recommendations" = "You might also like": other published films sharing genres, ranked by shared genres then rating.

## The list, and what marks each task done

| # | Task | Done when |
|---|---|---|
| F1 | Logged-out landing: the left sidebar lists the top 10 rated published films (ties: vote count, then title), max 10, then an "All films" button. | Signed out, the sidebar shows ≤ 10 films in rating order (browser + unit test of the ordering); All films opens /films. |
| F2 | All films (/films): filters on top - title search, genre, language, date, minimum rating; combinable, reflected in the URL, kept on reload; wrapping grid. | Each filter and combinations narrow correctly (backend/unit tests + browser run); no sideways scroll (the CR-008 sweep passes). |
| F3 | Film page in the BookMyShow layout: hero (poster, rating + votes, Rate now, format, language, runtime, certificate, genres, release date), About, shows grouped by screen per date, cast and crew (wrapping), reviews, You might also like. | Every section shows real data on a film with shows, and a sensible empty state on a film without; screenshots at 360/768/1440. |
| F4 | Reviews: write/edit (verified viewers only, server enforced), list (newest / most helpful), Helpful votes once per customer. | Backend tests: viewer posts, non-viewer 403, edit, one helpful vote per customer, author cannot vote own review. |
| F5 | The door: choosing a showtime on the film page reveals a half-open theatre door with ENTER above it and the screen name and time. | Door shows the chosen show; operable by mouse and keyboard (a real button with a name); hover/focus opens it a little more; reduced motion respected. |
| F6 | Walk in: pressing the door plays the existing walk-in (the fly-in arrival) into that screen's hall and lands on seat selection for that showtime. | Browser run: film page → show → door → walk-in → seat map of that exact showtime; reduced motion goes straight to the seats. |
| F7 | Book → pay → confirmation → My bookings, or back to All films. | Full journey in a browser end to end; header Back at each step goes to the previous screen. |
| F8 | Checks. | State machines of the new flows reviewed (one explicit status each); the no-sideways sweep, backend suite, frontend tests and `tsc -b` pass; screenshots of each step in `e2e/evidence/cr011/`. |

## F1-F8: what was built

Built 2026-11-22 (local commits only, nothing pushed or deployed). One migration (`0007_reviews_helpful_votes`), regenerated
from `docs/06 DataModel/datamodel.json` (30 tables; `generate.py --check` PASS, `consistency_check.py` 15/15 PASS): the column
`movie_rating.review_text` (1-2000 characters, CHECK) and the table `review_vote` (`UNIQUE(rating_id, user_id)`, frontrow_app
SELECT + INSERT only). Three endpoints `EP-ACC-22..24` under the new row `P-ACC-18` (E5) and two fields on `EP-ACC-19`,
regenerated into `contract.json` (77 endpoints, `generate_api.py --all` PASS). No new dependency, no timer, no polling.
Applied to the local database (alembic 0006 -> 0007; the local API image rebuilt).

| Task | Piece | Behaviour | Where |
|---|---|---|---|
| F1 | Landing sidebar | The rail lists at most 10 films that are out: best average first, unrated last, more votes then the title breaking ties (`sidebarTop`). Heading "Top 10", then **All films** (unchanged: opens `/films`). Same list signed in or out. | `landing/Landing.tsx`, `discover/discover.ts` |
| F2 | All films filters | A left column on desktop (folds behind a **Filters (n)** button under 60rem): Title (search box), Genre (from the films listed), Rating (Any, 6+..9+; an unrated film never passes), then the existing Date grid, Language, Format, Cinema. All combine and live in the URL (`q`, `genre_id`, `min_rating` beside the server's four); a reload keeps them; Clear filters clears all. Title / genre / rating narrow the server's answer on the client (no request per keystroke). | `browse/ListingScreen.tsx`, `browse.css`, `narrowFilms`, `genresOf` |
| F3 | Film page | Hero over the film's own poster (blurred): poster card ("In cinemas" / "Coming soon"), title, a rating box (★ x.x/10 and votes, or likes for a film not out) with **Rate now** / **Like it**, `1h 54m • genres • certificate • release date`, format + language chips, **Book tickets** (scrolls to the showtimes), Save and Share. Then Showtimes (week grid; a card per screen with its formats and times), About, Cast and Crew as wrapping initials tiles, Ratings, **Top reviews**, **You might also like** (films sharing genres, most shared then rating then title, 6, View all films). Empty states: "No showtimes for this movie." / "No reviews yet..." | `browse/MovieScreen.tsx`, `discover/FilmDetails.tsx`, `discover.css`, `byScreen`, `recommended` |
| F4 | Reviews | A verified viewer (the rating gate: a captured booking whose show has started, checked in the write's transaction) writes or edits a review with their score; anyone reads them newest or most helpful first; a signed-in customer marks another's review Helpful once (a second press changes nothing; no button on your own). Author shown by display name, else "FrontRow viewer", never the email. | `api/account.py`, `api/browse.py`, `domain/browse/catalogue.py` `reviews`, `discover/Reviews.tsx` |
| F5 | The door | Choosing a time (a plain click; a modified click still opens the seats in a new tab) shows that screen's door: a dark foyer, a lit **ENTER** sign, a half-open leaf on a perspective hinge with warm light through the gap and across the floor, the plate `SCREEN n · time`. One real `<button>` named "Enter SCREEN n for <film> at <time>"; focus moves to it; hover/focus swings it wider. Notes for a show already started and for adults-only certificates (A, R, NC-17, 18+: carry ID). The chosen show stays in the URL (`?show=`). Reduced motion: no swing, no flicker. | `discover/Door.tsx`, `door.css` |
| F6 | Walk in | Pressing the door swings it open and floods the page with warm light (700 ms, a timer: it always leaves), sets `fr.walkin` = the showtime and navigates holding the frame until the hall draws (`nextHallDrawn`). Hall3D then flies the baked **entrance route** (`hallN.json intro`: the ENTRY door to the all-seats view) instead of the seated arrival, landing on the seat map of that exact showtime. Reduced motion: straight to the seats (HallScene cuts). **No HallScene.tsx change** (the 3-line read is in `Hall3D.tsx`). | `hall3d/Hall3D.tsx`, `hall3d/hallReady.ts` |
| F7 | After paying | The confirmation gains **My bookings** and **Browse all films**. Header Back: seats -> film page (door still open, from `?show=`); checkout -> seats. | `ticket/ConfirmationScreen.tsx` |

### Endpoints

| Id | Route | Who | Notes |
|---|---|---|---|
| EP-ACC-22 | `GET /api/movies/{movie_id}/reviews?sort=newest\|helpful` | anyone | at most 50 + `count`; 404 for a film no customer can see; 422 for another sort |
| EP-ACC-23 | `PUT /api/me/reviews/{movie_id}` `{score, text}` | signed in | 403 without the viewing gate; 422 score outside 1..10 or text empty / over 2000; upsert on the one rating row |
| EP-ACC-24 | `POST /api/me/reviews/{review_id}/helpful` | signed in | 403 own review; 404 no such review, no text, or film hidden; ON CONFLICT DO NOTHING |
| EP-ACC-19 (amended) | `GET /api/me/movies/{movie_id}` | signed in | + `review`, `review_id`, `voted` |

### State machines (F8)

Every new flow has one explicit status: the door `Door = closed | opening` (exit: a timer, a second press is ignored);
the review list `ReviewList = loading | error | ready` (15 s ceiling, aborted on sort change); a vote
`idle | voting(id) | failed`; the review form is open while `draft !== null`, its write reuses FilmDetails' `Write`. The
`/films` Filters panel is a plain open/closed toggle with no wait. No flags pile, no poll.

### Tests

| Suite | Covers |
|---|---|
| `backend/tests/cr11/test_reviews.py` (2) | 401 without a session; 403 before the show starts and for a non-viewer; 400/422 bodies; post, trim, edit in place (count stays 1, average follows); list fields (author, written_at in the cinema's offset, no email); `review` / `review_id` / `voted` on EP-ACC-19; 422 bad sort, 404 unknown film; Helpful 401, 403 own, once per customer (a second press stays 1), 404 on a score with no text; newest vs most-helpful order; "FrontRow viewer" |
| `frontend/src/features/discover/flow.test.mjs` (6) | sidebar order and cap; each filter and combinations; You might also like order; showtimes by screen; review bounds, initials, adults-only, door status; the door rendered as one named button with ENTER, screen and time |
| Amended | `S-XCT-47`, `S-SCP-10`: the identifier `recommended` (the You-might-also-like helper) is allowed, any other "recommend" still fails; `test_discovery.py` EP-ACC-19 body (+3 fields); table counts 29 -> 30 (`S-XCT-04`, seed kit); contract 74 -> 77 (`S-SCP-01`, `S-ACC-10`); `scripts/seed.py` wipe list (+`review_vote`) |

**Browser walkthrough** (`e2e/walk_cr011.mjs browse|door|book|review`, local stack, accounts `e2e-sweep-1/2`):
sidebar = 10 films in the computed order; All films -> 20 cards; Title "the" 12, + Adventure 5, + 7+ stars 0, URL
`q=the&genre_id=8&min_rating=7` kept on reload; phone filters fold. Film page at 360/768/1440 and a coming-soon film with
no shows. Door: the click moved focus to "Enter SCREEN 1 for Silent Sky at 6:00 pm"; Enter on the keyboard opened it;
walk-in flown from the entrance; landed on `/showtimes/757`; header Back returned to `/movies/24?date=...&show=757` with
the door open; reduced motion went straight to the seats. Booking: seat -> hold -> checkout -> Back -> seats -> pay ->
FR-V5JK-YFKT -> My bookings lists it -> Browse all films. Reviews: `e2e-sweep-1` (saw Outpost 77) posted; no Helpful on
their own; `e2e-sweep-2` voted, a repeat POST stayed 1; a non-viewer PUT got 403. Screenshots: `e2e/evidence/cr011/f1-*` to `f7-*`.
