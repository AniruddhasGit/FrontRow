# Round 4, Track E: real-browser checks for the Blocked rows

Prepared 2026-11-06. The engineering ledger was read only. This file is the only thing Track E wrote, and it is not committed.

**Which rows.** Every row with `Status=Blocked` whose StatusNote mentions a real browser, computed CSS, focus, the keyboard, Playwright, contrast, live regions, reduced motion or viewport width: **24 rows**. S-BRW-11 is included even though its note says "Refuted by the verifier". Its note asks to flip it back to "needs a real browser: Enter/Space dispatch" if keydown has to be proved, and this plan covers that. The appendix lists three more rows with frontend-DOM clauses that the node render harness can close without a browser.

**What this file does not do.** It does not settle each row's non-browser blockers (config conflicts, Phase 5 to 8 endpoints, doc defects). A row that passes every browser step below stays Blocked if its note names another cause. That cause is repeated in a **Still blocked by** line on each row.

---

## 0. Harness: shared setup for every row

### 0.1 Where to run it
- Playwright is **not** a frontend dependency. `frontend/package.json` has react, react-dom and vite only, and adding a dependency breaks the stack lock. Run it **out of tree** from a scratch folder:
  ```
  npm init -y
  npm i -D @playwright/test@<pinned>
  ```
  Chromium builds are already cached in `~/AppData/Local/ms-playwright` (chromium-1248). The Playwright MCP tools can also drive single checks by hand.
- **Never** use compose project `frontrow`, `frontrow_p7`, `frontrow_p8`, `frontrow_vp7ops` or `frontrow_vp8reports`.
  - `docker-compose.yml` hard-codes `name: frontrow` and the host ports `8000:8000` (api) and `8080:8080` (web). Only Postgres and Redis can be moved, through `PG_HOST_PORT` and `REDIS_HOST_PORT`.
  - So a real-backend run needs `-p frontrow_e2e` **plus** an override file kept in scratch, not in the repo. The file uses `ports: !override` to move the api to `18000` and the web to `18080`.
  - Before starting, check with `docker ps` that nothing else holds those ports.

### 0.2 Two modes
| Mode | How the app is served | When to use it |
|---|---|---|
| **MOCK** | `vite build` output served by `vite preview --port 4173`. `page.route('**/api/**', …)` answers every API call from JSON fixtures. | Every DOM, CSS, focus, keyboard, live-region, clock and geometry clause. This is the default. |
| **REAL** | The scratch config `vite.e2e.config.mjs` (root = `frontend/`) sets `preview.proxy = { '/api': 'http://localhost:18000' }` and serves the built `dist`, with the `frontrow_e2e` compose stack behind it. | Clauses that read Redis, PostgreSQL or the running app's config, or that need a server-generated 409 or 201. |

- **No same-origin proxy exists in the repo.** The app calls relative `/api/...` with `credentials: "same-origin"` (`features/browse/api.ts:12`), and `frontend/nginx.conf` has no `/api` location (the ALB routes it in AWS). Port 8080 on its own therefore cannot reach the API.
- If a Vite proxy is not wanted, use `page.route('**/api/**', async r => r.fulfill({ response: await r.fetch({ url: r.request().url().replace(':18080', ':18000') }) }))`. `route.fetch` shares the context's cookie jar, and localhost cookies ignore the port.
- In REAL mode, read Redis with `docker compose -p frontrow_e2e exec redis redis-cli …` and PostgreSQL with `docker compose -p frontrow_e2e exec postgres psql -U frontrow …`.

**Seed facts for REAL mode** (`scripts/seed.py`):
- The largest hall is screen 6: **220 seats, 11 rows × 20 cols**, rows A–K.
- Bands are Standard A–F (6 rows), Premium G–J (4 rows), Recliner K (1 row). **In the seed, Row C is Standard.** AC strings such as "Row C seat 12, Premium" are fixture strings, so assert them in MOCK. In REAL, assert the same pattern on a G–J seat.
- Accounts: `admin-01@`, `manager-01..12@` and `customer-01..50@` at `SEED_EMAIL_DOMAIN`.
- The password is the operator's `SEED_DEFAULT_PASSWORD`. Do not read it from passwords.txt; Track E names no line. Pass it in as an environment variable of the test process and never log it.

### 0.3 Context defaults (set per test unless the row says otherwise)
- `page.clock.install({ time: <fixture instant> })` **before** `page.goto`. The checkout calls `Date.now()` (`CheckoutScreen.tsx:35,52`), so the countdown and expiry follow the fake clock. Move time with `page.clock.runFor(ms)` or `page.clock.setFixedTime`.
- `reducedMotion: 'reduce'` is the default for every timing-sensitive row, **except** where reduced motion is the thing under test (S-BRW-12). Reason: with the premium layer, `navigate()` uses `document.startViewTransition`, so the screen swap paints a frame later. `location.pathname` still changes synchronously (`pushState`). Assert routes on `location.pathname`, never on the new screen's heading, unless reduced motion is on.
- Run `await page.evaluate(() => document.fonts.ready)` before **any** geometry capture (getBoundingClientRect, offsetHeight, scrollWidth). The premium layer self-hosts Inter Tight and JetBrains Mono, so text reflows when the woff2 files arrive.
- Theme: `index.html` carries `data-theme="dark"` in the premium build and nothing on main. `emulateMedia({ colorScheme })` does **not** override `data-theme="dark"`. To test light, run `document.documentElement.setAttribute('data-theme','light')`. To test dark, set it to `'dark'`. Never rely on the OS preference.

### 0.4 Helpers (define once, in an `addInitScript` or a fixture)
```js
// Resolve a token to the same serialisation getComputedStyle returns: rgb()/rgba(), px.
const token = (page, name, prop = 'backgroundColor') => page.evaluate(([n, p]) => {
  const d = document.createElement('div'); d.style[p] = `var(${n})`; document.body.append(d);
  const v = getComputedStyle(d)[p]; d.remove(); return v; }, [name, prop]);
// Text insertions into a live region, counted from page start.
// Register in addInitScript; the region may mount with its text already in it.
window.__live = []; new MutationObserver(ms => ms.forEach(m => {
  const t = m.target.nodeType === 3 ? m.target.parentElement : m.target;
  const r = t && t.closest('[aria-live]');
  if (r && (m.addedNodes.length || m.type === 'characterData'))
    window.__live.push({ live: r.getAttribute('aria-live'), text: r.textContent });
})).observe(document, { subtree: true, childList: true, characterData: true });
// Every request, in order.
page.on('request', r => log.push({ m: r.method(), u: new URL(r.url()).pathname, t: Date.now() }));
// Unload spy. Register in addInitScript.
['unload','beforeunload','pagehide'].forEach(e => addEventListener(e, () => sessionStorage.setItem('__unload_'+e, '1')));
// Wrap fetch and sendBeacon so the test sees any request made during unload.
```
- **Tabbables:** `[...root.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].filter(e => e.tabIndex >= 0 && !e.disabled && e.checkVisibility())`.
- **Accessible names:** `page.getByRole('gridcell'|'button', { name })` or `page.accessibility.snapshot()`.

### 0.5 Seat map fixture (MOCK)
- **Shape** (from `features/seatmap/model.ts`): `{ showtime:{id,starts_at,sales_close_at,sales_closed}, screen:{id,name,rows,cols}, categories:[{id,name,price_paise}], seats:[{id,row,num,gr,gc,cat,price_paise,state:'available'|'sold'|'held',is_active}], generated_at, poll_interval_seconds }`.
- **Default `F220`:** 11 × 20, `poll_interval_seconds: 3`, three categories.
- **Hold** (sessionStorage `fr.hold`): `{ hold_token, showtime_id, expires_at, seats:[{seat_id,label,category,price_paise}], total_paise }`.
- **Other sessionStorage keys:**
  - `fr.selection`: `{showtime_id, seat_ids}`
  - `fr.pending_selection`
  - `fr.confirm_idempotency_key`
  - `fr.last_booking_reference`
- **Endpoints:**
  - Seat map: `GET /api/showtimes/{id}/seatmap` and `GET /api/showtimes/{id}`
  - Holds: `POST /api/showtimes/{id}/holds`, `GET /api/holds/{token}`, `DELETE /api/holds/{token}[/seats/{seat_id}]`
  - Booking: `POST /api/bookings`
  - Auth: `POST /api/auth/register|login|logout`
  - Account: `GET /api/me/bookings[/{reference}]`
  - Receipts: `GET /api/bookings/by-reference/{reference}`
  - Browse: `GET /api/movies[/{id}]`, `GET /api/reference`

---

## 1. Rows

Each row gives:
- **AC→browser**: only the clauses that need a browser.
- **Route** and **Pre**: preconditions and data.
- **Steps**
- **Pass**
- **Mode**
- **Still blocked by**: anything outside the browser.

### S-ACC-14: carry the selection through sign-in, take no hold
- **AC→browser:**
  - `fr.pending_selection` is written before `/sign-in` opens, by both exits.
  - `fr.pending_selection` and `fr.selection` are distinct keys and both are present.
  - The context note shows on both routes.
  - After 200/201, the client navigates to `/showtimes/412` and the GET seatmap goes out before any restore.
  - The re-selection and the three "taken while you were signing in" messages.
  - Accessible names of the now-sold and now-held seats.
  - The pending key is removed afterwards.
  - Zero `POST …/holds` until the primary action, which reads "Hold these seats".
  - A stale entry (more than 30 minutes) is discarded.
  - sessionStorage that throws: nothing stored, no message, sign-in still succeeds.
  - A missing showtime returns the visitor to the listing with "That showtime is no longer available."
  - Sign-out sweeps the `fr.` namespace.
- **Route:** `/showtimes/412` → `/sign-in` → `/showtimes/412`.
- **Pre:**
  - Clock fixed at `2026-08-14T10:00:00Z`.
  - Guest (no cookie).
  - Fixture 412 with seats 1187/1188 = C12/C13 (Premium) available. A second variant of seatmap 412 for the post-sign-in fetch.
  - The `__seq` init script wraps `Storage.prototype.setItem` and `history.pushState` and pushes `['set', key]` and `['push', url]` in order.
- **Steps:**
  1. Load the page and click cells C12 and C13. Assert `fr.selection` is `{showtime_id:412, seat_ids:[1187,1188]}`.
  2. Exit A: click the button named "Sign in to hold these seats".
  3. Assert `__seq` has `['set','fr.pending_selection']` **before** `['push','/sign-in']`. Assert `JSON.parse(sessionStorage['fr.pending_selection'])` deep-equals `{showtime_id:412, seat_ids:[1187,1188], stored_at:'2026-08-14T10:00:00Z'}`.
  4. Assert `Object.keys(sessionStorage)` contains both `fr.selection` and `fr.pending_selection`. Assert the text "Your seats are still selected. Sign in to hold them." is visible.
  5. Fulfil `POST /api/auth/login` with 200. Assert `location.pathname === '/showtimes/412'`. Assert the log index of `GET /api/showtimes/412/seatmap` is lower than the first `__seq` write of `fr.selection` after sign-in.
  6. Run three fixture variants for the second seatmap:
     - C12 sold and C13 held → message "C12 and C13 were taken while you were signing in. Your other seats are still selected." Use a third chosen seat so that the other seats survive.
     - Only C12 sold → message "C12 was taken while you were signing in. …"
     - Both gone, with only those two selected → message "The seats you chose were taken while you were signing in. Choose again from the map."
     - In every variant: the cell names are `Row C seat 12, Premium, sold` and `Row C seat 13, Premium, held by someone else`, and neither cell is in `fr.selection`.
  7. Assert `sessionStorage.getItem('fr.pending_selection') === null`, `fr.selection` equals the survivors, and **0** log entries `POST /api/showtimes/412/holds` exist. Assert the primary button's name is "Hold these seats".
  8. Exit B: repeat steps 1–4 using the header link "Sign in".
  9. Stale: seed `stored_at` at 10:00:00Z with the clock at 10:30:01Z. No `aria-selected` or `data-visual=held_by_me` cell, and no message text.
  10. Throwing storage: an init script replaces `Storage.prototype.getItem` and `setItem` with throwers. The sign-in still reaches 200 and lands on the map with no selection and no message.
  11. Missing showtime: the seatmap for 412 returns 404. Expect `location.pathname === '/'` and the text "That showtime is no longer available."
  12. Sign out: `Object.keys(sessionStorage).filter(k => k.startsWith('fr.')).length === 0`.
- **Pass:** every assertion holds for both exits and all three variants.
- **Mode:** MOCK for everything. REAL optional, for register 201 against the API.
- **Still blocked by:** the feature is **unbuilt**. The note says the seat-map half (write pending on both exits, re-check, messages) does not exist, so this check is red by design until it is built. It shares the guest handler with S-SEA-10.

### S-ACC-15: the 120-second booking run, 20 + 20 runs
- **AC→browser:**
  - t0 = the first accessibility-tree node whose name matches `^Row [A-Z]+ seat [0-9]+, .+, (available|sold|held by someone else|held by you|out of service)$`.
  - t1 = the first element whose **whole** text matches `^FR-[23456789ACDEFHJKMNPQRTVWXY]{4}-[…]{4}$`.
  - Exactly three stdout lines.
  - Network log: exactly one `POST …/holds` and one `POST /api/bookings` per run.
  - `PAYMENT_SIMULATED_DELAY_MS` is read back and is > 0.
  - Expired runs counted, reported as `409 HOLD_EXPIRED`.
- **Route:** `/` → film → showtime → `/showtimes/{id}` → `/showtimes/{id}/checkout` → `/bookings/{ref}`. Run 20 signed-in and 20 first-time (register via "Sign in to hold these seats" and `fr.pending_selection`).
- **Pre:**
  - REAL stack, `frontrow_e2e`, seeded, with a showtime of screen 6 well before cut-off.
  - The signed-in set reuses `customer-01..20`. The first-time set registers 20 fresh e-mails under the seed domain.
  - Read the delay from the running app's config: `docker compose -p frontrow_e2e exec api python -c "from app.core.config import settings; print(settings.PAYMENT_SIMULATED_DELAY_MS)"`. Assert the value is > 0.
- **Steps:**
  1. Poll t0 with `page.waitForFunction` over `page.accessibility.snapshot()` (rAF-paced) and record `performance.now()`.
  2. For t1, wait for `[...document.querySelectorAll('body *')].some(e => /^FR-…$/.test(e.textContent))` on leaf elements only.
  3. Per run, assert from the request log: `count(POST /holds) === 1` and `count(POST /api/bookings) === 1`.
  4. Print the three lines with `slowest` and `median` in whole seconds, computed over the runs that reached t1. The runs counter stays 20 per line.
- **Pass:** line 1's slowest < 120. The lines match their three anchored patterns, and stdout has exactly 3 lines with no `PASS` or `FAIL`.
- **Mode:** REAL only.
- **Note:** **blocked on S-ACC-14** for the first-time path, and on the seat map having no "Continue to payment" control (S-PAY-13 note). Until that control exists, the run cannot reach checkout by clicking.
- **Premium risk:** at a viewport ≥ 48rem with WebGL, `Hall3D` lazy-loads three.js and up to 3 GLB files (the recliner alone is 2.5 MB) on the seat page. Run at a fixed viewport and record which one. t0 itself is unaffected, because the 3D stage is `aria-hidden`.

### S-BRW-02: line-clamp and the missing-poster card
- **AC→browser:**
  - `getComputedStyle(cardSynopsis).webkitLineClamp === '3'` and on `/movies/{id}` it is `'none'`.
  - A movie whose poster is missing has **no `img`** after `onError`.
  - The poster box text is exactly the title.
  - The page text has none of "No poster", "Image unavailable" or "not found".
- **Route:** `/` and `/movies/{id}`.
- **Pre:**
  - MOCK `GET /api/movies` with one movie whose `synopsis` is 900 characters, and one movie `M404`.
  - Route `/api/movies/M404/poster` → `route.fulfill({ status: 404 })`. Use an abort so the img errors.
- **Steps:**
  1. `page.goto('/')` and wait for `networkidle`.
  2. Inside `M404`'s card, `locator('img')` has count 0. `.fr-poster` textContent `=== title`. Read the computed `color` of the title text and compare it to `token('--fr-ink-muted', 'color')`.
  3. The `.fr-card-synopsis` computed `webkitLineClamp` is `'3'`.
  4. Go to `/movies/{id}`. The `.fr-movie-synopsis` computed `webkitLineClamp` is `'none'`, and textContent length is 900.
- **Pass:** all of the above.
- **Mode:** MOCK.

### S-BRW-07: a guest has no 2px cell
- **AC→browser:** for a guest on the seat map, 0 cells have a name ending "held by you", 0 cells have a computed `borderTopWidth === '2px'`, and the primary action reads exactly "Sign in to hold these seats".
- **Route:** `/showtimes/{id}`, guest.
- **Pre:** MOCK F220 with mixed states, including some `held`. No `fr.hold` and no `fr.selection`.
- **Steps:**
  1. `page.$$eval('.fr-seat', cs => cs.filter(c => getComputedStyle(c).borderTopWidth === '2px').length)` is 0.
  2. `getByRole('gridcell', { name: /held by you$/ })` has count 0.
  3. The primary button text is exact.
  4. Then add `fr.selection` for one seat and assert exactly one 2px cell. This red-proofs the probe.
- **Pass:** 0, 0, exact label, plus the red-proof shows 1.
- **Mode:** MOCK.
- **Still blocked by:** the poster 302 (S-BRW-18). The byte-identical anonymous vs signed-in body and the expired-token reads are API-level, so do them in pytest and not in the browser.

### S-BRW-11: (optional) Enter/Space on all-retired seats
- **AC→browser:** 220 cells, all out of service, none activating on Enter or Space.
- **Pre:** MOCK F220 with every `is_active: false`.
- **Steps:**
  1. Focus the map's single tabbable cell.
  2. Press `Enter` and `Space` on 10 cells, moving with `ArrowRight` and `ArrowDown`.
  3. After each press: `fr.selection` stays null, the request log adds nothing, and no cell gets `data-visual="held_by_me"`.
  4. The banner reads exactly "None of the seats in this hall are available."
- **Pass:** zero changes.
- **Mode:** MOCK.
- **Status note:** run this only if the verifier wants keydown dispatch proved.

### S-BRW-12: the inactive-seat CSS, glyphs under one colour, ArrowRight, the change ring and reduced motion
- **AC→browser:**
  - An inactive seat computes `borderStyle 'dashed'`, `borderWidth '1px'` and `backgroundColor 'rgba(0, 0, 0, 0)'`, and renders its number.
  - ArrowRight from the seat at gc−1 focuses it.
  - Name: `Row C seat 12, Premium, out of service`.
  - Enter and Space fire nothing in any state.
  - Under a stylesheet forcing every `--fr-seat-*` fill and ink token to one colour, `data-glyph` is still 4 distinct values `{outline, bar, hatch, check}`.
  - The legend has 5 swatches and the 5th reads "Out of service".
  - The all-sold grid shows 220 cells and the banner "Every seat for this showtime is sold.", and the page text has no "Nothing".
  - A seat that changes between polls carries a 2px `--fr-focus-ring` outline for `--fr-motion-change` (900 ms) and then loses it.
  - Under `prefers-reduced-motion: reduce`, `animationName === 'none'` and the outline is still held for 900 ms.
- **Route:** `/showtimes/812`.
- **Pre:**
  - MOCK 812 with C-12 sold, C-13 held (with `fr.hold` containing C-13 for the "held by you" case) and C-14 available.
  - An inactive seat "Row C seat 12, Premium" at gc 14, whose left neighbour is at gc 13.
- **Steps:**
  1. Read the computed styles of the inactive cell. Assert `borderTopStyle === 'dashed'`, `borderTopWidth === '1px'` and `backgroundColor === 'rgba(0, 0, 0, 0)'`, and that `.fr-seat-num` text is non-empty.
  2. Focus the gc−1 cell, press `ArrowRight`, and assert `document.activeElement === inactiveCell`.
  3. Press Enter and Space on an inactive cell in each wire state (four fixtures): no change to `fr.selection`, no requests.
  4. `page.addStyleTag` setting every `--fr-seat-*` token to `#808080` on `:root` and `[data-theme]`. Then `new Set($$('.fr-seat').map(c => c.dataset.glyph)).size === 4`, and the set equals `{outline, bar, hatch, check}`.
  5. Legend: count the swatches (5). The 5th label is "Out of service".
  6. All-sold fixture: 220 `.fr-seat`, the banner text is exact, and `!/Nothing/.test(document.body.innerText)`.
  7. Change ring with `reducedMotion: 'no-preference'`:
     - Poll 1 has C-14 available. Poll 2 (after `clock.runFor(3000)`) has C-14 held.
     - Immediately afterwards, C-14 computes `outlineWidth === '2px'` and `outlineColor === token('--fr-focus-ring','color')`.
     - After `clock.runFor(899)` the outline is still present. After `runFor(2)` it is gone (`outlineStyle === 'none'`, or the `data-changed` attribute is absent).
  8. Repeat step 7 with `reducedMotion: 'reduce'`: `animationName === 'none'` while the outline holds for the same 900 ms.
- **Pass:** all of the above.
- **Mode:** MOCK.
- **Note:** the ring timer must be the screen's own `setTimeout`, so that `page.clock` drives it. CSS animation time is not faked, so assert on the attribute or the outline, not on the animation progress.

### S-BRW-13: the legend's price placeholder
- **AC→browser:** a category whose price has not arrived renders a block whose computed background equals `--fr-surface-inset`, with no "₹" in its text, and the page has no "₹0.00".
- **Pre:** MOCK seatmap with one category whose `price_paise` is absent. The app rejects a non-integer, so if a missing price can only come from the loading state, delay the seatmap response with `route.fulfill` after 2 s.
- **Steps:**
  1. Find `.fr-inset-block` inside that legend row. Its `getComputedStyle(el).backgroundColor === token('--fr-surface-inset')`.
  2. Its text does not include "₹", and `document.body.innerText` does not include "₹0.00".
  3. Run in **both** themes (§0.3).
- **Pass:** the colour matches the token in light **and** dark.
- **Mode:** MOCK.

### S-BRW-17: no layout shift while the seat map loads
- **AC→browser:** the getBoundingClientRect of the field (`.fr-field`), the screen bar (`.fr-screen-bar`) and the row gutters (`.fr-gutter`) is equal in x, y, width and height before and after the seatmap response. At both points there are 0 `[role=progressbar]` elements and 0 accessible names containing "Loading".
- **Route:** `/showtimes/{id}`.
- **Pre:** MOCK. Hold the seatmap route open on a promise and release it by hand. Run `fonts.ready` first.
- **Steps:**
  1. Go to the page with the seatmap pending. Wait for `.fr-field`. Run `document.fonts.ready`. Capture the three rect sets (all `.fr-gutter`).
  2. Check `page.getByRole('progressbar')` count is 0, and that no node in the accessibility snapshot has a name matching `/Loading/`.
  3. Release the response. Wait for 220 `.fr-seat`. Capture again and compare every number exactly.
- **Pass:** identical rects and 0 progress or loading nodes.
- **Mode:** MOCK.
- **Premium risk, real break:** `Hall3D` renders `null` while `map === null`. Once the map arrives it inserts a `<section class="fr-hall3d">` of 22–40rem height **above** `.fr-seatmap-body` (worktree `SeatMapScreen.tsx` diff). At a viewport ≥ 48rem with WebGL, every rect's **y** moves. Run this check at **375 px and 1280 px**. At 1280 px with the premium layer it is expected to **fail** until the 3D section reserves its space before the response, or this AC is re-scoped to the 2D field.

### S-PAY-13: the checkout panel's computed font size and stable height
- **AC→browser:**
  - The notice slab's computed `fontSize` is ≥ the resolved value of `--fr-text-md`.
  - The panel's `offsetHeight` is identical before and during the request.
  - Tabbing from the top of the panel reaches only the pay action and then "Back to seats".
  - The countdown text still changes while the request is in flight.
  - Pressing "Back to seats" makes 0 requests, and the Redis keys are untouched.
- **Route:** `/showtimes/7/checkout`.
- **Pre:**
  - Clock installed. `fr.hold` = F7, F8 and F9 at 30938 paise and J3 and J4 at 36666 paise, `expires_at` = now + 180 s, `total_paise: 166146`.
  - MOCK `GET /api/showtimes/7`.
  - `POST /api/bookings` is held pending.
  - The seat map has no "Continue to payment" control, so `goto` the checkout URL directly after seeding sessionStorage with `addInitScript`.
- **Steps:**
  1. Font size: `parseFloat(getComputedStyle($('.fr-notice')).fontSize) >= parseFloat(token('--fr-text-md','fontSize'))`. The token is `1rem`, so compare in px.
  2. Focus order: click the panel heading area, then press Tab repeatedly, collecting `document.activeElement` until the focus leaves `.fr-checkout`. The list is exactly `[payButton, backButton]`.
  3. Height: `h0 = $('.fr-checkout').offsetHeight` after `fonts.ready`. Click pay. The label changes to "Confirming…". `h1 = offsetHeight` must equal `h0`.
  4. Read the countdown text, run `clock.runFor(1000)`, read it again: the two differ.
  5. Back to seats: on a fresh load, clicking "Back to seats" adds 0 entries to the request log, and `location.pathname === '/showtimes/7'`.
- **REAL add-on for Redis:**
  1. Take a real hold through the API as customer-01.
  2. Before the press: `EXISTS`, `GET` and `PTTL` on `lock:seat:7:<seat>` for all five seats.
  3. Press "Back to seats".
  4. Repeat: EXISTS is still 1, GET returns the same token, and PTTL is > 0 and ≤ the value before.
- **Pass:** all of the above.
- **Mode:** MOCK, plus REAL for the Redis clause.
- **Note:** the busy label in code is `"Confirming…"` (U+2026, `checkout.ts:139`) while the AC says `'Confirming...'`. Assert what the PRD publishes and raise the mismatch if they differ.

### S-PAY-14: checkout endings that need a clock and a live region
- **AC→browser:**
  - At 0:00 with no confirm in flight: the pay action is disabled and labelled "Hold expired". The zero-state text appears **exactly once** in an `aria-live="polite"` region. The route moves to the seat map with the selection re-applied only after **5000 ms**, and at 4999 ms the route is unchanged.
  - At 0:00 with a confirm in flight: no route change, no return timer, and the fetch's `AbortSignal` never fires.
  - The 409 `IDEMPOTENCY_IN_FLIGHT` retry happens 3 times and keeps the same key.
  - The error banner is inside an `aria-live="assertive"` region and contains 0 controls.
- **Route:** `/showtimes/7/checkout`.
- **Pre:** clock installed, `reducedMotion: 'reduce'`, `fr.hold` with `expires_at` = T. The `__live` observer is registered.
- **Steps:**
  1. `clock.setFixedTime(T)` and then `runFor(0)`. Assert the button is disabled and its name is "Hold expired".
  2. `__live.filter(x => x.live === 'polite' && x.text.includes(<zero-state text>)).length === 1`.
  3. `clock.runFor(4999)` → `location.pathname === '/showtimes/7/checkout'`. `runFor(1)` → `'/showtimes/7'`. `fr.selection` holds the hold's seat ids.
  4. In flight: an init script wraps `fetch` to record `init.signal` and adds an `abort` listener that sets `window.__aborted = true`.
     - Press pay with the bookings response pending.
     - `clock.setFixedTime(T)` and `runFor(10000)`.
     - The path is unchanged and `__aborted !== true`.
     - Release a 201: the route goes to `/bookings/{ref}`, and the `fr.last_booking_reference` write is in `__seq` before the push.
  5. 409 in flight: stub four answers of 409 with `Retry-After: 1`.
     - Expect exactly 4 POSTs with an identical `Idempotency-Key` header.
     - The button is disabled through the third retry and enabled after the fourth, while `.fr-banner` is still present.
  6. Banners: for each code, `banner.closest('[aria-live="assertive"]')` is non-null and `banner.querySelectorAll('button,a,input').length === 0`.
- **Pass:** all of the above.
- **Mode:** MOCK.
- **Premium risk:** without `reducedMotion: 'reduce'`, the 5000 ms navigate runs inside `startViewTransition`. The pathname is still synchronous, so step 3 holds on the pathname, but a check on the seat-map heading would see the old screen for one frame.

### S-SCP-09: one responsive interface, measured at 375 px and 1280 px
- **AC→browser:**
  - At 375 px, the 220-seat map container has `scrollWidth > clientWidth`, and `document.body.scrollWidth === document.body.clientWidth`.
  - A seat cell computes `width: 24px` at 375 px and again at 1280 px.
- **Route:** `/showtimes/{screen-6 showtime}`.
- **Pre:** MOCK F220 (11 × 20). Viewports `{width:375,height:812}` and `{width:1280,height:800}`.
- **Steps:**
  1. For each viewport: run `fonts.ready`, then take `c = $('.fr-grid-scroll')`.
  2. Assert `c.scrollWidth > c.clientWidth` (at 375 px only), the body equality, and `getComputedStyle($('.fr-seat')).width === '24px'`. Also check that the width equals `token('--fr-seat-size','width')`.
- **Pass:** all hold at both widths.
- **Mode:** MOCK.

### S-SCP-10: the Language control, html lang and the nav names
- **AC→browser:**
  - Changing the listing's Language control issues `GET /api/movies?…language_id=…`.
  - `document.documentElement.lang` is byte-identical before and after.
  - The accessible names of every link inside the navigation landmark are byte-identical before and after.
  - `/upcoming` and `/coming-soon` render the 404 view.
  - The shell's accessibility tree has no control named like `/language|locale|translate|coming soon|pre-sale|notify me|recommend|for you/i`.
- **Route:** `/`, `/upcoming`, `/coming-soon`.
- **Pre:** MOCK `GET /api/reference` with languages, and `GET /api/movies`. Run once as a guest and once signed in (MOCK `/api/me` or a cookie), because the nav differs by role.
- **Steps:**
  1. `before = { lang: document.documentElement.lang, nav: getByRole('navigation').getByRole('link').allInnerTexts() }`. Use accessible names from the accessibility snapshot, not innerText.
  2. `selectOption` on the Language control. Wait for the request where the path is `/api/movies` and `searchParams.has('language_id')`.
  3. `after` equals `before`, both sides JSON-stringified.
  4. Walk `accessibility.snapshot()` for roles in {button, link, combobox, menuitem, tab, switch, checkbox, radio, option}: no name matches the regex. **Caveat:** the Language **filter** control is itself named "Language". The AC's regex matches it, so either the walk scopes to the shell (header, nav and footer, not `main`) or this is an AC defect to raise. Record which.
  5. `/upcoming` and `/coming-soon` both show the 404 view's heading.
- **Pass:** all of the above.
- **Mode:** MOCK. The `published_at DESC, id DESC` order, anonymous vs signed in, is API-level, so do it in pytest.

### S-SEA-01: the computed fill, border and mark of each of the four states
- **AC→browser:**
  - **Available:** fill `--fr-seat-available` with the outline mark.
  - **Sold:** fill `--fr-seat-sold` with the hatch mark.
  - **Held by someone else:** fill `--fr-seat-held-other` with the bar mark and **no border**.
  - **Held by you:** fill `--fr-seat-mine` with a **2px** `--fr-seat-edge-mine` border and the check mark. A seat in `fr.selection` but in no hold gets the same treatment.
  - **Inactive:** no fill, a **1px dashed `--fr-rule`** border, and a number in `--fr-ink-muted`.
  - The map is exactly 1 tab stop.
- **Route:** `/showtimes/77`.
- **Pre:** MOCK 77 with seat 402 `held`, three variants:
  - (a) no `fr.hold`;
  - (b) `fr.hold` containing 402;
  - (c) `fr.selection` containing 402 and no hold.
  - Plus one seat of each wire state and an inactive seat.
- **Steps:**
  1. For each cell: `bg = getComputedStyle(cell).backgroundColor`. Sold paints a gradient over the token, so for sold read `backgroundImage` as well. Compare `bg` to `token(<state token>)`.
  2. Held-other: `borderTopStyle === 'none' || borderTopWidth === '0px'`.
  3. Held by you, in (b) and (c): `borderTopWidth === '2px'` and `borderTopColor === token('--fr-seat-edge-mine','borderTopColor')`.
  4. Inactive: `backgroundColor === 'rgba(0, 0, 0, 0)'`, `borderTopStyle 'dashed'`, `borderTopWidth '1px'`, `borderTopColor === token('--fr-rule','borderTopColor')`, and the `.fr-seat-num` color equals `token('--fr-ink-muted','color')`.
  5. `new Set(cells.map(c => bg + '|' + c.dataset.glyph)).size === 4`.
  6. Tab stops: `tabbables(map).length === 1`.
  7. Run in **both themes**.
- **Pass:** every computed value equals its token in both themes.
- **Mode:** MOCK.
- **Premium note:** dark is now the default, so a run that never sets `data-theme` covers dark only.

### S-SEA-02: taps, the storage writes and spies, reload and unload
- **AC→browser:**
  - Tapping C12 adds it to the selection and `fr.selection` with **0 requests**; tapping again removes it.
  - Tapping a sold, held-other or inactive seat changes nothing.
  - An 11th tap is refused, and the note reads "Up to 10 seats.".
  - Reload restores and re-checks.
  - `fr.selection` is deleted when it empties.
  - `fr.pending_selection` is null after each case.
  - Closing the tab makes 0 requests.
  - Redis has no `lock:seat:7:*`.
- **Route:** `/showtimes/7`, signed in.
- **Pre:** MOCK 7 with poll responses at the same payload.
- **Steps:**
  1. `log.length = 0` after the first seatmap response. Exclude poll GETs from the count by filtering out the `GET /api/showtimes/7/seatmap` path.
  2. Click C12 and assert `fr.selection`. Click it again and assert the key is removed.
  3. Click sold, held-other and inactive seats: no change.
  4. Click 10 available seats and then an 11th: the selection size stays 10, and `.fr-cap-note` text is "Up to 10 seats.".
  5. After each case, `sessionStorage.getItem('fr.pending_selection') === null`.
  6. Reload with a fixture where one chosen seat is now sold: the restore re-checks and drops it.
  7. Unload: run `page.close({ runBeforeUnload: true })` from a context with the request log on. Assert no request between the close and the context close, and no `navigator.sendBeacon` call (wrapped).
- **REAL add-on:** after the close, `redis-cli KEYS 'lock:seat:7:*'` returns empty. Use a seeded showtime and replace 7 with its id.
- **Pass:** all of the above.
- **Mode:** MOCK, plus REAL for Redis.

### S-SEA-03: the total renders in `--fr-font-mono`
- **AC→browser:** the total figure's computed `fontFamily` equals the resolved `--fr-font-mono`.
- **Steps:**
  1. Select seats so that `.fr-total` renders.
  2. `getComputedStyle($('.fr-total')).fontFamily === token('--fr-font-mono','fontFamily')`.
- **Pass:** equal.
- **Mode:** MOCK.
- **Premium risk:** the premium tokens change `--fr-font-mono` to `"JetBrains Mono", ui-monospace, …`. Any check that compares against the literal old system stack breaks, so compare against the resolved token only.

### S-SEA-04: the "no longer available" banner
- **AC→browser:**
  - The banner text is exactly "C12 is no longer available. It has been removed from your choices."
  - **Exactly one** text insertion into the `aria-live=assertive` element.
  - Exactly one control in the banner: role button, label "Dismiss", accessible name "Dismiss this message". Activating it takes the banner count from 1 to 0.
  - A `SEAT_UNAVAILABLE` banner has 0 controls and clears on the next selection change.
  - With the banner showing, a focused cell's rect is fully inside the viewport.
  - Two seats gone in one re-check → one banner.
  - The selection drops that seat, the total drops by its `price_paise`, and there are 0 requests beyond the map fetch.
- **Route:** `/showtimes/{id}`.
- **Pre:** MOCK. Poll 1 has C12 available and chosen. Poll 2 (`clock.runFor(3000)`) has C12 `held`. `__live` is registered.
- **Steps:**
  1. After poll 2: `__live.filter(x => x.live === 'assertive' && x.text.includes('C12 is no longer available')).length === 1`.
  2. `banner.querySelectorAll('button,a,[role=button]').length === 1`, and `getByRole('button', { name: 'Dismiss this message' })` has text "Dismiss".
  3. `$$('.fr-banner').length` is 1. Click Dismiss. It is now 0.
  4. Viewport check:
     - Use `setViewportSize({ width: 375, height: 600 })`, then focus a cell in the last row by pressing ArrowDown inside the map.
     - Trigger the banner.
     - The cell's rect is fully inside the viewport (`r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth`).
  5. Two seats gone: one `.fr-banner`.
  6. `SEAT_UNAVAILABLE` (a 409 from POST holds): 0 controls in its banner. The next seat click removes it.
- **Pass:** all of the above.
- **Mode:** MOCK.
- **Caveat:** `SeatMapScreen.tsx:270/278` mounts the `aria-live="assertive"` element **together with** its text. The insertion count will pass, but some screen readers do not announce a live region that arrives already filled. One manual NVDA or VoiceOver pass is advised before calling this AT-proven.

### S-SEA-10: the guest's primary action, no hold on return
- **AC→browser:**
  - Pressing "Sign in to hold these seats" writes the selection and opens sign-in with 0 hold requests.
  - On return the action reads "Hold these seats", the selection is restored and re-checked, and **no hold** exists until it is pressed.
- **Steps:** the same as S-ACC-14 steps 1–7, on showtime 77.
- **REAL add-on:** `redis-cli KEYS 'lock:seat:<id>:*'` is empty after the return and before the press. After the press it is non-empty.
- **Pass:** 0 POST holds before the press, and an empty KEYS result before the press.
- **Mode:** MOCK, plus REAL for Redis.
- **Still blocked by:** the guest handler is unbuilt (the S-ACC-14 seat-map half). The router-level 401 and the manager/admin 201 are pytest.

### S-SEA-12: a seat lost to a hold is repainted held-other, not sold
- **AC→browser:** after a 409 `SEAT_UNAVAILABLE` naming C12 and C13, each named cell computes the fill `--fr-seat-held-other` with `data-glyph=bar` and a name ending "held by someone else". It is never `--fr-seat-sold`, `hatch` or "sold". The other chosen seats stay in `fr.selection`.
- **Pre:** MOCK. Five chosen seats. `POST /api/showtimes/{id}/holds` returns 409 `{error:{code:'SEAT_UNAVAILABLE', message:…, details:{unavailable_seats:['C12','C13']}}}`.
- **Steps:**
  1. Press "Hold these seats".
  2. For C12 and C13: `backgroundColor === token('--fr-seat-held-other')` and `!== token('--fr-seat-sold')`, `dataset.glyph === 'bar'`, and the name matches `/held by someone else$/`.
  3. `fr.selection` contains the other three ids.
  4. Replace `message` with `"zzz"` and repeat: the same cell state.
- **Pass:** all of the above, in both themes.
- **Mode:** MOCK. The server sentences are already covered by pytest.

### S-SEA-14: the countdown's live region, urgent colours, storage and resume
- **AC→browser:**
  - At `now = expires_at − 60 s`: the text "1:00", the warning line, the bar and digits switch to `--fr-countdown-urgent`, and **exactly one** insertion into `aria-live=polite`.
  - The digits have no `[aria-live]` ancestor.
  - The label is `TIME LEFT`.
  - `localStorage.length === 0`.
  - After a reload, `GET /api/holds/{token}` gives the same `expires_at` and the countdown resumes.
  - At 0:00 the cells are not repainted until the next poll.
  - With a confirm in flight at 0:00: the "waiting for the answer" line, and no abort.
  - Closing the tab makes 0 requests and Redis `EXISTS` stays 1.
- **Route:** `/showtimes/{id}` with a hold, and `/showtimes/{id}/checkout`.
- **Pre:** clock installed at `expires_at − 75 s`. `fr.hold` is set. MOCK `GET /api/holds/{token}`.
- **Steps:**
  1. Read `.fr-countdown-digits` → "1:15". `runFor(15000)` → "1:00". The warning line text is present.
  2. `getComputedStyle(digits).color === token('--fr-countdown-urgent','color')`, and the bar's `backgroundColor` matches the same token.
  3. `__live.filter(x => x.live === 'polite' && x.text.includes('Less than a minute left')).length === 1`, and it is still 1 after a further `runFor(5000)`.
  4. `digits.closest('[aria-live]') === null`.
  5. `localStorage.length === 0`.
  6. `runFor(60000)`:
     - The text is "0:00", never negative.
     - The pay action is disabled.
     - The ended line shows.
     - The held cells still have `data-visual=held_by_me` and `backgroundColor === token('--fr-seat-mine')` until the next poll payload is released.
  7. Reload with the clock at `expires_at − 30 s`: the countdown reads "0:30" from the GET's `expires_at`.
  8. In flight at 0:00: the abort spy from S-PAY-14 step 4, and the text "Your hold has ended. We are waiting for the answer to your payment. Do not close this page."
  9. Unload: as S-SEA-02 step 7.
- **REAL add-on:**
  - `EXISTS lock:seat:<id>:<seat>` returns 1 after the tab closes.
  - Resume against a real `GET /api/holds/{token}`.
- **Pass:** all of the above, with the urgent colours checked in both themes.
- **Mode:** MOCK, plus REAL for Redis and resume.

### S-SEA-20: the state-machine clauses that are only observable in a browser
- **AC→browser:**
  - SIGN_OUT from `held_by_me`: the key is nil, and sessionStorage has zero `fr.` keys.
  - TAB_CLOSED from `held_by_me`: 0 requests (unload spy), and the key is present with a PTTL that has not increased.
  - The rendered cells for `held_by_me_paying` and `held_by_me` are byte-identical.
- **Steps:**
  1. **REAL.** Hold seat 402 on a seeded showtime as customer-01.
  2. SIGN_OUT: click "Sign out". Then `redis GET lock:seat:<id>:402` is nil and `Object.keys(sessionStorage).filter(k => k.startsWith('fr.')).length === 0`. The hold must be released by the server-side logout; verify which component does it.
  3. TAB_CLOSED: hold again, read PTTL `p0`, close the page with `runBeforeUnload`. 0 requests. Read PTTL `p1`: `0 < p1 <= p0` and `p0 - p1 < 1000 + elapsed`.
  4. DOM comparison, **MOCK**:
     - Capture `cell402.outerHTML` with the hold live.
     - Press pay with `POST /api/bookings` pending, which gives `held_by_me_paying`.
     - Capture again on the seat map. The checkout is a separate route, so this needs the seat map visible while a confirm is in flight.
     - Assert the strings are identical.
- **Pass:** all of the above.
- **Mode:** REAL for steps 2–3, MOCK for step 4.
- **Still blocked by:** the PAY-dependent transition rows, and the seat map having **no confirm-in-flight state**. Step 4 cannot run until a confirm can be in flight while the map is mounted. Today the confirm lives on `/showtimes/{id}/checkout`.

### S-SEA-21: a residual lock on a sold seat renders sold
- **AC→browser:** seat 402's cell computes the fill `--fr-seat-sold`, `data-glyph=hatch`, **no border**, and a name ending "sold", and there is no banner element. Seat 402's own `outerHTML` is byte-identical when rendered from the payload taken with the residual lock and from the one taken without it.
- **Steps:**
  1. MOCK both payloads. They are identical on the wire by design, so the REAL variant is the meaningful one: create the booking row and a residual `SET lock:seat:<id>:402 …`, fetch, render, then delete the lock and fetch again.
  2. Compare `outerHTML`.
  3. `backgroundColor` (the base layer under the hatch) equals `token('--fr-seat-sold')`, and `borderTopWidth === '0px'` or the style is `none`.
  4. `$$('.fr-banner').length === 0`.
- **Pass:** all of the above, in both themes.
- **Mode:** MOCK, plus REAL.

### S-TKT-04: the confirmation page's focus, tab order, clipboard and live region
- **AC→browser:**
  - Focus is on the h1 after arrival.
  - The tab order is heading → reference → copy control → facts → resend control.
  - The copy control writes `FR-ACDE-FHJD` to the clipboard and announces "Reference copied." in a live region.
  - The reference's accessible name is `F R, A C D E, F H J D`.
  - With no navigation state, 0 occurrences of "on its way", "has been sent", "was sent" and "delayed".
  - In the loading state the reference textContent has length 0.
- **Route:** `/bookings/FR-ACDE-FHJD`.
- **Pre:**
  - MOCK `GET /api/bookings/by-reference/FR-ACDE-FHJD` or `GET /api/me/bookings/FR-ACDE-FHJD`. Check which one `ConfirmationScreen` calls.
  - Use `context.grantPermissions(['clipboard-read','clipboard-write'])`.
  - Navigation state: arrive by `navigate()` from a page that set it, or seed `history.replaceState(state)` before render. Check how `arrival.ts` reads it.
- **Steps:**
  1. After arrival: `document.activeElement.tagName === 'H1'` with the text "Your booking is confirmed.".
  2. Press Tab four times and collect `activeElement` each time: [reference element (if it is focusable as the AC implies), copy button, facts (if focusable), resend button]. Compare with the AC order.
  3. **Note:** a `<dl>` of facts is not focusable by default. If the AC means the reading order, assert DOM order instead and raise it.
  4. Click copy: `navigator.clipboard.readText() === 'FR-ACDE-FHJD'`, and `__live` records "Reference copied." in an `[aria-live]` region (`.fr-ref-copied`).
  5. The reference's accessible name from the snapshot is exact.
  6. With no state: a regex sweep over `document.body.textContent`.
  7. Loading: hold the GET pending; `$('.fr-ref').textContent.length === 0`.
- **Pass:** all of the above.
- **Mode:** MOCK.

### S-XCT-38: the seat map is one tab stop; per-route keyboard reach; contrast in a real browser
- **AC→browser:**
  - Tab from the element before the map enters it once, and the next Tab leaves it, never 220 stops.
  - The map has exactly one `tabindex="0"`.
  - Every element with an onClick handler is in the tab sequence on every route.
  - The four states are told apart by accessible name and mark.
- **Route:** every route in §2.
- **Steps:**
  1. On `/showtimes/{id}`:
     - Find `pred`, the tabbable immediately before the map's single `tabindex=0` cell in document tab order. **Compute this dynamically**, because the premium layer inserts four Hall3D buttons before the map.
     - Focus `pred` and press Tab: `activeElement` is inside `.fr-grid` and is the `tabindex=0` cell.
     - Tab again: `activeElement` is outside `.fr-grid`.
     - `$$('.fr-grid [tabindex="0"]').length === 1`.
  2. For each route, collect the elements that carry click listeners. Use CDP `DOMDebugger.getEventListeners` per node, or React props from `__reactProps$*` keys. Tab through the page from `body` until focus wraps, and assert every click-bearing element was reached. **Record which detection method was used.**
  3. Contrast: CONTRAST.md is generated from tokens. A browser pass should also sample the real text-on-ground pairs that tokens do not cover (see risk P-6).
- **Pass:** steps 1 and 2.
- **Mode:** MOCK.
- **Premium risk:** see P-5 and P-6.

### S-XCT-39: the 375 px phone geometry
- **AC→browser:**
  - At 375 px: computed `--fr-seat-size` 24px and `--fr-seat-gap` 4px.
  - `document.body.scrollWidth <= 375` on **every route**.
  - The visible strip is 283 px, which shows 10 of 20 columns.
  - The row is 556 px wide, so 273 px is hidden.
  - On first paint `scrollLeft === 0`.
  - Focusing column 11 from column 10 changes `scrollLeft` by exactly **21**, with no transition longer than 200 ms and the body's `scrollLeft` unchanged.
  - A restored selection scrolls to the first restored seat, and a 409 with `unavailable_seats` scrolls to the first named seat. Both use the same minimum movement.
  - The container's computed `scroll-padding-inline-start` equals `var(--fr-seat-gutter)`, which is 28px.
  - A poll leaves `scrollLeft` unchanged.
  - Each poster slot's `aspect-ratio` is `2 / 3`, and its container's `offsetHeight` is the same before and after the image loads.
- **Pre:** MOCK F220 (11 × 20). Viewport `{ width: 375, height: 812 }`. `fonts.ready`.
- **Steps:**
  1. `c = $('.fr-grid-scroll')`. `strip = c.clientWidth - 28`, which should be 283. Columns shown: `Math.floor((strip + 4) / 28)`, which should be 10. Row width `$('.fr-grid-row').scrollWidth - 28`, or the cells' span, should be 556. Hidden: `556 - strip`, which should be 273.
  2. `c.scrollLeft === 0`.
  3. Focus column 10 with ArrowRight from column 1. Read `s0`. Press ArrowRight. Read `s1`. `s1 - s0 === 21`.
     - Check that `getComputedStyle(c).scrollBehavior` is not `smooth`, or that any transition is ≤ 200 ms. Read after `waitForTimeout(250)` without the fake clock: scroll is not timer-driven.
     - `document.scrollingElement.scrollLeft === 0`.
  4. `getComputedStyle(c).scrollPaddingInlineStart === '28px'`.
  5. `runFor(3000)` for a poll: `scrollLeft` is unchanged.
  6. Restore: seed `fr.selection` with a column-15 seat, reload, and assert the minimum-movement scrollLeft. The same for a 409 naming a column-15 seat.
  7. Every route in §2: `document.body.scrollWidth <= 375`.
  8. On `/` and `/movies/{id}`: every `.fr-poster` has `aspectRatio === '2 / 3'`. `offsetHeight` before the img loads (the poster route held pending) equals the value after (released).
- **Pass:** all four numbers are exact (283, 10, 556, 273), the delta is 21, and steps 4–8 hold.
- **Mode:** MOCK.
- **Premium risk, real break:** see P-1. Under the premium layer the strip is not 283 px.

---

## 2. Route list for the every-route sweeps (S-XCT-38, S-XCT-39)

| Group | Routes | Signed in as |
|---|---|---|
| Public | `/`, `/movies/:id`, `/showtimes/:id` | guest |
| Account | `/sign-in`, `/register`, `/account/reset`, `/account/reset/confirm` | guest |
| Booking | `/showtimes/:id/checkout`, `/bookings`, `/bookings/:ref` | customer |
| Admin | `/admin`, `/admin/movies`, `/admin/movies/new`, `/admin/movies/:id`, `/admin/lookups`, `/admin/venue`, `/admin/halls`, `/admin/seat-categories`, `/admin/showtimes`, `/admin/managers` | admin |
| Reports | `/dashboard`, `/dashboard/audit` (lane p8-reports, in flight) | manager |
| Not found | `/upcoming`, plus one unknown path | guest |

Re-collect this list from `features/*/routes.tsx` when you run the checks: batch 2 is adding routes now.

---

## 3. Premium layer: risk register

**Where it is.** The premium layer (FR-ADR-074, CR-001) is **not** in `frontrow_aws` HEAD (`8436011`) or in its working tree. Main still has `--fr-page-max: 44rem`, no `premium.css` and no `data-theme` on `<html>`.
- It lives on branch **`worktree-agent-a4aed4da5dccf7ca1`** (`.claude/worktrees/agent-a4aed4da5dccf7ca1`), in commits `d84f852`, `89ad0cb` and `16e9335`.
- It adds:
  - `premium.css`, loaded last;
  - `data-theme="dark"` in `index.html`;
  - `--fr-page-max: 90rem`;
  - Inter Tight and JetBrains Mono fonts;
  - the `Hall3D` WebGL section on the seat page (at least 48rem wide);
  - View Transitions in `navigate()`.
- **Run every check in §1 against both builds,** main and premium. A check that passes on main can still break once premium merges.

**Light theme and 44rem.** No AC in the ledger asserts a light-theme hex value or the 44rem width.
- A grep of AcceptanceCriteria and StatusNote found 0 hits for `44rem`, `page-max`, `--fr-measure`, `data-theme` and `prefers-color-scheme`.
- The only theme clause is S-XCT-38's "in both themes".
- Every colour AC names a **token**, so the risk is in how a check is written, not in the AC. Resolve the token in the active theme (§0.4) and never compare to a literal hex or rgb copied from light mode.

| # | Rows | What the premium layer changes | Effect on the AC | Severity |
|---|---|---|---|---|
| P-1 | **S-XCT-39** | `.fr-field { padding: var(--fr-space-5) }` (24px, up from 16px) and a new 1px `--fr-rule-quiet` border. | At 375 px the strip is 375 − 32 − 48 − 2 − 28 = **265 px**, not 283. That gives 9 columns, not 10, and 291 px hidden, not 273. Column 10 (x 252–276) is already off-strip, so the "column 10 → 11 = +21" step starts mid-scroll and its delta is no longer 21. **Four of the AC's numbers fail.** | **High, real break** |
| P-2 | **S-BRW-17** | `Hall3D` returns `null` until the map arrives, then mounts a 22–40rem section above `.fr-seatmap-body` (viewport ≥ 48rem, WebGL present). | The y-coordinate of the field, screen bar and gutters moves between before and after. The check fails at desktop width, and passes at 375 px only because the 3D section does not mount there. | **High, real break** |
| P-3 | S-PAY-14, S-ACC-14, S-TKT-04, every route assertion | `navigate()` → `document.startViewTransition(flushSync(...))` unless reduced motion is on. | `location.pathname` changes synchronously, but the new screen paints one frame later. The 4999/5000 ms check passes on the pathname but can flake on rendered content. Use `reducedMotion: 'reduce'`, or assert on the pathname. | Medium (how the check is written) |
| P-4 | S-SEA-03 (and any `fontFamily` assertion) | `--fr-font-mono` → `"JetBrains Mono", ui-monospace, …`. Body and display become Inter Tight. | A check that compares against the old system-stack literal fails. Geometry (S-BRW-17, S-PAY-13 `offsetHeight`, S-XCT-39, S-SEA-04) reflows when the fonts load, so run `document.fonts.ready` before measuring. | Medium |
| P-5 | **S-XCT-38** (tab walk), S-SEA-01 (one tab stop) | Hall3D adds 4 buttons ("Hall overview", "View from my seat", "From the screen", "Use the 2D map only") before the map. The r3f `<canvas>` attaches native pointer listeners inside an `aria-hidden` stage. | "The element before the map" is now a Hall3D button: compute it dynamically. A listener-based (CDP) walk of "every onClick element is tabbable" **will find the canvas** and fail, because it is not focusable. A React-props walk will not see it. Record which method was used. The 2D map stays the keyboard path. | Medium to high |
| P-6 | **S-XCT-38** (contrast, "both themes") | New text-on-ground pairs that CONTRAST.md does not cover: (a) `.fr-hall3d-modes .fr-choice[aria-pressed=true]` paints `--fr-screen-ink` on `--fr-surface-notice`. In **light** that is `#0B5A6E` on `#16212B`, about **2.1:1**, under 4.5:1 (computed here by hand; confirm with contrast.py). In dark, `#6ED4EA` on `#16212B` passes. (b) Text over `color-mix()` grounds: the checkout panel is 92% `--fr-surface-raised` over a glow with `backdrop-filter`; `.fr-movie-head` uses a glow-to-inset gradient; the body has a radial `--fr-screen-glow`; `.fr-hall3d-name` and `.fr-hall3d-caption` sit at 88% base over the WebGL canvas. (c) `.fr-nav a` and `.fr-movie-synopsis` change to `--fr-ink-muted`. | contrast.py only proves token pairs, so these rendered grounds are unmeasured. (a) is a likely **AA failure in light theme**. Light is now reachable only by setting `data-theme="light"`, because `index.html` forces dark and there is no theme toggle, but the AC asks for both. | **High for (a)**, medium for (b) and (c) |
| P-7 | S-SEA-01, S-SEA-12, S-SEA-14, S-SEA-21, S-BRW-13, S-BRW-12 | Dark is the default (`<html data-theme="dark">`). | A computed-colour check written without setting the theme covers dark only. `emulateMedia({colorScheme:'light'})` does nothing against `data-theme="dark"`. Run each colour check twice and set `data-theme` explicitly. | Medium (how the check is written) |
| P-8 | S-SCP-09, S-XCT-39 (every route ≤ 375 px) | `--fr-page-max: 90rem`. New minimum widths: `.fr-cards` `minmax(min(100%,17.5rem))`, `.fr-times` `minmax(13rem)`, `.admin-list` `minmax(16rem)`, `.fr-ticket-facts` `minmax(14rem)`, `.fr-booking-row` `minmax(10rem)`. | The 90rem limit only matters above 1440 px, so the AC's 1280 px clause is unaffected. Every `minmax` floor is under the 343 px content box at 375 px, so no overflow is expected, but S-XCT-39's every-route sweep is the proof. Admin tables (`.admin table`, width 100%) can overflow with long cells; check `/admin/showtimes` and `/admin/managers` at 375 px. | Low to medium |
| P-9 | S-ACC-15 | The seat page at ≥ 48rem lazy-loads three.js plus `seat_standard.glb` (100 KB), `seat_premium.glb` (361 KB) and `seat_recliner.glb` (2.5 MB). | Adds time and main-thread load inside t0→t1 at desktop width. t0 itself is unaffected (the stage is `aria-hidden`). Pin the viewport and report it next to the three lines. | Low to medium |
| P-10 | S-TKT-04 | `h1[tabindex="-1"]:focus { outline: none }` | Focus on the h1 is still asserted through `document.activeElement`. There is no AC on its ring. No break. | None |
| P-11 | S-SCP-15 (appendix) | Hall3D renders a `<canvas>`, on the seat page only. | The confirmation and booking pages have no canvas, so the S-SCP-15 check is unaffected. Keep its page scope exact. | None |

---

## 4. What needs the real backend

| Needs REAL | Rows and clauses |
|---|---|
| Redis `KEYS`, `EXISTS`, `GET` or `PTTL` | S-PAY-13 (Back to seats), S-SEA-02 (`lock:seat:7:*` empty), S-SEA-10 (no auto hold), S-SEA-14 (EXISTS after the tab closes), S-SEA-20 (SIGN_OUT and TAB_CLOSED), S-SEA-21 (residual lock) |
| The running app's config | S-ACC-15 (`PAYMENT_SIMULATED_DELAY_MS` > 0) |
| A whole booking flow | S-ACC-15 (20 + 20 runs, a real 409 `HOLD_EXPIRED`) |
| A real resume | S-SEA-14 (`GET /api/holds/{token}` after a reload) |
| **MOCK is enough** | All DOM, CSS, focus, keyboard, live-region, clock and geometry clauses: S-ACC-14, S-BRW-02, S-BRW-07, S-BRW-11, S-BRW-12, S-BRW-13, S-BRW-17, S-PAY-13 (except Redis), S-PAY-14, S-SCP-09, S-SCP-10, S-SEA-01, S-SEA-03, S-SEA-04, S-SEA-12, S-SEA-20 (DOM comparison), S-TKT-04, S-XCT-38, S-XCT-39 |
| **Not browser work** (pytest) | S-BRW-07 (byte-identical body, expired-token reads), S-SCP-10 (id order), S-SEA-10 (router 401, manager/admin 201), S-SEA-12 (server sentences) |

**Blocked before any browser run, because a feature is missing:**
- S-ACC-14 and S-SEA-10: the guest exit to sign-in and the restore are unbuilt.
- S-ACC-15: depends on S-ACC-14, plus there is no "Continue to payment" control on the seat map.
- S-SEA-20 step 4: the seat map has no confirm-in-flight state.

## Appendix: frontend-DOM rows the node render harness can close (no browser)
- **S-SCP-15:** the svg, canvas and img checks on the confirmation and booking pages, and the BOOKING REFERENCE regex. These are static DOM. `frontend/src/test/render.mjs` can do them.
- **S-TKT-12 (b):** SCR-TKT-01 renders the entrance line. Static DOM.
- **S-TKT-13:** the SCR-TKT-01 DOM comparison between sent and failed. Static DOM.
