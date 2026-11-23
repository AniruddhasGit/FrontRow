# CR-013: Anyone signed in can rate, reviews become one scrolling list, and a star filter

| | |
|---|---|
| **Raised** | 2026-11-23, by the owner, in a working session |
| **Status** | **Built locally, not deployed.** No database migration: the change is in queries, the API and the film page only. |
| **Amends** | CR-011 F4's rating and review gate (the lead's call then: verified viewers only). The owner overrides it. Nothing in the frozen sources. |

## What the owner asked for (their words)

1. "If I login I should have the option to rate the movie. the option should be available right on top of the other ratings."
2. "make a scroll list rather than the boxes for the comments of other people. and the rating besides it."
3. "and give them a stars based filter."

## Decisions (by the lead, on the owner's behalf)

| | Decision |
|---|---|
| **A. Who may rate** | Any signed-in customer may rate a released film and write or edit their review. A booking is no longer needed. Kept: no rating of a coming-soon film (`403`; they Like it instead), one rating per customer per film, editable by its author, and a Helpful vote once per customer and never on one's own review. |
| **B. The badge tells the truth** | Each review item from `GET /api/movies/{id}/reviews` carries `verified`. It is true when the author has a confirmed, captured booking for that film whose show has started, or when the author is a demo crowd account (CR-012 ruling 2: the crowd keeps the badge). The crowd is marked the same way as everywhere else: `customer-51@` onward at a `.invalid` domain (`demo_fill.crowd()`, now the one predicate that `crowd_statement` also uses). It is computed in the same query as the page of reviews (a correlated `EXISTS`), never one query per review. The film page shows "Saw it at FrontRow" only when `verified` is true. |
| **C. Star filter** | Scores are 1 to 10. The filter offers All, then 9–10, 7–8, 5–6, 3–4 and 1–2, each labelled with stars and a count, for example "★★★★★ 9–10 (17)". It is filtered on the server: `?band=9-10` (and the others), and any other value is `422 VALIDATION_FAILED` with `{"field": "band"}`. The counts are of **reviews** (ratings with text), returned as `bands` with every list in one extra grouped query; they do not change with the band chosen. The filter combines with Newest / Most helpful. An empty band says "No reviews scored 5–6 yet." |

## What was built

| Piece | Behaviour |
|---|---|
| **Rating gate** (`backend/app/api/account.py`) | `PUT /api/me/ratings/{id}` and `PUT /api/me/reviews/{id}` refuse only a coming-soon film. `can_rate` on `GET /api/me/movies/{id}` is now "the film is out". |
| **Reviews read** (`backend/app/domain/browse/catalogue.py`, `backend/app/api/browse.py`) | `band` query parameter, `bands` counts, `verified` per item. `count` is the number of reviews in the chosen band, or all reviews when no band is chosen. |
| **Your rating** (`FilmDetails.tsx`) | The 1–10 buttons, Write/Edit your review and the form moved to the top of the Reviews section, above everyone else's reviews (`#film-rate`). A guest sees "Sign in to rate and review it." with the link back to the page. The Ratings box keeps the average and the bars. For a coming-soon film (no reviews section) the Like control stays in the Ratings box under the same id. The hero's "Rate now" link (`MovieScreen.tsx`) now points at `#film-rate`. |
| **The list** (`Reviews.tsx`, `discover.css`) | One vertical list in a scroll area (32rem tall, 26rem on a phone, never sideways), rows divided by hairline rules. Each row has the initials, the name, the badge when verified, the score "★ 8/10" to the right of the comment (beside the name on a phone), the comment, and the date, the helpful count and the Helpful button. The list is a real `ul`; the scroll area is a focusable, labelled region; the star filter and the sort are both `ChoiceGroup` toggle groups with `aria-pressed`. |
| **Contract** | `docs/03 PRD/sections/E5_account.md` (P-ACC-17, P-ACC-18, EP-ACC-20, -22, -23) edited; `contract.json` and `FrontRow_PRD.md` regenerated; `generate_api.py --all` passes. |

## Checks

- Backend: `tests/cr11/test_reviews.py` (three new tests: a non-viewer rates and reviews and a coming-soon film is refused; `verified` true and false in the right cases; the band filter, its 422 and band + sort), with the CR-011 and CR-008 tests that asserted the old 403 amended and marked.
- Frontend: `tsc -b`, `node --test` (a new test for the band helpers in `flow.test.mjs`).
- Browser: `e2e/walk_cr013.mjs`, screenshots in `e2e/evidence/reviews2/`.
