# CR-008: Personal account (rewards, wishlist, sidebar), discovery features, realistic speakers, hall mistakes, state machines

| | |
|---|---|
| **Raised** | 2026-11-22, by the owner, in a working session (after a BookMyShow comparison) |
| **Status** | **Asked for by the owner** 2026-11-22. In progress. Local commits only; no push or deploy until the owner says. |
| **Amends** | The frozen scope (SRC-001): adds customer-facing account features, discovery and a loyalty discount. Payments stay simulated. "Nothing runs on a schedule" is kept: every new feature is driven by a request or an event (a booking), never a timer. |

## What the owner asked for (their words)

- "i like the recommendations that you gave me, i would also like to just add the rewards per account so they can collect points and get discounts, a customer can bookmark and in the sidebar they have it is going to be their personal account side bar, in which they can have stuff from this list above as you said also add stuff that you can come up with as of right now the webapp looks bland and boring. add more stuff to it like features which will work end to end and make it fill up."
- "make sure that all the implicit state machines in my app are working correctly and the new ones are fitting in properly."
- "in the theatres all the speakers ... none of them look realistic ... very pointy edges ... no texture and there is no light shading ... for all the halls and all speakers."
- "there's lots of stupid mistakes like this [an ENTRY door sticking out of the wall, its sign cut off] fix those."
- "make a list ... mention in that list doing what will make it such that you can mark that task as done ... follow this list ... don't stop, keep going."

## The list, and what marks each task done

| # | Task | Done when (the check that marks it done) |
|---|---|---|
| T1 | **Hall mistakes** (doors, signs and anything else poking through or floating) in all six halls | A new automated geometry check (`check_halls.py`) passes for all six halls: every door frame, leaf, bar and sign box sits flush on its wall plane (within 1 cm) and inside the room; every sign's text lies fully inside its sign box and faces the room; no speaker, door or rail intersects a wall, a row or another fixture. A close-up render of every door and every speaker type in every hall is looked at and shows nothing wrong. |
| T2 | **Realistic speakers** (side, rear and ceiling, all halls) | Every speaker is a bevelled cabinet (no sharp box edges) with a woven fabric grille (procedural texture + normal/bump), a recessed baffle and visible drivers behind the cloth, and materials that take light (roughness, sheen). Close-up renders show rounded edges and shading. All six halls are re-baked and copied to the site; `check_sightlines.py` still reports 0 blocked; the seat positions are unchanged. |
| T3 | **Rewards: points and discounts per account** | A customer earns points on every paid booking (once, even if payment is retried), sees the balance and history, and can redeem points for a discount at checkout. The server computes the discount; redeeming more than the balance, twice at once, or on a failed payment is refused or rolled back. Backend tests cover earn, idempotent earn, redeem, over-redeem, concurrent redeem and rollback on payment failure. A browser run books, sees points arrive, then redeems them and pays a smaller total. |
| T4 | **Bookmarks (wishlist)** | A bookmark toggle on film cards and the film page saves the film per account, survives a reload, and lists in the account sidebar and a Wishlist page. A guest is sent to sign in and the bookmark is applied after. Backend + frontend tests. |
| T5 | **Personal account sidebar** | A ☰ button opens a right-side panel: a greeting, points balance, and links to My bookings, Wishlist, Rewards, Notifications (with an unread count), Profile & settings, Help & support, Sign out; a guest sees a sign-in nudge. It opens and closes by mouse and keyboard (Esc, focus kept inside, focus returns), works at phone width, and every link opens a working page. |
| T6 | **Profile & settings** | A customer can edit display name, phone and preferred language and format; saving persists through the API and shows on reload; validation errors show inline. Tested. |
| T7 | **Notifications** | Events (booking confirmed, points earned, points redeemed) create in-app notifications; the sidebar and header show the unread count; opening the inbox lists them and mark-read / mark-all-read work. No polling timer is added. Tested. |
| T8 | **Help & support** | A Help page with an accessible FAQ (accordion) about booking, holds, payment, rewards and cancellation, and a contact form that stores the message (no email sent). Reachable from the sidebar and footer. |
| T9 | **Search** | A header search finds films by title and genre as you type (debounced), with keyboard navigation, a no-results state, and Enter opening the film. Tested. |
| T10 | **Landing content rows** | The landing page gains rows under the hall: Recommended (top rated), Now showing, Coming soon, each a horizontal poster row with See all. Rendered from the API; links work. |
| T11 | **Genre line on cards** | Every film card shows its genres under the title. |
| T12 | **Ratings and likes** | A customer with a past booking for a film can rate it 1-10 (server enforced); cards and the film page show the average and vote count; an upcoming film shows a like count and a like toggle. Tested. **Extended 2026-11-22** (owner: "As people scroll through the movies list they should be able to see the star rating right beside without opening and when opened they'll see more details ... the ratings count as well along with descriptions and all the other stuff."): every film card in lists and on the landing shows the star average beside the title ("New" when unrated); the film page shows average, rating count, a 1-10 breakdown, the viewer's own rating, and full details (description, genres, runtime, certificate, language, release date, cast and crew; missing fields added to the schema and the admin film editor). Done when all of this shows in a browser from database data, the count changes after a verified viewer rates, and a non-viewer is refused (backend test). |
| T13 | **Extra features** (proposed) | (a) a featured-films hero carousel on the landing (pauses on hover/focus, reduced motion respected); (b) "Add to calendar" (.ics) on the booking confirmation; (c) Share for a film and a booking (Web Share, copy-link fallback); (d) Recently viewed films row (per browser). Each works end to end in a browser run. |
| T14 | **State machines** | `claude_leash/prompts/state-machine-review.md` run over the whole app, old flows and new: every implicit state machine listed; every CONFIRMED finding fixed with a test that failed before; every new flow uses one explicit status (a union or reducer), not a pile of flags. Report saved here as an appendix. |
| T15 | **Verification and records** | Backend test suite, frontend unit tests, `tsc -b` and the affected e2e checks pass on the local stack; a browser walkthrough of every new feature with screenshots; the graphics library (`claude_leash/Graphics/FrontRow/`) updated; local commits in both repos; nothing pushed. |
| T16 | **No horizontal scroll anywhere** (owner, 2026-11-22: "i do not want this kind of horizontal scroll come up with something better. Infact no horizontal scroll through out the entire app.") | An automated browser sweep of every route at 360, 768 and 1440 px finds no element with `overflow-x` auto/scroll whose `scrollWidth > clientWidth`, and no page wider than the viewport. The date strip becomes a wrapping week grid; the 2D seat map fits its panel (scaled, screen still centred, tap-to-zoom a block on phones); landing rows are wrapping grids. |

## T3-T8: what was built

Built 2026-11-22 (local commit only). One migration (`0005_account_features`), regenerated from
`docs/06 DataModel/datamodel.json` (27 tables; `generate.py --check` and `consistency_check.py` 15/15 PASS); nine new
endpoints in `E5` (`EP-ACC-09..17`, `P-ACC-16`) and two optional fields on `EP-PAY-01`, regenerated into
`contract.json` (70 endpoints, `generate_api.py --all` PASS). No new dependency, no timer, no polling.

| Piece | Behaviour | Where |
|---|---|---|
| Points ledger (T3) | `reward_entry` (earned / redeemed, `UNIQUE(booking_id, kind)`), `users.points_balance` with `CHECK (>= 0)`. Earn and redeem run **inside the booking-confirm transaction**: a 402 or an expired hold rolls the redemption back with the booking; a retried confirm replays the stored answer and the unique key makes a second earn impossible. Redeem locks the caller's `users` row (`FOR UPDATE`) and spends with a conditional `UPDATE ... WHERE points_balance >= n`. | `backend/app/domain/rewards.py`, `app/api/bookings.py` |
| Checkout (T3 + the lead's CONFIRMED finding) | The checkout now reads the **server's** hold on arrival (`GET /api/holds/{token}`) and shows its seats and total, then asks `GET /api/me/rewards?quote_paise=` for the points offer. Pay sends `use_points` and `expected_total_paise`; the server computes the discount against its own hold and answers **409 `TOTAL_CHANGED`** (new registry code) with `details.total_paise` when the totals differ, booking nothing; the screen re-reads the hold. Fixes "tab A shows 2 seats, Pay books 3". | `features/booking/CheckoutScreen.tsx`, `checkout.ts` |
| Bookmarks (T4) | `bookmark` (`UNIQUE(user_id, movie_id)`, un-save = `saved=false`, no DELETE grant). Save toggle on every `/films` card, the film page and the landing's film bar; Wishlist page. A guest's Save stores `fr.pending_bookmark`, goes to sign-in with `?next=` back, and Shell applies it once signed in. | `features/account/Bookmark.tsx`, `AccountScreens.tsx` |
| Account sidebar (T5) | ☰ button in the header (guest and signed in) opening a native modal `<dialog>` from the right: greeting, points, My bookings, Wishlist, Rewards, Notifications (unread count), Profile & settings, Help & support, Sign out; guest: "Unlock rewards and bookmarks" + Sign in / Create an account. Esc closes, focus stays inside (modal), focus returns to ☰, any navigation closes it, 360 px wide fits. | `features/account/AccountMenu.tsx`, `Shell.tsx`, `account.css` |
| Profile & settings (T6) | Display name, phone, preferred language and format (active entries from `/api/reference`); client check mirrors the server's; the server's 422 names every failing field (`details.fields`) and each shows inline. | `EP-ACC-15/16`, `AccountScreens.tsx` |
| Notifications (T7) | `notification` rows written by the confirm transaction only (booking confirmed, points earned, points redeemed; `UNIQUE(booking_id, kind)`). Unread count from `GET /api/me/summary`, read on navigation and once after a page marks something read (`fr:account-changed` event) - no timer. Inbox with mark-read and mark-all-read (only the caller's rows). | `EP-ACC-09/13/14` |
| Help & support (T8) | `/help`: seven-question FAQ as native `<details>` (booking, holds and the countdown, simulated payment, rewards, bookmarks, cancellation, entry) and a contact form stored in `support_message` (guest gives an email; a signed-in sender is filed under their account). 5 per hour per IP (the register bucket's capacity under its own key). Linked from the sidebar and every page's footer. | `EP-ACC-17`, `HelpScreen.tsx`, `layout.tsx` |

### Values (all in `backend/app/domain/rewards.py`, nowhere else)

| Rule | Value | Worked example (checked against the rule's absence) |
|---|---|---|
| Earn | `EARN_POINTS_PER_UNIT = 10` per whole dollar actually paid (after discount), floored | paid $830.73 -> 830 -> 8,300 points; $0.99 earns 0 |
| Redeem | `REDEEM_POINTS_PER_UNIT = 100` points = $1.00 (1 point = 1 cent at ratio 100) | 250 points -> $2.50 off |
| Cap | `REDEEM_CAP_DIVISOR = 2`: discount <= order // 2 (50%), floored | order $309.39: cap 15,469 (15,469.5 floored), pays $154.70; a rounded cap would pay $154.69, under half |
| Choice | the customer only ticks "use my points"; the server spends `min(balance, cap)` | |

### Tests

| Suite | Covers |
|---|---|
| `backend/tests/cr8/test_rewards.py` (9) | earn + notifications; idempotent earn (replayed key, and `earn()` twice); redeem pays a smaller total (quote = confirm); the cap's floor; over-redeem refused (conditional update and the CHECK); two confirms at once spend the balance once (real overlap via the payment gate); 402 rolls the redemption back; expired hold spends nothing; `TOTAL_CHANGED` on the two-tab repro, then success with the server's total |
| `backend/tests/cr8/test_account.py` (5) | every route 401 without a session; bookmark save/unsave/idempotent/only-mine/404 for a hidden film; inbox lists events, mark-read only the caller's, bad bodies 400; profile save, inline field errors, partial PUT refused; support message for a guest and an account |
| `frontend/src/features/account/account.test.mjs` (10) | load states, wording, `payExtras` (the total the screen shows), pending bookmark, saved-set reducer, profile validation, checkout discount line and Pay name, Help FAQ and form labels, menu button name, Rewards / Notifications states |
| Amended | the users column set in `S-ACC-01`, `S-ACC-03`, `S-ADM-02` (+5 CR-008 columns); `S-ADM-27` visibility callers (+`account.py`); `S-PAY-08` twelve codes and two optional body properties; `S-PAY-06` cleanup truncates the two CR-008 tables; the lock allow-list (`domain/rewards.py`: `users`); `scripts/seed.py` wipe list (+4 tables); `test_s_xct_04` and `tests/seed/kit.py` 23 -> 27 tables; `shell.test.mjs` S-SCP-12 reads the footer's first paragraph (the footer gained the Help link); contract-count tests raised from the generator (see the commit) |

**No horizontal scrolling (owner rule, 2026-11-22).** Measured in the browser at 360, 768 and 1440 px: Rewards,
Notifications, Wishlist, Profile, Help and the open sidebar all have `scrollWidth - clientWidth = 0`. None of the
T3-T8 CSS uses `overflow-x`; lists wrap (the wishlist is an `auto-fill` grid, rows stack below 40rem).

**Results (2026-11-22, local stack).** Full backend suite: all green except **3 failures that predate this work** and touch no
T3-T8 file - `S-ADM-23` (failed on the untouched baseline run too), `S-PAY-11` (a docstring in `domain/admin/films.py`) and
`S-TKT-13` (the word "bounced" in a `hall3d/HallScene.tsx` comment from CR-007). Frontend `node --test`: 174 / 174.
`tsc -b`: clean. Browser (Playwright, `customer-41`): guest Save -> sign-in -> bookmark applied; booked A5+A6 ($25.98) ->
250 points + 2 notifications; sidebar at 360 px (Esc closes, focus returns, Tab stays inside); mark-all-read cleared the
badge; second booking A8 with points: $12.99 - $2.50 = **$10.49** charged (payment row 1049), balance 250 -> 0 -> +100;
profile saved and shown on reload (bad phone shown inline first); Help message stored. Screenshots: `e2e/evidence/cr008/`.
