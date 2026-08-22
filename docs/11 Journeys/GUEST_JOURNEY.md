# GUEST — the person with no account

```
Lane .............. GUEST (GOAL_06, one of five walked independently and blind)
Walked ............ 2026-08-22
Sections read ..... docs/03 PRD/sections/S1_reading_rules.md (full)
                    docs/03 PRD/sections/S3_personas_surfaces.md (full)
                    docs/03 PRD/sections/S2_scope.md (full)
                    docs/03 PRD/sections/E1_browse.md (full — P-BRW-01..16, SCR-BRW-01..03,
                      EP-BRW-01..07, lane notes)
                    docs/03 PRD/sections/E5_account.md (P-ACC-01, -02, -13, -14, -15, SCR-ACC-01)
                    docs/03 PRD/sections/E2_seat_hold.md (P-SEA-01..04, P-HLD-05, P-HLD-06,
                      P-HLD-14)
                    docs/03 PRD/sections/E8_crosscutting.md (P-XCT-07, -08, -09, -11,
                      SCR-XCT-03, SCR-XCT-05 — grepped, not read end to end)
                    CONSTITUTION.md Article X.0–X.0d (to check what is already filed)
Defects filed ..... 10, in defects_guest.tsv (J-GST-01 .. J-GST-10)
```

**What this lane is.** The guest has no account and no session. They may browse movies, showtimes and
the seat map, and they may select seats in the interface. **They cannot hold and they cannot book**
(`S3.1`, `S3.6`, `P-BRW-05`, `P-HLD-05`). This document walks what they can see, what the empty and
degraded states look like, and what happens at the wall.

**One thing to hold throughout.** Nothing on the browse path varies by who is reading it. The seat map
is one shared cached payload and the server does not know whose session is reading it
(`P-BRW-09`, `EP-BRW-06`). So a guest is not a reduced customer on these screens — a guest and a
signed-in customer receive byte-identical responses, and the only differences are drawn on the client:
no seat is ever `held_by_me`, and the primary action reads `Sign in to hold these seats`.

---

## Walk 1 — a guest browses with no account, including the empty and degraded states

Entering state for step 1: a first visit, no cookie, cold cache, a populated catalogue.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 1.1 | `SCR-BRW-01` the movie listing, `/` | no session, no cookie, cold Redis | Opens the site | browser → `GET /api/movies` and `GET /api/reference`; app → Redis `cache:listing:{generation}:{fingerprint}` **miss** → rebuild lock `SET NX PX 2000` → PostgreSQL → write back at 60 s TTL | `system` | Every published film inside its display window, `published_at DESC, id DESC`, with a count; the date strip; and whichever filter controls have two or more values in use | `P-BRW-01` `P-BRW-02` `P-BRW-03` `P-BRW-05` `P-BRW-12` `P-BRW-13` `P-XCT-08` | — |
| 1.2 | `SCR-BRW-01`, poster boxes | listing rendered, poster boxes drawn at `--fr-poster-ratio` before any image arrives | Browser fetches each `poster_url` | `GET /api/movies/{id}/poster` → **302** with a presigned S3 GET URL valid 3600 s → browser → S3 directly. The API never proxies the bytes | `system` | Posters, or the perforation motif with the title inside it where the object is missing — no words, no broken-image glyph | `P-BRW-15` `P-BRW-02` | — |
| 1.3 | `SCR-BRW-01`, **empty — nothing in window** | every published film has `T >= display_until`, or none is published | Opens `/` | app → PostgreSQL: `published_at IS NOT NULL AND display_from <= T AND T < display_until`, `T` from the **injected** clock in Asia/Kolkata, evaluated at read time because nothing sweeps (`P-SCP-07`) | `time` | `Nothing is showing right now.` One line, no illustration, **and no date strip at all** — the maximum is over an empty array, so there is no bound to render | `P-BRW-01` `P-BRW-04` `P-SCP-07` | — |
| 1.4 | `SCR-BRW-01`, filters | a populated listing, `Any date` / `Any language` / `Any format` selected, no `Clear filters` control rendered | Chooses a language | client re-requests `GET /api/movies?language_id=…`; app → Redis under a **new filter fingerprint** → miss → PostgreSQL. Filters narrow the set and never change the order | `system` | A narrowed listing, the same order, a `Clear filters` control, and a re-derived date strip — `max(display_until)` is taken over the **filtered** array, so applying a filter can shorten the strip | `P-BRW-03` `P-BRW-04` `P-BRW-12` | — |
| 1.5 | `SCR-BRW-01`, **empty — filters set** | a language and a format chosen | Waits for the response | app → PostgreSQL: the movie matches `language_id`, **and** has at least one showtime satisfying `date`, `cinema_id` and `format_id` **simultaneously** — one `EXISTS`, never three | `system` | `Nothing is showing for the chosen filters.` with `Clear filters` beneath it. No special wording exists for "your filters were satisfied separately but not together" | `P-BRW-04` | — |
| 1.6 | `SCR-BRW-01`, date strip | strip runs today → the day **before** `max(display_until)` over the filtered array | Presses a day button on which no film has a showtime | client re-requests with `date=`; app → PostgreSQL converts the local day to `[2026-08-14T18:30:00Z, 2026-08-15T18:30:00Z)` and applies the showtime `EXISTS` | `time` | `Nothing is showing for the chosen filters.` — **from a control the specification says cannot reach that state** | `P-BRW-04` `P-BRW-06` | `J-GST-01` |
| 1.7 | `SCR-BRW-01` → `SCR-BRW-02` `/movies/{id}` | a film chosen | Presses a card | `SCR-BRW-01 -> SCR-BRW-02`; then `GET /api/movies/{id}` and `GET /api/showtimes?movie_id=…` with no `date`, which **defaults to today in the cinema's zone** — the opposite of the listing's rule, deliberately | `page` | The full synopsis, the poster, a date strip bounded by this one film's window, and today's showtimes ascending by start time with hall and base price | `P-BRW-01` `P-BRW-02` `P-BRW-06` | — |
| 1.8 | `SCR-BRW-02`, a date with no showtimes | a film with a sparse schedule | Presses a day in the strip | app evaluates `next_date_with_showtimes`: strictly after the requested date, inside the window, holding **one** showtime that is both still open and matching every filter carried | `time` | `No showtimes on this date.` plus `Next: Fri 15 Aug` — or, where no such date exists, `No showtimes for this movie.` and **no button at all** | `P-BRW-06` `P-BRW-07` | — |
| 1.9 | `SCR-BRW-02`, a closed showtime | a showtime whose `starts_at + SALES_CUTOFF_MINUTES` has passed | Looks at the grid | app derives `sales_close_at` at read time, never stored; `sales_closed = NOT (T < sales_close_at)` against the injected clock. **`SALES_CUTOFF_MINUTES = +15` is `PROVISIONAL`** | `time` | The showtime **still listed**, marked `Closed`, removed from the tab order, not navigable. The list is never emptied to force them forward | `P-BRW-07` | — |
| 1.10 | `SCR-BRW-02` → `SCR-BRW-03` `/showtimes/{id}` | an open showtime chosen | Presses a showtime button | `SCR-BRW-02 -> SCR-BRW-03`; two requests — `GET /api/showtimes/{id}` for the header, and `GET /api/showtimes/{id}/seatmap` for the map. The header exists so the frame draws at full size before the map lands | `page` | The hall's real layout: rows, seat numbers, aisles as the **absence** of a cell, category bands derived client-side from `gr`/`cat`, a legend, and a per-seat already-rounded `price_paise` | `P-BRW-08` `P-BRW-09` `P-BRW-10` `P-BRW-13` `P-BRW-16` | — |
| 1.11 | `SCR-BRW-03`, live | map painted | Waits, looking at the map | client re-fetches every `poll_interval_seconds` (server configuration, published in the payload, default **3**); app → Redis `cache:seatmap:{id}` at a **10 s** TTL. Worst-case staleness ≈ **13 s** | `time` | A map that moves under them, with a 2 px ring on any cell that changed. Polling pauses while the tab is hidden and fires immediately on return | `P-BRW-11` `P-BRW-09` `P-BRW-14` | — |
| 1.12 | `SCR-BRW-03`, **sold out** | every seat has a booking row for `(showtime_id, seat_id)` | Opens the map | app → PostgreSQL derives `sold`, then Redis for live locks, then `available` | `system` | The **full map**, every cell hatched, plus `Every seat for this showtime is sold.` Never an empty state — the guest wants to see that it is genuinely full | `P-BRW-09` `P-BRW-08` | — |
| 1.13 | `SCR-BRW-03`, **every seat retired** | an admin has retired every seat since the showtime was created | Opens the map | app returns the frozen seat set with `is_active: false` on every member — the set is **not empty**, so this is a 200 and not the 500 one word away | `system` | A complete grid, every cell dashed and out of service, nothing selectable, plus `None of the seats in this hall are available.` | `P-BRW-08` `P-BRW-09` | — |
| 1.14 | `SCR-BRW-03`, **hall never laid out** | a showtime whose seat set has zero rows | Opens the map | app → PostgreSQL returns no seats → `500 INTERNAL_ERROR`, because a showtime always has a hall and a hall always has seats | `system` | `The seat map could not be loaded.` plus `If you need help, quote a1b2c3d4.` — the request id is shown on 5xx only. Unreachable for a normally created showtime, and specified anyway | `P-BRW-08` `P-XCT-11` | — |
| 1.15 | `SCR-BRW-03`, **Redis unreachable** | Redis down mid-browse | Opens or polls the map | limiter runs **before** the cache and fails closed → `503 DEPENDENCY_UNAVAILABLE`. The PostgreSQL fallback is never reached. The movie list and showtime list are **not** limited and still return 200 | `system` | `The seat map is unavailable right now. You can still browse showtimes. Try again in a few minutes.` The rest of browsing keeps working, slower | `P-BRW-12` `P-XCT-09` `P-XCT-11` | — |
| 1.16 | `SCR-BRW-03`, **rate limited on first load** | six other people behind the same public address are already polling this showtime | Opens the map | app → Redis token bucket, 120/min **per IP**, no per-user bucket because the endpoint is unauthenticated. One legitimate poller uses 20 | `system` | Two published answers for one situation, and a limit that a shared address exhausts at about six concurrent guests | `P-BRW-11` `P-XCT-07` | `J-GST-07` `J-GST-08` |
| 1.17 | `SCR-BRW-01`, **reference data down, listing up** | PostgreSQL healthy for the listing query, `/api/reference` 503 | Opens `/` | `GET /api/reference` → 503; `GET /api/movies` → 200 | `system` | A listing with **no filter controls at all** — which is also the correct day-one rendering, so a guest and a screenshot cannot tell an outage from an empty vocabulary | `P-BRW-04` `P-BRW-12` | `J-GST-10` |

**Sorting, walked and found absent by design.** `sort` accepts exactly one value, `newest`, and **no
sort control renders while one value exists** — the same rule that keeps the cinema filter off the
screen. A guest cannot re-order the listing at all. That is not a defect: which sorts the customer may
choose is `OPEN-SORT-01`, filed and unruled, and `P-BRW-03` refuses to invent a menu. Walked, cited,
not filed again.

**The cinema filter, walked as a positive absence.** `cinema_id` is implemented, tested and documented
and **nothing renders it**, because one cinema exists and the two-or-more rule governs
(`P-BRW-04`, `FR-ADR-046`). The control appears on its own the day the reference endpoint reports two.
This is `excluded is not blocked` doing visible work, and it is correct.

**One thing the guest sees that is bounded rather than exact.** The listings cache is invalidated by an
`INCR` of a generation counter on every **admin write**. A film leaving its display window is a *time*
event and not a write, so nothing increments anything — the film can survive in a cached listing for
up to `LISTING_CACHE_TTL_SECONDS` (60 s) after it left. That staleness is bounded and stated, and it is
the correct trade. It is recorded here because a reader watching the clock at the boundary will see it
and should not read it as a defect.

---

## Walk 2 — the registration wall

Entering state: a guest on `SCR-BRW-03` with four seats selected and a running total on screen.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 2.1 | `SCR-BRW-03` | guest, map painted, four `available` seats tapped, total built from summed integers | Presses the primary action, which reads `Sign in to hold these seats` | writes `fr.pending_selection` = `{showtime_id, seat_ids, stored_at}`, **then** `SCR-BRW-03 -> SCR-ACC-01` at `/sign-in` | `page` | The authentication screen, with a context note reading `Your seats are still selected. Sign in to hold them.` **Nothing was held and nothing was sent** | `P-BRW-05` `P-SEA-01` `P-SEA-03` `P-SEA-04` `P-ACC-13` `P-HLD-05` | `J-GST-05` |
| 2.2 | the hold endpoint, bypassing the interface | a guest, or a caller with no interface at all, posting directly | `POST /api/showtimes/{id}/holds` with no cookie | router authorisation dependency refuses **before the handler runs**; no Redis `SET NX` is issued, no lock is taken, no seat leaves sale | `system` | `401 AUTH_REQUIRED` — `Sign in to hold seats. Your selection has been kept.` The stop is at the hold, not at the seat click and not at payment | `P-HLD-05` `P-HLD-14` `P-BRW-05` | — |
| 2.3 | `SCR-XCT-05` the shell | guest on `SCR-BRW-03` with a live selection | Uses the header `Sign in` link instead of the primary action | `SCR-BRW-03 -> SCR-ACC-01`; **`fr.pending_selection` is never written**, because only the primary action writes it | `page` | On success, `SCR-ACC-01`'s "otherwise" branch: the **movie listing**. The showtime and the selection are gone with no message | `P-ACC-13` `P-BRW-05` | `J-GST-06` |
| 2.4 | `SCR-ACC-01` | the form open, seats **not** held | Types an email and a password, slowly | **no TTL is running, because nothing was held.** Any other customer may hold or buy those seats during this interval. Selection is local; scarcity is consumed only at the hold | `time` | Nothing on the server. The seats are exactly as exposed as they were before the guest chose them | `P-SEA-03` `P-HLD-05` `P-ACC-13` | — |
| 2.5 | `SCR-ACC-01`, abandoned and resumed | the guest walked away for 40 minutes and came back to the same tab | Returns and signs in | on restore the client compares `stored_at` to the current instant; **older than 30 minutes is discarded** — a `[JUDGMENT CALL]`, not a ruled figure | `time` | The seat map with **no selection and no message**. Restoring a 40-minute-old selection only to report every seat gone is worse than starting clean | `P-ACC-13` | — |

**The answer to the question this walk exists to ask.** *Are the seats held, lost, re-selected, or
silently taken while the guest fills in a form?* **They are none of held and none of silently taken.
They are re-selected, and any that went are named.** The selection is client-side only
(`sessionStorage`, key `fr.pending_selection`), no lock is taken at any point before the hold, the map
is **refetched before anything is restored**, and a seat that has gone is reported by name and by count
before the guest proceeds. The PRD answers this seam fully and explicitly, and refuses the two obvious
shortcuts — it does not take the hold automatically on return, because that would either silently drop
a seat or fail immediately after a successful registration and read as the registration having failed.

The seam is answered. What is **not** answered is the mechanism underneath it: two rows describe two
different write policies for one stored fact and only one of them names a key (`J-GST-05`), and one
route to the same screen skips the write entirely (`J-GST-06`).

---

## Walk 3 — registration itself, and the return to the booking flow

Entering state: `SCR-ACC-01`, register tab, `fr.pending_selection` written.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 3.1 | `SCR-ACC-01` register tab | email and a 12-character password typed | Presses `Create account` | `POST /api/auth/register` → app → Redis (registration bucket, 5/hour/IP) → bcrypt **in a thread, off the event loop** → PostgreSQL insert with `role='customer'`, `password_version=1`, `last_signed_in_at=NULL` → session cookie → `201` | `system` | An account **and a live session in one request**. No verification email, no welcome email — every SES message competes with the receipt for a sandboxed quota | `P-ACC-01` `P-ACC-14` `P-XCT-07` | — |
| 3.2 | `SCR-ACC-01` register tab | the address already has an account | Presses `Create account` | app → PostgreSQL unique index on `lower(email)`; a simultaneous second registration is caught as a unique violation and **translated**, never surfaced as a 500 | `system` | `409` — `An account already exists for that email address. Sign in instead, or reset the password if you have forgotten it.` This discloses that the address is registered, and it is recorded as an accepted weakness rather than solved | `P-ACC-01` | — |
| 3.3 | `SCR-ACC-01` | five accounts already created from this address this hour | Presses `Create account` | app → Redis token bucket; `Retry-After` computed from the **refill rate** (3600/5 = 720 s), never a constant, then rendered by `S7.20` as minutes because it is at or above 120 s | `time` | `429` — `Too many accounts have been created from this connection. Try again in 12 minutes.` The control **stays enabled**; the server is the thing that says no | `P-ACC-14` `P-XCT-07` | — |
| 3.4 | `SCR-ACC-01` | Redis unreachable | Presses `Create account` | limiter fails **closed** — not unlimited access | `system` | `503` — `Registration is unavailable right now. Browsing still works. Try again shortly.` Which is true: the listing and the showtime list still serve from PostgreSQL | `P-ACC-01` `P-XCT-09` | — |
| 3.5 | `SCR-ACC-01` → `SCR-BRW-03` | `201`, session cookie set, `fr.pending_selection` present | Nothing — the interface navigates | **no success screen.** `SCR-ACC-01 -> /showtimes/{stored showtime_id}`, and the client **refetches the seat map before restoring anything** | `page` | The same showtime they left, not the top of the site. They land **where they were**, because a stored selection exists | `P-ACC-13` | — |
| 3.6 | `SCR-BRW-03` | fresh map in hand, stored seat ids not yet applied | Client re-applies the selection | client intersects stored ids against the fresh payload; ids still `available` are re-selected, ids now `sold` or `held_by_other` are **not**, are drawn in their real state, and are named | `system` | `C12 and C13 were taken while you were signing in. Your other seats are still selected.` — or the singular at exactly one, or `The seats you chose were taken while you were signing in. Choose again from the map.` at zero survivors. Then `fr.pending_selection` is deleted | `P-ACC-13` `P-SEA-03` | — |
| 3.7 | `SCR-BRW-03` | selection restored, primary action now reads `Hold these seats` | Presses it, after the cut-off passed during registration | `POST /api/showtimes/{id}/holds` → cut-off checked **at the hold and never at confirmation**, against the injected clock | `time` | `409 SALES_CLOSED` — and **two rows publish two different sentences for this exact surface** | `P-ACC-13` `P-HLD-06` `P-HLD-14` `P-BRW-07` | `J-GST-09` |
| 3.8 | `SCR-BRW-03` | first-time run complete | Measures the run | `t0` is the first paint of real seat data; `t1` is the paint of the booking reference. The first-time figure **includes registration and will not meet `SC-1`** | `time` | A number reported on its own line, labelled first-time, **with no pass or fail attached** and never blended into the signed-in figure | `P-ACC-15` | — |

**Do they land back where they were, or at the top?** **Where they were**, and the rule is explicit:
the destination is the seat map for the stored showtime when `fr.pending_selection` exists, and the
movie listing otherwise. Two things narrow that. First, the "otherwise" branch is not a fallback for an
interrupted task — an interrupted request is `SCR-XCT-04`'s, which preserves **the path**, and the two
rules are deliberately separate rather than one stated twice. Second, the guest who reaches the form by
the header link has no stored selection at all and therefore takes the "otherwise" branch and is
dropped on the listing (`J-GST-06`) — the same screen, the same success rule, a materially different
outcome, decided by which control they pressed two screens earlier.

---

## Walk 4 — a film leaves its display window while its showtimes still have unsold seats

`OPEN-BRWVIS-01` is **OPEN**. This walk records what the documents do say, and stops where they stop.
No policy is invented here.

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 4.1 | `SCR-BRW-01` | `T` crosses `display_until` for a film with unsold seats tonight | Reloads `/` | window evaluated at **read time** against the injected clock — nothing sweeps, because nothing runs on a schedule. The cached listing survives its 60 s TTL, so the film can linger for up to a minute past the boundary | `time` | The film gone from the listing. It is never deleted and never hidden from the admin | `P-BRW-01` `P-BRW-12` `P-SCP-07` | — |
| 4.2 | `/movies/{id}` by direct link | the film has left its window | Follows a bookmark or a shared link | `GET /api/movies/{id}` applies both gates and returns `404 NOT_FOUND` — **the same 404 as a movie that never existed**, so draft ids cannot be enumerated | `page` | `That movie is not showing.` and a link reading `Back to what is showing` | `P-BRW-01` `P-BRW-02` | — |
| 4.3 | the showtime list | the film has left its window | Requests `GET /api/showtimes?movie_id=…` | app applies the visibility gate to the **movie** before listing its showtimes | `system` | `404` — the showtimes are unreachable through the browse path | `P-BRW-06` `P-BRW-01` | — |
| 4.4 | `SCR-BRW-03` by direct link | the film has left its window; the showtime still has unsold seats | Follows a bookmarked `/showtimes/{id}` | `EP-BRW-05` states in terms that it **does not apply the movie visibility gates** — "it is the booking surface". `EP-BRW-06` applies none either | `page` | **A 200, the film's title and certification, the hall, the price, and a live polling seat map for a film the listing says is not showing.** `SCR-BRW-03` publishes **no state and no banner** for this | `P-BRW-01` `P-BRW-05` `P-BRW-08` | `J-GST-02` `J-GST-03` |
| 4.5 | the hold endpoint | the same guest, now signed in, on that map | Presses `Hold these seats` | E2 checks membership of the showtime's seat set, `is_active`, the ten-seat cap and the sales cut-off. **It checks nothing about the film's display window** — the words `display window` do not appear in E2 at all | `system` | The hold succeeds, and the sale proceeds. **Whether it should is `OPEN-BRWVIS-01`, and this walk does not answer it** | `P-HLD-05` `P-HLD-06` | `J-GST-03` |
| 4.6 | `SCR-BRW-01` date strip | an admin created a showtime whose `starts_at` falls **outside** the film's display window — nothing forbids it | Looks for that showtime | the strip ends at the day before `max(display_until)`, and `next_date_with_showtimes` condition 2 confines the search to inside the window | `time` | The showtime is **reachable from no guest browse surface at all** — not the strip, not the next-date button, not the listing's date filter. It exists, it has seats, and only a direct URL finds it | `P-BRW-04` `P-BRW-06` `P-BRW-01` | `J-GST-04` |

**What the documents cannot answer, stated as a gap and not filled.** `FR-ADR-021` settles that the
window governs the **browse surface** and not the booking record. It settles nothing about whether
those showtimes may still be **sold**. The PRD's own lane notes say so plainly and refuse to decide:
making the seat map 404 would break a customer mid-checkout, and leaving it sellable creates a
withdrawal path in all but name — and withdrawal is `OPEN-SHOWCANCEL-01`, which is reserved and open.
That is `OPEN-BRWVIS-01`, already filed, and this lane re-files nothing.

What this lane adds is the **surface** consequence, which is separable from the policy and needs
fixing whichever way the client rules: `P-BRW-01` states without qualification that a film failing
either gate is "invisible to guests and customers alike" and that the predicate is called "from every
such query", while `EP-BRW-05` states the opposite for itself. One of those two sentences is wrong
today, and no ruling on `OPEN-BRWVIS-01` makes both right (`J-GST-02`). And `SCR-BRW-03` has states for
sold out, sales closed, all seats retired, Redis down and showtime not found, and **none** for the film
having left its window (`J-GST-03`).

---

## Walk 5 — the exclusions, walked as absence

The `P-SCP` rows describe capabilities this product deliberately does not have. A guest is the right
persona to walk them, because a guest sees every public surface and has no privileges that could
explain an absence away. **Each step below is an attempt to reach an excluded capability.**

| # | Surface | State entering | Action | Seam crossed | Seam type | What they leave with | P-rows | Defects |
|---|---|---|---|---|---|---|---|---|
| 5.1 | `SCR-XCT-05` the shell, on `/` | guest | Looks in the header for anything beyond browsing | the guest's primary nav is **empty** — the wordmark is the only navigation, and the account area holds one `Sign in` link. There is no upcoming section to link to and no route that serves one | `page` | No "coming soon", no pre-sale, no notify-me. A future-dated film is representable and simply not rendered | `P-SCP-08` | — |
| 5.2 | any unmounted path | guest | Hand-types `/upcoming` | a **global exception handler**, mounted on the application and on no router, renders the standard envelope | `system` | `404 NOT_FOUND` — `That page does not exist.` No request id, because it is a 4xx | `P-SCP-08` `P-XCT-11` | — |
| 5.3 | `SCR-XCT-05`, `SCR-BRW-01` | guest reading English | Looks for a language switcher | the shell's own list of what it deliberately does not add names **no language switch**; the `Language` control on the listing filters the **film's** language and is unrelated to the interface's | `page` | One interface language. Checked as a near-miss and cleared: a film's `language` and an interface locale are two different fields and the PRD says so | `P-SCP-04` `P-BRW-04` | — |
| 5.4 | `SCR-BRW-03` | guest with seats selected | Looks for a scannable artefact | no image is generated anywhere, in the email or on screen. Entry is a person at the entrance reading `FR-XXXX-XXXX` and checking it by hand — no scanning device, no validation endpoint, no `used_at` column | `page` | No QR code, no barcode, no scanner. **Accepted weakness, stated rather than buried: nothing prevents the same reference being presented twice** | `P-SCP-09` `P-SCP-10` | — |
| 5.5 | every surface a guest can reach | guest | Looks for a cancel or refund control | the capability matrix marks cancellation `∅` for **all four roles**, and the 58-endpoint inventory contains no cancellation and no refund route. The schema keeps `status` and `cancelled_at` and **no v1 endpoint exposes either** | `page` | Nothing. A confirmed booking is final, and a customer who cannot attend loses their money — recorded, not challenged | `P-SCP-11` | — |
| 5.6 | every surface a guest can reach | guest | Looks for a download or export | no endpoint returns a file: no CSV, no spreadsheet, no PDF, no print-to-file. The reason is stronger than a missing feature — it keeps customer-level booking data off any download path | `page` | Nothing to download | `P-SCP-14` | — |
| 5.7 | `SCR-BRW-03` price summary | four seats selected | Reads the total | the client **sums already-rounded integers** and performs no arithmetic of its own. There is no F&B line, no loyalty balance, no discount field, no booking fee and no separate tax line — **and no space left on any screen for one** | `system` | A total that is the sum of the seat prices and nothing else. The stored total is a single figure and cannot be split retrospectively; that limit is stated rather than discovered | `P-SCP-02` `P-SCP-03` `P-SCP-16` `P-SEA-04` `P-BRW-10` | — |
| 5.8 | `SCR-BRW-03` on a 375 px phone | guest on the largest hall's map | Scrolls | the map scrolls **horizontally inside its own container** and the page body never does. The seat cell is never shrunk to avoid the scroll | `page` | One responsive web interface. No native app, no app-store artefact, no install prompt | `P-SCP-01` `P-BRW-13` | — |
| 5.9 | any never-deleted entity | a hand-made request, not the interface | Sends `DELETE /api/movies/{id}` | a **global handler**, not a route, renders `405`. No `DELETE` route is mounted for movie, showtime, screen, cinema or the four lookup vocabularies, because withdrawal replaces deletion | `system` | `405 METHOD_NOT_ALLOWED` — `That action is not available. Nothing was changed.` Entity-blind, because routing failed before any handler ran | `P-XCT-11` | — |
| 5.10 | `SCR-BRW-03` | guest looking at a seat that was sold at the counter ten minutes ago | Reads the map | the application knows only online sales — **a seat sold at the counter is invisible to it** | `system` | A seat drawn `available` that is not. Stated plainly as a real operational consequence: while both channels exist, the online map is authoritative only for online sales | `P-SCP-05` | — |
| 5.11 | `SCR-BRW-01` | guest | Looks for recommendations | the listing sorts by the customer's chosen filter, defaulting to newest first. **That is an ordering, not a recommendation.** No model call anywhere in the product, no customer data sent to any model | `page` | A list, in a stated order, with a stated tiebreak | `P-SCP-17` `P-BRW-03` | — |
| 5.12 | `SCR-BRW-01` | guest, on a day when a film's details look thin | Waits for an external source to fill them in | **there is none.** No external movie API, no API key, no upsert-by-external-id, and **no "the external source is unavailable" failure path — the failure cannot occur because the dependency does not exist**. Nothing runs on a schedule | `time` | Exactly what the admin typed by hand, and no attribution footer | `P-SCP-06` `P-SCP-07` | — |
| 5.13 | `SCR-BRW-03` legend and cells | guest who uses a wheelchair, or a pair of guests | Looks for an accessible seat or a couple seat | no wheelchair flag, no pair linkage, no gap rule — every seat is sold individually and any available seat may be chosen. The lock stays **per seat**, which keeps the hardest part of the system at its simplest form | `page` | No marking of any kind. Recorded, not challenged: a real cinema in India operates under accessibility obligations and this rests on there being no real customers | `P-SCP-13` `P-SEA-01` | — |
| 5.14 | `SCR-BRW-02` | guest looking at a showtime the cinema means to pull | Looks for a withdrawn or cancelled showtime | **the admin has no way to withdraw a showtime** — no endpoint, no control, no screen. So the guest can never meet one. The gap is stated to the client rather than left to be found | `page` | Every showtime that exists is still listed. `P-SCP-18` is `OPEN`, reserved, and not an exclusion | `P-SCP-18` | — |
| 5.15 | `SCR-XCT-05` footer, every route | guest anywhere in the product | Reads the footer | one line, on every screen, discharging two requirements at once: the simulated provider must be visible rather than silent, and the deployed environment must never be called production | `page` | `Demonstration environment. Payments are simulated and no card details are ever taken.` No card field and no placeholder for one exists anywhere | `P-SCP-12` `P-SCP-15` | — |

**Result of walk 5: no contradiction found.** Every excluded capability was searched for on the
surfaces a guest can reach — the shell and its nav, the listing and its controls, the movie screen, the
seat map and its legend, the price summary, the footer, and the 58-row endpoint inventory — and **no
screen, endpoint or copy string offers one**. Two near-misses were checked and cleared rather than
assumed: the `Language` filter (the film's language, not the interface's, `P-SCP-04`) and the `cinema`
filter capability that exists and does not render (`excluded is not blocked` working as intended,
`S2.5`). The absences are also **positively specified** rather than merely missing — `SCR-XCT-05`
carries an explicit list of what it does not add so a later session cannot read the omissions as
oversights, and `S3.8` states the four absent endpoint classes as deliberate.

---

## What this lane could not settle

- **Whether a showtime of an out-of-window film may still be sold.** `OPEN-BRWVIS-01`, filed, open,
  and not answered here. The walk records the mechanics on both sides of the boundary and stops.
- **Whether the sales cut-off is 15 minutes before or after the advertised start.** `PROVISIONAL`
  (`SRC-003 OPEN-BOOK-03`). Every `Closed` marking a guest sees in walk 1 step 1.9, and the
  `next_date_with_showtimes` button in step 1.8, move by half an hour if the client reverses it.
- **Which sorts a customer may choose.** `OPEN-SORT-01`, filed, open. The guest cannot sort at all in
  v1 and no control renders.
- **What a format is.** `OPEN-FORMAT-01`, filed, open. The format filter is required by a frozen
  clause; no value vocabulary exists, so the control does not render until an admin creates two.
- **Nothing in this walk was executed.** No application code exists. Every statement here is read from
  the specification, not observed, and the seam behaviour is **reasoned, not measured**.
