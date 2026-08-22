# ADMIN_JOURNEY — the admin's walks

```
Lane .............. ADMIN (GOAL_06, one of five lanes walked independently)
Date .............. 2026-08-22
Sections read ..... docs/03 PRD/sections/S1_reading_rules.md (full)
                    docs/03 PRD/sections/S3_personas_surfaces.md (full)
                    docs/03 PRD/sections/E6_admin.md (full: S4 P-ADM-01..26, S5 SCR-ADM-01..08,
                      S6 the Films / Showtimes / Seat / Manager endpoint blocks, the eight
                      newerrorcode blocks, and the Lane notes)
                    docs/03 PRD/sections/E8_crosscutting.md (targeted: P-XCT-03 audit,
                      P-XCT-04, P-XCT-07 rate limits, P-XCT-14 alarms, P-XCT-30 the seed)
                    docs/03 PRD/sections/E7_dashboard.md (targeted: P-RPT-11 the change log)
                    docs/03 PRD/sections/E1_browse.md (targeted: P-BRW-01, EP-BRW-05's
                      authorisation rule, PROPOSED-BRWVIS-01)
                    CONSTITUTION.md Article X (open-row ids only, read-only)
Defects filed ..... 16, in defects_admin.tsv
Steps walked ...... 53 across 8 walks — 38 system, 11 page, 4 time, 0 process
```

> **Nothing in this document decides an open question.** Where the walk reaches a point the frozen
> sources, the client's rulings, an `APPROVED` record and the PRD cannot answer, the walk says so and
> stops. Six of the eight walks end at an open Article X row and none of them is filled in.

**One structural fact about this lane, stated because its absence looks like an omission.** The admin
lane crosses **no `process` seam at all.** Nothing an admin does is asynchronous: there is no worker
job, no queue message and no scheduled anything behind any admin write (`P-XCT-22`, `SRC-002 §E E-4`).
Every admin write is one HTTP request and one database transaction. The only asynchronous work in the
product is the receipt send, which belongs to the customer's path. **Zero is the correct count here,
not a gap in the walking.**

---

## Walk 1 — Creates a film by hand and uploads a poster

**Entering state.** A signed-in admin on a database that has been migrated and **not** seeded. This is
the harder starting state and it is the one the PRD says an admin actually meets
(`SCR-ADM-04` Empty, `SCR-ADM-05` List-empty, `SCR-ADM-07` Empty).

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-01` film list, `/admin/movies` | Signed in as admin; the list is empty and reads "No films yet. Create the first one." | Presses "New film" | `SCR-ADM-01 -> SCR-ADM-02 (/admin/movies/new)` | `page` | An empty create form. The poster panel is disabled and reads "Save this film first, then upload its poster." | `P-ADM-01` `P-ADM-18` | - |
| 2 | `SCR-ADM-02` film editor | Form open; the language, certification and genre selects are **replaced by empty-vocabulary lines**, because no lookup row exists | Follows the "Manage lists" link | `SCR-ADM-02 -> SCR-ADM-07 (/admin/lookups)`, opening on the Languages tab | `page` | The Languages vocabulary, empty, with a name field and "Add to list" | `P-ADM-23` `P-ADM-01` | - |
| 3 | `SCR-ADM-07` lists | Languages empty | Types `Hnidi` — a typo — and presses "Add to list" | `API -> Postgres: INSERT language + INSERT audit_log(language.created), one transaction` | `system` | A language row, `is_active = true`, and one audit row carrying `before = null`, `after = {"name": "Hnidi"}` | `P-ADM-23` `P-ADM-19` `P-XCT-03` | - |
| 4 | `SCR-ADM-07` lists | The typo is on the list and is offered in every film form | Presses "Withdraw", confirms | `API -> Postgres: PATCH is_active=false + INSERT audit_log(language.withdrawn), one transaction` | `system` | The entry is withdrawn, not deleted. It still participates in the unique index, so `Hnidi` cannot be re-added; the remedy is Restore, and the correction is a **second** row named `Hindi` | `P-ADM-24` `P-ADM-19` `P-ADM-20` | - |
| 5 | `SCR-ADM-02` film editor | Vocabularies now populated; title, synopsis, runtime, certification, language, genres filled | Presses "Save" | `API -> Postgres: INSERT movie (published_at NULL, poster_object_key NULL, version 1) + movie_genre rows + audit_log(movie.created), one transaction` | `system` | 201 with `id` and `version = 1`; the editor reloads at `/admin/movies/{id}` and the poster panel becomes usable | `P-ADM-01` `P-ADM-19` `P-ADM-22` | - |
| 6 | `SCR-ADM-02` poster panel | Saved draft, `version 1`. The panel states the limits **before** the file is chosen | Chooses a 1.8 MB JPEG and submits, with `version` as a second form part | `API -> S3: streamed PUT to posters/{movie_id}/{random}.jpg` | `system` | An object in a **private** bucket under a server-generated key. `Content-Length` was checked at the header; `version` was checked **before the first byte was streamed** | `P-ADM-03` `P-ADM-12` `P-XCT-07` | `J-ADM-01` |
| 7 | — (server side) | The object is in S3; nothing yet points at it | The server commits the film write | `API -> Postgres: re-read row, compare version inside the transaction, set poster_object_key, version++, INSERT audit_log(movie.poster_uploaded)` | `system` | 200 with the new `version`. The audit row's `before` and `after` carry the S3 **key**, never the bytes | `P-ADM-03` `P-ADM-19` `P-ADM-12` | - |
| 8 | — (the half-failure) | The same upload, but Postgres becomes unreachable between step 6 and step 7 | Nothing the admin can do | `S3 write committed; Postgres transaction rolled back — the two are not one transaction` | `system` | 503, "The system cannot reach its database right now. The poster was not saved against this film." An **orphan object** stays in the bucket. **No compensating delete is performed**, because deletion is not in this system's vocabulary (`FR-ADR-012`) | `P-ADM-03` `P-ADM-20` | - |
| 9 | `SCR-ADM-02` poster box | A film with a poster | The browser requests the poster | `API -> 302 -> S3: presigned GET URL, valid one hour` | `system` | The image. The bucket has no public-read policy and nothing is ever hotlinked | `P-ADM-03` | - |
| 10 | `SCR-ADM-01` film list | A tab left open for more than an hour, or S3 briefly unavailable | Nothing — the page re-renders | `the presigned URL's one-hour validity elapses` | `time` | The row renders its `--fr-poster-empty-mark` box and the words **"No poster"** — the identical rendering a draft with no poster gets | `P-ADM-03` | `J-ADM-04` |
| 11 | `SCR-ADM-02` poster panel | The bucket's 5 GB allowance is exhausted — reachable in ~2,500 uploads at the 2 MB cap, and **every replaced poster stays forever** | Uploads a poster | `API -> S3: PutObject refused, allowance exhausted` | `system` | 503, "The system cannot reach its file storage right now. The poster was not saved. Try again in a moment." — **a retry that can never succeed**, and no film can be published until it is diagnosed by hand | `P-ADM-03` `P-ADM-05` `P-XCT-14` | `J-ADM-02` `J-ADM-03` |

**What the documents do say about a full bucket, stated exactly.** `P-ADM-03` exception 12 covers "S3
rejects the write **or** is unreachable" with one 503 and one sentence. The Lane notes and
`EP-ADM-05`'s `rate_limit` entry both say the endpoint "writes to a 5 GB S3 allowance with no limiter
and no deletion" and raise it as `PROPOSED-ADMINRATE-01`, now `OPEN-ADMINRATE-01`. **What no row
says** is what the operator does when the allowance is reached, or who notices: `P-XCT-14`'s
unwatched-metrics list names RDS free storage and does not name S3.

**There is no deletion path for a poster and that is deliberate, not an oversight.** `P-ADM-20`'s
table entry for a poster object reads "not withdrawn and not deleted", and the reason is stated: an
`audit_log` `before` value must still resolve to a real image. The consequence is monotonic growth,
and it is the growth the walk above reaches.

---

## Walk 2 — Sets a display window, and it expires

**Entering state.** A saved draft with a poster, `version 3`. This walk is the required
**time-boundary** walk.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-02` window fields | Draft with a poster; both window fields empty; labels read "Shown from (India time)" / "Shown until (India time)" | Types `2026-09-04 00:00` and `2026-10-02 00:00` — **naive local, no `Z` and no offset**, which the form produces by construction | `API -> Postgres: both values converted through the cinema row's zone and stored as timestamptz UTC; audit_log(movie.display_window_changed) with both instants before and after` | `system` | `version++`; stored `2026-09-03T18:30:00Z` and `2026-10-01T18:30:00Z`. Nothing was rounded, no day was added, and neither end was derived from the other | `P-ADM-04` `P-ADM-26` `P-ADM-19` | - |
| 2 | `SCR-ADM-02` window fields | The same film; the admin wants to move only the start | Sends a `PATCH` carrying `display_from = 2026-10-15 00:00` alone | `API -> Postgres: the row is re-read inside the transaction for the version check, and the bound is evaluated against the MERGED pair, not against the submitted field` | `system` | 422, "The display window must end after it starts." **Nothing is written, including no audit row and no version increment.** Checked against the submitted field alone this passes and stores a window no instant can satisfy | `P-ADM-02` `P-ADM-04` `P-ADM-12` | - |
| 3 | `SCR-ADM-02` publish control | Poster present, window set, `version` echoed | Presses "Publish", confirms | `API -> Postgres: preconditions re-read INSIDE the transaction; published_at stamped from the injected clock; audit_log(movie.published)` | `system` | 200. The gate status block now renders **two independent lines** — publication and the window — and never collapses them into one "live" flag | `P-ADM-05` `P-ADM-19` | - |
| 4 | every customer surface, and `SCR-ADM-01` | The film is published and inside its window | **Nobody acts.** The clock reaches `2026-10-01T18:30:00Z`, which is local `2026-10-02 00:00` | `display_until is reached; the bound is EXCLUSIVE` | `time` | For the **customer**: `P-BRW-01`'s predicate goes false at that instant and the film leaves every browse listing and every filter. For the **admin**: *nothing happens at all* — no audit row, no notification, no state column, no request. `SCR-ADM-01`'s gate mark flips to "Outside its display window" only the next time somebody loads the list | `P-BRW-01` `P-ADM-04` `P-ADM-05` `P-ADM-26` | `J-ADM-05` |
| 5 | a customer's browser | The film is gone from browse; **its showtimes still have unsold seats** | Opens a showtime URL they already had, or a link from an email | `browse listing -> the booking surface (EP-BRW-05 / EP-BRW-06), whose authorisation rule states in terms that it does NOT apply the movie visibility gates` | `page` | **The documents cannot say whether that showtime keeps selling.** `FR-ADR-021` rules that the window governs the browse surface and not the booking record, which answers the *booking* half and not the *selling* half | `P-BRW-01` `P-ADM-04` | `J-ADM-05` |
| 6 | the seat map | Same instant, same showtime | Selects a seat and asks for a hold | `API -> Redis: SETNX hold token on a showtime whose film has left its display window` | `system` | **A hold, apparently.** No P-row in the hold path consults the display window — the string does not appear anywhere in `E2_seat_hold.md` — so nothing refuses it and nothing says it should | `P-ADM-04` `P-BRW-01` | `J-ADM-06` |

### `OPEN-BRWVIS-01` — recorded, not answered

> **A film leaves its display window while its showtimes still have unsold seats. Do those showtimes
> keep selling?**

**Status: `OPEN`, class `product`, filed as `PROPOSED-BRWVIS-01` by the browse lane and carried in
`CONSTITUTION.md` Article X.0b.** The browse lane's own note records that it may be a facet of
`OPEN-SHOWCANCEL-01`, which is **reserved: money**.

**What this walk can state, and it is the whole of it:**

- The browse surface hides the film. That is ruled (`P-BRW-01`, `FR-ADR-021`).
- The booking surface does not apply the gates. That is stated on `EP-BRW-05`'s authorisation rule.
- The hold path does not mention the window at all. That is an absence, verified by search, not an
  inference.
- **Therefore the three surfaces disagree and no row reconciles them.** Making the seat map answer 404
  breaks a customer mid-checkout; leaving it sellable creates a withdrawal path in all but name, and
  withdrawal is the reserved row `OPEN-SHOWCANCEL-01`.
- `SCR-ADM-02` publishes the sentence **"Its display window has ended. Customers can no longer see
  this film."** That sentence is true of browse and is not known to be true of the booking surface.

**No policy is proposed here.** The admin's remedy is unruled and the question goes to the client.

---

## Walk 3 — Creates a showtime and prices it

**Entering state.** A published film with `runtime_minutes = 148`; Screen 3 with 150 seats in service;
three seat categories.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | the admin shell | Signed in as admin | Opens Showtimes | `shell -> SCR-ADM-03 (/admin/showtimes)` | `page` | The screen, already carrying **the first hall by name** and **today's local date in Asia/Kolkata** — neither is a preference the implementer may vary, because the pair decides what the first screen anyone sees shows | `P-ADM-09` | - |
| 2 | `SCR-ADM-03` day strip | Hall and date chosen | The screen issues its first request | `API -> Postgres: EP-ADM-09, one hall for one local date resolved through the cinema row's zone, whole and unpaginated` | `system` | The day in start order, with a **gap readout in minutes between consecutive rows**. `include_past` defaults to `true`: nothing is hidden from an admin who did not ask | `P-ADM-09` `P-ADM-26` | - |
| 3 | `SCR-ADM-03` create form | The strip is loaded | Presses "New showtime", picks the film and Screen 3, types `18:30` | `day strip -> the create form` | `page` | `ends_at` prefilled at `20:58` — **start + runtime exactly, with no turnaround added** — and the prefill note saying so in words | `P-ADM-07` `P-ADM-08` | - |
| 4 | `SCR-ADM-03` create form | Times set; types `250.00` in the rupees field, which the interface converts at the boundary to `25000` paise; the price preview renders one line per category | Presses "Create showtime" | `API -> Postgres: SELECT ... FOR UPDATE on the screen row; overlap re-checked inside that lock; INSERT showtime; INSERT one showtime_seat row per in-service seat; seat_count_at_creation set from that statement's row count; audit_log(showtime.created) — all one transaction` | `system` | 201, `version 1`, `seat_count_at_creation = 150`, and **150 `showtime_seat` rows**. The showtime and its seat set become visible together or neither does | `P-ADM-07` `P-ADM-08` `P-ADM-10` `P-ADM-14` `P-ADM-19` | `J-ADM-07` |
| 5 | `SCR-ADM-04` pricing | The uplifts need changing | Opens Pricing | `SCR-ADM-03 -> SCR-ADM-04 (/admin/pricing)` | `page` | The categories, each with its uplift | `P-ADM-11` | - |
| 6 | `SCR-ADM-04` | The form is drawing | The screen loads the categories | `API -> Postgres: EP-ADM-12 returns each category plus affected_future_showtimes and evaluated_at_utc, counted at the instant of the read` | `system` | The impact line, rendered **as returned** — the interface never counts it and never renders `seat_count` in its place — and a count-as-of line so the figure has an instant attached to it | `P-ADM-11` | - |
| 7 | `SCR-ADM-04` confirmation | Premium `1250` -> `1500`; the confirmation names the category, both percentages and the count | Confirms | `API -> Postgres: version compared inside the transaction; uplift_basis_points written; audit_log(seat_category.uplift_changed) with before and after; count recomputed at the write instant` | `system` | 200. **This is the most dangerous single write in the system**: one edit changes the price of every future show in every hall | `P-ADM-11` `P-ADM-12` `P-ADM-19` | - |
| 8 | a customer's seat map | The new uplift is live | A customer holds two seats | `API -> Redis: the per-seat prices are computed once and written INTO the hold, under the hold token, alongside the seat ids and the absolute expiry` | `system` | The price the customer was shown is now a property of their hold, not of the showtime row. An admin edit after this cannot change what they are charged | `P-ADM-12` | - |
| 9 | the hold | 180 seconds from `SEAT_HOLD_TTL_SECONDS` | Nothing — the customer walks away | `the hold TTL expires; the held prices expire with it` | `time` | The price protection ends with the hold, needing no separate expiry and no cleanup job. The next hold is quoted the new uplift | `P-ADM-12` | - |

### The arithmetic, walked explicitly

**The rule** (`FR-ADR-038`, owned by `P-ADM-11`), integer throughout, no float and no `Decimal` in the
expression:

```
seat_price_paise = (base_price_paise * (10000 + uplift_basis_points) + 5000) // 10000
```

`10000` is the basis-point denominator. Adding `5000` — **half the denominator** — before an integer
floor division is integer **half-up**. Both are named constants.

**Is the worked example degenerate? No — and it was checked in both directions rather than assumed.**

```
base_price_paise = 25000  (Rs 250.00)

Standard   0 bp:  (25000 * 10000 + 5000) // 10000 = 250005000 // 10000 = 25000   Rs 250.00
Premium 1250 bp:  (25000 * 11250 + 5000) // 10000 = 281255000 // 10000 = 28125   Rs 281.25
Recliner 3333 bp: (25000 * 13333 + 5000) // 10000 = 333330000 // 10000 = 33333   Rs 333.33
```

- Standard and Premium **do** divide evenly and demonstrate nothing about rounding.
- **Recliner does not.** The exact value is `25000 x 1.3333 = 33332.5` paise — **exactly half**.
  Half-up gives `33333`; half-even would give `33332`, because 33332 is the even neighbour.
  **This is the single case where the two rules visibly disagree, and the example lands on it.**
- The rule is also exercised in the **other** direction elsewhere and I checked that too: the seed's
  base price is `24999`, and `(24999 * 13333 + 5000) // 10000 = 33331` — the exact value is
  `33331.1667`, below a half, so the `+5000` does **not** carry. Both directions are published.

**Per-seat, never per-total** (`FR-ADR-038`). Three Recliner seats:

```
per seat, then sum:      33333 * 3   = 99999 paise  ->  Rs 999.99   <- the rule
round the total instead: 33332.5 * 3 = 99997.5 -> 99998 paise ->  Rs 999.98
```

One paisa apart, and the first is the figure the customer was shown three times on the seat map.

**Verdict on this walk's assigned check: the rounding rule is stated, the worked example is
non-degenerate, and the formula is identical in all five places it appears** (`P-ADM-11`, `P-ADM-12`,
`E1 P-BRW-10`, `E2` twice). **No `blocks-code` defect on the pricing arithmetic.** That is reported as
a result of looking, not as an absence of looking. The one pricing defect found is elsewhere — the
endpoint block drops the P-row's arithmetic ceiling (`J-ADM-07`).

---

## Walk 4 — Prices something absurd

**Entering state.** The same admin, the same create form, one mistyped field. `SCR-ADM-03` says the
admin types **rupees and paise** and the interface converts at the boundary.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-03` create form | Intending ₹250.00 | Types `25000` into the rupees field — a decimal point away from the intended figure — and presses "Create showtime". **There is no confirmation step on this form**; only the uplift edit has one | `API -> Postgres: showtime created with base_price_paise = 2500000. Both bounds pass — it is >= 1, and it is nineteen orders of magnitude below the 2^63 arithmetic ceiling` | `system` | A showtime priced **a hundred times over**, created in one click, with an audit row that faithfully records the number the admin typed | `P-ADM-07` `P-ADM-10` | `J-ADM-08` |
| 2 | a customer's seat map | The showtime is live and sells like any other | Holds one Recliner seat | `API -> Redis: held price = (2500000 * 13333 + 5000) // 10000 = 3333250 paise = ₹33,332.50, written under the hold token` | `system` | A three-minute hold at ₹33,332.50 for one cinema seat. Nothing in the product questions the figure | `P-ADM-11` `P-ADM-12` | - |
| 3 | checkout | The hold is live | Pays | `API -> the SIMULATED payment provider: the held amount is captured` | `system` | A confirmed booking. `booking_seat` carries `price_paise = 3333250` plus `base_price_paise_applied` and `uplift_basis_points_applied`, **snapshotted and never recomputed**. The receipt goes out with the reference | `P-ADM-12` | - |
| 4 | `SCR-ADM-03` | The admin notices | Edits the base price back to `25000` | `API -> Postgres: PATCH base_price_paise; version++; audit_log(showtime.base_price_changed) with before 2500000 and after 25000` | `system` | The correct price **for holds acquired after the edit**. The paid booking is untouched — that is `P-ADM-12` working exactly as specified. **And there it stops:** no refund exists (`P-SCP-11`), no cancellation exists, and the showtime cannot be withdrawn (`P-ADM-21`) | `P-ADM-09` `P-ADM-12` `P-ADM-21` | `J-ADM-08` | 

### `OPEN-PRICEBOUND-01` — recorded, not answered

> **What is the highest ticket price and the highest category uplift this system accepts?**

**Status: `OPEN`, `reserved: money`, `CONSTITUTION.md` Article X.0b.** `P-ADM-10` bounds
`base_price_paise` at `>= 1` (**derived** — a payment of zero is not a payment) and at a 64-bit
arithmetic ceiling (**technical**, and marked as such). `P-ADM-11` bounds `uplift_basis_points` at
`>= 0` (**derived** — a negative uplift is a discount, and `OPEN-PRICE-02` rules discounts out) and at
the same arithmetic ceiling. **Neither has a business upper bound and none is invented here.**

**What the product does have, so the walk is not overstated:** `SCR-ADM-03` renders a price preview,
one line per seat category, computed with the server's own rule — so the mistyped figure is on screen
as `₹25,000.00` before the admin presses the control. That is a real mitigation and it is the only
one. It is not a check, it is not enforcement, and the interface is never the enforcement point.

**The two facts that make the chain irreversible, and they compound:** money is reserved, and the two
capabilities that would undo it — a refund and a showtime withdrawal — are both absent by design, the
second of them because of another open row. **A sanity ceiling is a money decision and no model may
set one.**

---

## Walk 5 — Creates a hall and lays out its seats

**Entering state.** A venue exists (it comes from the seed; there is no create endpoint). Three seat
categories exist. No hall yet.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-05` hall list, `/admin/halls` | "No halls yet. Create the first one." | Presses "New hall"; the venue select renders **even with one option**, with the venue's IANA zone beside it | `SCR-ADM-05 -> SCR-ADM-08 (/admin/venue)` if no venue exists at all; otherwise the create form opens in place | `page` | Either the venue screen, or the hall create form carrying a venue and its zone | `P-ADM-25` `P-ADM-13` | - |
| 2 | `SCR-ADM-05` create form | Venue chosen, name typed | Presses "Create hall" | `API -> Postgres: INSERT screen (cinema_id required) + audit_log(screen.created)` | `system` | A hall with no seats. The **freeze banner** renders immediately and says the layout can be changed freely and that the first showtime fixes it permanently | `P-ADM-13` `P-ADM-19` `P-ADM-25` | - |
| 3 | `SCR-ADM-05` seat editor | Empty grid, "No seats yet. Add the first row." | Submits a batch of 220 seats — `row_label`, `seat_number`, `grid_row`, `grid_col`, `seat_category_id`, every one typed by a person | `API -> Postgres: SELECT ... FOR UPDATE on the screen row; INSERT the seats; INSERT one audit_log(seat.created) row PER SEAT — 220 of them — all in the same transaction, all-or-nothing` | `system` | 220 seats, 220 audit rows, and a change log whose first page is nothing but seat creations until somebody filters | `P-ADM-13` `P-ADM-14` `P-ADM-19` | `J-ADM-10` |
| 4 | `SCR-ADM-05` seat editor | `C12` already exists on this hall | Submits a seat labelled `c12` | `API -> Postgres: the unique index on (screen_id, row_label, seat_number)` | `system` | **The documents do not agree what happens.** `P-ADM-13`'s validation table says `row_label` is *"stored uppercase"*; `EP-ADM-19` and `EP-ADM-20` say only *"1..4 letters"*; and the unique constraint is stated with **no** normalisation, unlike every other unique name in the epic, each of which states `lower(trim(name))` explicitly | `P-ADM-13` | `J-ADM-09` |
| 5 | `SCR-ADM-05` seat editor | A label was mistyped and **no showtime exists on this hall yet** | Corrects `row_label` | `API -> Postgres: PATCH seat + audit_log(seat.updated); permitted, because the domain layer counts zero showtime rows on this screen` | `system` | A corrected label. **This is the entire window in which that is possible** | `P-ADM-13` `P-ADM-14` | - |
| 6 | `SCR-ADM-03` | The hall is laid out; the admin schedules the first show | Creates a showtime on this hall | `API -> Postgres: INSERT showtime under SELECT ... FOR UPDATE on the screen row. From this commit, showtime_count on this screen is greater than zero` | `system` | **The freeze bites here, at this exact commit.** Not at the first booking, not at the first *future* showtime — **any showtime row at all**, past or future, booked or empty | `P-ADM-07` `P-ADM-14` | `J-ADM-11` |
| 7 | `SCR-ADM-05` seat editor | The same mistyped label, now after step 6 | Tries to correct it | `API -> Postgres: the domain layer counts showtime rows INSIDE the transaction; the whole request is refused and nothing is written, including no audit row` | `system` | 409 `LAYOUT_FROZEN`, "Seat C12 cannot be renumbered. This hall has showtimes, and a seat number is what a past customer's ticket says." The field renders **read-only, not merely disabled**, with the reason inline | `P-ADM-14` | - |
| 8 | `SCR-ADM-05` seat editor | The label is permanently wrong | Takes the mistyped seat out of service and adds a correctly labelled one beside it | `API -> Postgres: audit_log(seat.deactivated); then a seat insert. The retired seat STAYS on every showtime that already exists, and the new seat is absent from every one of them` | `system` | A permanently retired seat row in the hall, and a new seat that is unsellable on any showtime created before it. **There is no rename** | `P-ADM-15` `P-ADM-14` `P-ADM-16` | - |

### Where the freeze bites, stated exactly

**The state is decided by one question and one only:** *does any `showtime` row exist on this screen?*
Not "any showtime in the future". Not "any showtime with bookings". **Any showtime row at all.**

| Operation | No showtime row | One or more showtime rows |
|---|---|---|
| Change `row_label` | permitted | **409 `LAYOUT_FROZEN`** |
| Change `seat_number` | permitted | **409 `LAYOUT_FROZEN`** |
| Change `seat_category_id` | permitted | **409 `LAYOUT_FROZEN`** |
| Delete a seat | permitted (`EP-ADM-21`) | **409 `LAYOUT_FROZEN`** |
| Add a seat · change `grid_row`/`grid_col` · service toggle · rename the hall | permitted | **permitted** |

**And the practical deadline is earlier than it looks.** `P-XCT-30`'s seed creates **720 showtimes
across all six halls**. A database that has been seeded therefore has **every hall frozen** before an
admin has looked at a single seat label. No row in the PRD states that running the seed is what closes
this window (`J-ADM-11`).

### `OPEN-SEATLABEL-01` — recorded, not answered, and not normalised here

> **`row_label` is unique per screen and unnormalised, so `C12` and `c12` are two seats a person reads
> as one name.**

**Status: `OPEN`, `reserved: irreversible`, `CONSTITUTION.md` Article X.0c.** The row states its own
deadline: normalising would have to be **upper-case** rather than `lower(trim())`, so it changes what
is **stored**; and `P-ADM-14` freezes `row_label` once a showtime exists, so **a rule applied later
cannot correct a row already written.**

**What this walk adds to the row rather than repeating it:** the PRD is not merely silent, it is
**internally inconsistent**. One validation table says the value is stored uppercase; the two endpoint
blocks that actually accept the field say nothing of the kind; and under `S1.2` the endpoint block
outranks the P-row on a field bound, because `api/contract.json` is generated from the block. So the
artefact the client and the server are built from carries no normalisation at all.

**Why it stops being a display bug:** the label is **printed on the emailed receipt** and **read aloud
at the door**. Two seats that a person reads as one name is, on that surface, two people in one chair.

**No fix is proposed and none is implied.** Upper-casing is not adopted here, is not described as
decided, and is not written into the walk as though it were. The question is the client's.

---

## Walk 6 — Withdraws a showtime that already has bookings

**Entering state.** Showtime 41 on Screen 3, day strip row reading "42 of 150 seats booked". The admin
has decided this screening must not happen.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-03` day strip | 42 seats sold. **There is no withdraw control and no disabled one.** The standing never-deleted note reads "Showtimes are never deleted, and v1 has no way to cancel one." | Goes to do the nearest thing the interface offers | `SCR-ADM-03 -> SCR-ADM-02 (/admin/movies/{id})` | `page` | The film editor and its "Withdraw from customers" control | `P-ADM-21` `P-ADM-06` | `J-ADM-12` |
| 2 | `SCR-ADM-02` | Published film | Presses "Withdraw from customers". The confirmation says in terms: "Showtimes and bookings for it are not changed and nothing is refunded." | `API -> Postgres: published_at = NULL + audit_log(movie.unpublished); then API -> Redis: the cached listings that could contain the film are deleted after commit` | `system` | The film leaves the browse surface immediately. **The showtime still exists, the 42 bookings still stand, the customers keep their seats and their references, and nothing is refunded, because nothing was cancelled** | `P-ADM-06` `P-ADM-19` `P-ADM-20` | - |
| 3 | a customer's browser | The film is off browse | Opens the showtime URL directly | `browse listing -> the booking surface, which does not apply the movie visibility gates` | `page` | The showtime, apparently still sellable. **Unresolved — this is `OPEN-BRWVIS-01` again, reached from the other side** | `P-BRW-01` `P-ADM-06` | `J-ADM-05` `J-ADM-06` |
| 4 | `SCR-ADM-05` | The admin tries the hall instead | Takes Screen 3 out of service, confirms | `API -> Postgres: screen.is_active = false + audit_log(screen.deactivated)` | `system` | The hall **accepts no new showtimes** and that is all. The confirmation says so: "Showtimes that already exist are not changed, bookings are not cancelled, and nothing is refunded." Showtime 41 is untouched | `P-ADM-16` `P-ADM-19` | - |
| 5 | the showtime itself | Nothing the admin can do has stopped it | Waits | `sales close at starts_at + SALES_CUTOFF_MINUTES (+15, PROVISIONAL under OPEN-BOOK-03)` | `time` | **The only thing in the product that ever stops that showtime selling is the clock — and under the current provisional reading it happens FIFTEEN MINUTES AFTER the screening has already started.** The 42 customers hold valid references for a screening the admin wanted stopped | `P-ADM-07` `P-ADM-09` | `J-ADM-12` | 

### `OPEN-SHOWCANCEL-01` — recorded, not answered

> **An admin withdraws a showtime that already has confirmed, paid bookings. What happens to those
> bookings, and what happens to the money?**

**Status: `OPEN`, `reserved: money, irreversible`, `CONSTITUTION.md` Article X.0.** `P-ADM-21` decides
nothing and says so on itself.

**Why it is open, in the client's own words.** `SRC-003 OPEN-OPS-03` lists what only the admin may do:
*"changes in movie, **cancel a show** or other priviledged things"* — so cancelling a show is a
**named admin capability**. `OPEN-CANCEL-02`, asked what happens when the cinema cancels a show and
whether refunds are automatic, answered *"no forget this"*, and `OPEN-CANCEL-01` answered *"no refund
policy"*. Those customers have paid. Either they are refunded, which contradicts a ruling, or they
have paid for a screening that will not happen and receive nothing — **which is a decision about money
that no model may make**.

**What v1 has instead, verified surface by surface:** no endpoint, no `DELETE`, no `POST /withdraw`,
no `PATCH` that sets a withdrawal state; no screen and no disabled control; **no `withdrawn_at` column
and no cancellation state on the `showtime` row**, because a column implies a capability that is not
built; no refund path, no customer notification, and no wording for one. A request to any
withdraw-showtime address answers `404 NOT_FOUND`, "That page does not exist" — the same answer as any
other address that does not exist.

**What this walk establishes that the row does not state on itself:** the two nearest actions
(`P-ADM-06`, `P-ADM-16`) **each explicitly change nothing about an existing showtime**, and the third
route — closing the film's display window — runs into `OPEN-BRWVIS-01`. **There is therefore no
combination of existing capabilities that stops one specific screening selling.** That is the honest
statement of the gap, and it is the fail-closed position: an unbuilt capability is recoverable, an
unrefunded customer is not.

**One further thing is blocked on this row and is recorded rather than resolved:** what a withdrawal
would do to **live seat holds and in-flight checkouts** on that showtime. `FR-ADR-035` states it is
blocked and does not pretend to resolve it. The case cannot arise in v1 because the capability does
not exist.

---

## Walk 7 — The audit trail

**Entering state.** An admin about to change a showtime's base price, on a system in Phase 2 or later.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | `SCR-ADM-03` edit form | Showtime 41, `version 1`, `base_price_paise = 25000` | Submits `base_price_paise = 28000`, echoing `version` | `API -> Postgres, ONE transaction: re-read the row; compare version; validate fields; no-op check; write the column; INSERT audit_log; COMMIT` | `system` | 200. One audit row: `occurred_at` UTC, `actor_user_id` non-null, `actor_role` **copied at the time** rather than joined, `action = showtime.base_price_changed`, `entity_type = showtime`, `entity_id = 41`, `before = {"base_price_paise": 25000}`, `after = {"base_price_paise": 28000}`, `request_id`. **Both rows commit together or neither exists** | `P-ADM-19` `P-XCT-03` `P-ADM-12` | - |
| 2 | — (the failure direction) | The same write; the audit insert fails | Nothing the admin can do | `API -> Postgres: the WHOLE transaction rolls back. The change fails BECAUSE the audit failed, never the reverse` | `system` | 500, and nothing written. The application's database role holds `INSERT` and `SELECT` on `audit_log` and **no `UPDATE` and no `DELETE`** — checkable by a test asserting an `UPDATE` from that role raises insufficient privilege | `P-ADM-19` `P-XCT-03` | `J-ADM-15` `J-ADM-16` |
| 3 | the admin shell | The operator wants to know who changed a price | Opens "Change log" | `shell -> SCR-RPT-02 (/dashboard/audit)` | `page` | The change log. **Admin only, and it is the one admin-only route that does not sit under `/api/admin`** — it is a read, so it belongs to the reporting router by shape and narrows to admin by rule | `P-RPT-11` `P-ADM-18` | - |
| 4 | `SCR-RPT-02` | A date window chosen | Filters on `action = showtime.base_price_changed` | `API -> Postgres: EP-RPT-04, rows ordered by id DESC with a cursor; available_actions and available_actors computed over the DATE WINDOW ALONE` | `system` | The row, joined to the acting user for `actor_email`, with `before`/`after` rendered **verbatim with the field name and never unit-converted** — `base_price_paise: 25000 -> 28000`, exactly so. **The reading surface is Phase 8; the rows are written from Phase 2**, because an audit trail that starts when its reader is built has a hole as long as the build took | `P-RPT-11` `P-XCT-04` | - |
| 5 | `scripts/seed.py` | A migrated, unseeded database. The seed writes **one cinema, six screens, 960 seats, three categories, twelve lookup rows, eight films, one poster, 720 showtimes, 115,200 `showtime_seat` rows, 63 accounts and 11,003 bookings** | Runs the seed | `scripts/seed.py -> Postgres: direct INSERTs into every table, with no HTTP request, no session, no router dependency and no authenticated actor` | `system` | **A fully populated database, and the specification does not say whether one `audit_log` row was written for any of it, or what `actor_user_id` would name.** `P-ADM-19` makes `actor_user_id` non-null and says "never a role name, never a service account". The seed creates the **first admin itself**, so for the earliest rows no actor exists to name | `P-XCT-30` `P-ADM-19` `P-XCT-03` | `J-ADM-13` |
| 6 | `SCR-ADM-05` | Screen 6 being laid out | Submits 220 seats in one request | `API -> Postgres: 220 seats and 220 audit_log rows in one transaction` | `system` | An all-or-nothing batch, and a change log whose first page is nothing but seat creations. **That is stated as a cost and accepted**, because `entity_id` is the primary key of the changed row and one column cannot hold 220 of them without lying about one | `P-ADM-19` | - |

### The audit guarantee, confirmed against the walk

**Same transaction: confirmed.** `P-ADM-19` and `P-XCT-03` both state it, and `P-ADM-19` exception 1
states it in the load-bearing direction — *the change fails because the audit failed, never the
reverse.* An audit written after the commit is missing exactly the rows that crashed.

**Names the acting admin: confirmed.** `actor_user_id` is a non-null foreign key to a real user row;
`actor_role` is copied at the time because a role can change. No credential ever enters `before` or
`after`; no card data anywhere; no poster bytes, only the S3 key.

**Readable: confirmed, from Phase 8.** `P-RPT-11` specifies the reading surface, admin-only as a
stricter adoption that is recorded as one. `available_actions` is derived from the data rather than
from a vocabulary the reporting lane defines, so the reading surface can never disagree with the
writing surface.

**The seeded-data path: NOT confirmed, and this is the gap.** Every rule above is written for a
request handler with an authenticated actor in the request context. `scripts/seed.py` has none of
those things. `P-XCT-30` is exhaustive about days, halls, slots, formats, occupancy, seat labels, band
widths, film assignment, runtimes, booking sizes and owners — **and says nothing at all about the
audit log.** A developer writing the script must choose between violating the non-null actor rule,
violating the every-privileged-write-is-audited rule, or inventing the service account the
specification forbids. **That is a guess, and it is filed rather than guessed** (`J-ADM-13`).

---

## Walk 8 — A second admin

**Entering state.** The client is the only admin. They want a second one — a partner, a stand-in, or
simply a second account so that the first can be locked away.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1 | the admin shell | Signed in as admin. The navigation carries **Dashboard · Change log · Films · Showtimes · Pricing · Halls · Managers · Lists · My bookings**. There is no item for accounts of any other kind | Opens Managers, the only account surface there is | `shell -> SCR-ADM-06 (/admin/managers)` | `page` | A list of manager accounts, a "New manager" action, **no password field and no role selector** — the screen states in terms that it "creates managers and nothing else" | `P-ADM-17` `P-ADM-18` | - |
| 2 | `SCR-ADM-06` create form | An email address and a set of halls | Creates the account. If they try to force it by sending `{"role": "admin"}` in the body, that property is **rejected with 400 `REQUEST_INVALID`, never dropped and never honoured** | `API -> Postgres: INSERT user with role='manager' and NO usable password + audit_log(manager.created) + one audit_log(manager.screen_assigned) per hall, one transaction` | `system` | **A manager.** Read-only, scoped to their halls, and by rule unable to write anything. Not an admin, and no request to this endpoint can produce one | `P-ADM-17` `P-ADM-19` | - |
| 3 | — (off the product entirely) | Every surface exhausted. `P-ADM-17` states it flatly: *"There is no endpoint that creates an admin account. The first admin is created by the seed script; creating a second is a database action the client performs deliberately"* | Connects to the database and inserts or updates a `user` row by hand | `operator -> Postgres: an account created OUTSIDE the application — no router dependency, no request id, no actor, and no audit row` | `system` | An admin account whose creation is **invisible to the change log**. The one table that exists to answer "who changed what" cannot answer who granted a person the ability to change everything. **No procedure for this is specified anywhere** — not a runbook step, not a documented statement, not a warning | `P-ADM-17` `P-ADM-19` `P-ADM-18` | `J-ADM-14` |
| 4 | the sign-in page | A hand-created admin row with no usable password | Uses the password-reset link | `API -> SES: a password-reset email` | `system` | A password. **Reasoned, not specified:** `P-ADM-17` states this mechanism for a *manager* and no row states it for an admin. It would work, because the reset flow is open to any account — but nothing in the PRD says so, and nothing has been observed running | `P-ADM-17` | - |

### `OPEN-ADMINCOUNT-01` — recorded, not answered

> **How is a second admin account created?**

**Status: `OPEN`, `reserved: access control`, `CONSTITUTION.md` Article X.0b**, raised by the admin
lane itself as `PROPOSED-ADMINCOUNT-01`.

**Why it is genuinely unruled and not merely unbuilt.** `SRC-003 OPEN-ROLE-01`'s *"do not make more
personas… only 1 admin persona"* **can be read as ruling that there is exactly one admin** — in which
case the absence is correct and permanent. It can also be read, as `SRC-003 C-1` reads it for
managers, as being aimed at persona *tiers* rather than at account counts. **The build session may not
pick**, and it did not: the interim position is fail-closed, because an endpoint that accepts a role
string is one privilege-escalation bug away from creating an admin.

**Where the walk actually dead-ends, precisely:** at step 3, at the boundary of the product. Not at a
disabled control, not at a 403, not at a "coming soon" — **there is no surface at all.** The only
route left leaves the application, and leaving the application is exactly the thing that makes the
audit trail unable to record it.

**No endpoint is proposed, no role selector is drawn, and no procedure is invented.**

---

## What this walk could not establish

- **Nothing here has been observed running.** No application code exists. Every statement about S3,
  presigned URLs, streaming behaviour, Redis holds and SES in this document is **reasoned from the
  specification, not observed**, and this project has never seen the product running in AWS.
- **Step 4 of walk 8 is reasoned, not specified.** That a hand-created admin obtains a password
  through the reset flow follows from `E5`'s flow being open to any account; no row states it.
- **I did not read `E5_account.md` or `E3_checkout_payment.md`.** Walk 4's payment step and walk 8's
  reset step therefore cite no `P-PAY` or `P-ACC` row, and neither is claimed as verified.
- **I did not read `E8_crosscutting.md` end to end**, per the brief. `P-XCT-05` was located but not
  read, so it is not cited even though authorisation is walked; `P-ADM-18` carries that citation
  instead.
