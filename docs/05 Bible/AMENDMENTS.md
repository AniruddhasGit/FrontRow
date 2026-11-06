# Bible amendments

One line per amendment to an `AcceptanceCriteria` cell of `FrontRow_Bible.csv`. Each line names the
higher source that decides it (`CONSTITUTION.md` Art II.1: SRC-001, SRC-002, client ruling, APPROVED
ADR, PRD, BRD, Bible) and the Bible text it overrules. The ledger and `docs/08 SIT/SIT_TestCases.tsv`
are regenerated from the Bible after each batch (`generate_ledger.py`, `build_sit.py`), so they follow.

## 2026-10-18, round 3 doc-reconcile

- S-SCP-06: register with `role: staff` now returns 201 and a `customer` row, not 400 REQUEST_INVALID. Source: PRD EP-ACC-01 block (errors list has no REQUEST_INVALID; "never read from the request body") with PRD S1.2 rank 1 (the block decides the status code), agreeing with S-ACC-01.
- S-SEA-07: an absent SEAT_HOLD_TTL_SECONDS boots with 180 and no longer exits. Source: PRD S7.9 defaults table (the default is the ruled value) and SRC-002 §7.1 (only a *required* variable crashes boot).
- S-SEA-11: an absent SALES_CUTOFF_MINUTES boots with +15. Source: PRD S7.9 defaults table.
- S-SEA-15 (a): an absent REDIS_CONNECT/COMMAND_TIMEOUT_MS boots with 500. Source: PRD S7.9 defaults table. The cell already said "(default 500)".
- S-SEA-15 (b): "command log for the failing request being empty" is now "holding only the one attempted command whose failure raised, and nothing after it". Source: PRD P-HLD-10 ("a Redis failure caught in an exception handler must not read Redis *again*"). An empty log cannot exist, because the failure is only discovered by attempting a command.
- S-BRW-10: SALES_CUTOFF_MINUTES unset boots with +15; 'fifteen' still exits naming the variable. Source: PRD S7.9 defaults table.
- S-BRW-15: SEATMAP_POLL_INTERVAL_SECONDS missing boots with 3; non-integer still exits. Source: PRD S7.9 defaults table.
- S-PAY-01 (a): CURRENCY_MINOR_UNIT_RATIO unset boots with 100; 0 or non-integer still exits. Source: PRD S7.9 defaults table.
- S-PAY-01 (b): `LIKE '%_paise'` is now `LIKE '%paise%'`, so the query can return base_price_paise_applied, which the same cell requires. Source: PRD P-PAY-02 / E3 column names (base_price_paise_applied does not end in _paise).
- S-SEA-18: the stress script sends the Cookie (fr_session) and Content-Type headers, plus the Host and Content-Length that HTTP/1.1 requires, instead of "only Authorization and Content-Type". Source: PRD P-ACC-05 (the session is a cookie and never an Authorization header). P-HLD-13 names no headers.
- S-SEA-19: "all 24 rows" is now P-HLD-14's 27 entries (24 numbered rows plus 2b, 3b and 4b), each asserted where it is emitted. Rows 4, 4b and 18 are asserted on the confirm, and row 10 is a client banner. Source: PRD P-HLD-14 table.
- S-XCT-03: the `FOR UPDATE` sweep now excludes `domain/admin`, so the screen-row lock is no longer a violation. Source: PRD P-ADM-13 (every admin hall and seat write takes FOR UPDATE on its screen row).
- S-PAY-04: `FAIL_` in the rg became `["']FAIL_`, which matches only a quoted literal. Source: PRD S7.9. The variable name PAYMENT_SIMULATOR_FAIL_KEY_PREFIX contains FAIL_, and every module that reads it would otherwise be a hit.
- S-XCT-42: the refund and withdraw sweep now allows PRD-published copy and vocabulary: the SCR-TKT-01 policy line, the E4 receipt line, the hall and film withdrawal confirmations ("nothing is refunded"), and the *.withdrawn audit actions. It still forbids any identifier, route or function, and any withdraw line that matches showtime. Sources: PRD P-PAY-12, E4 receipt template, E6 SCR-ADM-05 / P-ADM-16 copy, S-ADM-02 audit vocabulary. Each requires a string that the old 0-hit rule forbade.
- S-PAY-11: frontend 'refund' hits may also be the published admin withdrawal confirmations. Before, it was "exactly 1". Source: PRD E6 SCR-ADM-05 copy ("...and nothing is refunded."), which S-ADM-17 requires to render in frontend/src.
- S-ADM-20: "exactly two published copy lines" is now "only published copy lines", which adds the E6 withdrawal confirmations. Source: PRD E6 SCR-ADM-05 copy, also required by S-ADM-17 in this same epic.
- S-SCP-12: backend/tests/ is added to the card-pattern rg paths. Source: the cell's own text ("backend/tests/ must stay IN scope"), applying the stricter of its two readings (Art II.1 "stricter always wins").
- S-XCT-12 (a): the two 422 password sentences are now P-ACC-01's published sentences (rows 4 and 5, with the byte count 75 interpolated). Source: PRD P-ACC-01 (rank 2 owns the exact words).
- S-XCT-12 (b): the to_thread rg path `backend/app/api/routes/auth.py` is now `backend/app/api/auth.py backend/app/domain/accounts`. Source: SRC-002 §11.1 (routers sit directly in backend/app/api, logic in backend/app/domain; there is no routes/ directory).
- S-XCT-10: the role-check rg path `backend/app/api/routes` is now `backend/app/api` with deps.py excluded. Source: SRC-002 §11.1.
- S-XCT-29: .env.example equals the settings model plus S7.9's seed-only variables. Source: PRD S7.9 ("Read by the seed script only" table, plus ".env.example is complete: every variable"). The API must not require the seed variables.
- S-XCT-43: the .pem/.crt/.key check may walk the working tree where git is absent. A tree walk is a superset of the tracked paths. Source: the cell's own aim (test file names, not contents); the walk is the stricter mechanism (Art II.1).
- S-PAY-09: "invalid input syntax for type integer" is now "type bigint". Source: APPROVED ADR FR-ADR-017 (every primary key is bigint), and docs/06 schema.sql.
- S-ADM-15: the T0+120s quote now uses a Premium and a Standard seat other than C12/C13, which the T0+95s confirm has sold. Source: SRC-001 §2.2 (a seat is never sold twice). The PRD P-ADM-12 worked example has the same slip; see the open list below.
- S-BRW-02: "card text content is exactly the movie title" is now "poster box's text content". Source: PRD P-BRW-02 exception 1 (the poster box draws the motif with the title inside it). The card also carries the synopsis and the metadata.
- S-BRW-04: the Asia/Kolkata rg now allows lines carrying P-ADM-25's published zone sentence. Source: PRD E6 P-ADM-25 row 4 / SCR-ADM-08 ("...such as Asia/Kolkata."), which the server must render.
- S-SCP-02: "exactly three compose services" is now the six that S-XCT-36 names, three of them application processes. Source: SRC-002 §12.2 (the local docker-compose runs Postgres and Redis).
- S-SEA-01, S-SEA-12, S-SEA-20, S-ACC-14, S-ACC-15, S-XCT-38: the accessible-name ending `held by another customer` is now `held by someone else`. Source: PRD SCR-BRW-03 copy table. E2 P-SEA-01 itself says the seat-map strings "are the same strings SCR-BRW-03 publishes", so E2's `held by another customer` (P-SEA-01 row 2) is a rank-4 restatement (PRD S1.2).

## 2026-11-07, client approvals (SRC-008 NIGHT-1)

The client approved CR-002 ("Approve CR-002") and the move of the ₹ criteria to US dollars ("Amend both to USD").
`SRC-008 ROLE-1` and its ADDENDUM rule the admin grant. CR-003 (accepted 2026-11-06) supplies the hall rows. Each
CR-002 line names the item whose wording it applies (`docs/15 ChangeRequest/CR-002_ac-defect-fixes.md`).

### CR-002 (Source: CR-002, approved by SRC-008 NIGHT-1)

- S-PAY-02: the `10000|5000` sweep now excuses a whole-line `*_MS` / `*_SECONDS` duration constant, and nothing else. Source: CR-002 A-1.
- S-XCT-03: the `FOR UPDATE` sweep is now an allow-list over `FOR UPDATE|with_for_update\(`, with the file and the locked table per row. It has no `domain/admin` exemption and allows no lock on booking_seat or showtime_seat. Source: CR-002 A-2.
- S-PAY-07: the seat `FOR UPDATE` sweep is replaced by "the S-XCT-03 allow-list holds". The bookings.py one-hit clause stays. Source: CR-002 A-2.
- S-TKT-06 (a): the scheduler-word sweep scans the shipped trees, not `backend/tests/`, and no test may import a scheduler. Source: CR-002 A-3.
- S-TKT-06 (b), S-TKT-07: the `now\(\)` sweep is now `rg -niP` with a `(?<![.\w])` lookbehind, plus the three PostgreSQL clock functions it missed. Source: CR-002 A-4.
- S-SEA-08: the wall-clock sweep drops `time\.sleep\(` and adds `datetime.today`, `date.today` and `time.time_ns`. Every sleep must now sit in a poll loop bounded by a count, checked with `ast`. Source: CR-002 A-5.
- S-XCT-48: the bcrypt-hash scan covers what `git ls-files` lists (or, with no git, the tree outside `.git/` and `.claude/`), docs included. The self-check over docs/05 Bible/ stays. Source: CR-002 A-6.
- S-SCP-11: the `\bpos\b` sweep is now the point-of-sale pattern. The mapper listener is replaced by three checks: a census of the two booking_seat writers, a Core `before_cursor_execute` trace of the confirm (`app.domain.`), and the seed's COPY count. Source: CR-002 A-7.
- S-ADM-09: the showtime-insert census is `(?i)INSERT INTO showtime\b|insert\(showtime\)`, hitting exactly `domain/admin/showtimes.py` and `scripts/seed.py`. Source: CR-002 A-8.
- S-ADM-23: the movie-insert census is `INSERT INTO movie\b[^_]|insert\(movie\)`, hitting exactly `domain/admin/films.py` and `scripts/seed.py`. ON CONFLICT is barred on the movie table only; join tables are excluded. Source: CR-002 A-9. The client's approval of CR-002 is the one-line ruling A-9 asked for.
- S-XCT-05 (a): three clauses change. The money-column query accepts only `_paise(_applied)?$`. The `uplift_basis_points` sweep bars arithmetic only. The pricing-import list names the five real importers, and the receipt render and the reports domain import nothing from pricing. Source: CR-002 A-10.
- S-PAY-11: the `withdraw` allow-list becomes "no hit on a line matching showtime", plus a walk of the routes and schemas, and no withdraw, cancel or DELETE operation under /api/admin/showtimes. Source: CR-002 A-11.
- S-ADM-12 (a): the money constants are `CURRENCY_MINOR_UNIT_RATIO` and `CURRENCY_CODE` in `backend/app/core/config.py`. The `[*/]\s*100\b` sweep excludes config.py and domain/money.py. Source: CR-002 A-12. The code value is USD (see below).
- S-XCT-20 (a): the Redis-timeout rg scans `backend/app` and expects one construction site. The no-fallback rg scans `domain/holds/` and adds `with_for_update`. Source: CR-002 A-13.
- S-XCT-20 (b): POST /api/bookings now answers with the P-HLD-14 CONFIRM_REDIS_DOWN sentence, and the payment count stays unchanged. Source: CR-002 B-3.
- S-ACC-07: the reset link is `/account/reset/confirm#token=`. The screen reads it from `location.hash` and removes it after reading, asserted on the rendered email. The last sentence now begins "The rest of what the worker puts in the email". Source: CR-002 B-1. **PRD P-ACC-07 still says `?token=`; this batch does not edit it.** *Later on 2026-11-07: the PRD now says `#token=` at all four places in FrontRow_PRD.md and the four in sections/E5_account.md, citing CR-002 B-1.*
- S-ADM-20: the cancelled_at sweep names "the module under backend/app/models/ that declares the booking table". The refund copy list adds SCR-ADM-02's film withdraw confirmation. Source: CR-002 B-2.
- S-XCT-19: the release step is the compare-and-delete EVAL, never a bare DEL of a `lock:` key, and SET NX < COMMIT is asserted. Source: CR-002 B-4.
- S-ADM-04: with CINEMA_TIMEZONE unset the process boots with Asia/Kolkata. A value that does not resolve still exits, naming the variable. Source: CR-002 B-5.
- S-BRW-09: date=2026-08-17 returns the 09:00 showtime with next null. The empty-state copy moves to date=2026-08-18. Source: CR-002 B-6.
- S-SCP-01: POST /api/admin/movies/import returns 404 NOT_FOUND through the 405 handler when the path parameter fails its type, and the movie count is unchanged. Source: CR-002 B-7.
- S-XCT-10: "four routers" becomes one deps.py dependency per non-public router, with the admin sub-routers inheriting require_admin and a fixed public set. Source: CR-002 B-8.
- S-ACC-06: the users-mapper listener becomes a Core `before_cursor_execute` listener that records the SET columns of each UPDATE. Source: CR-002 B-9.
- S-SCP-14: "after the full suite" becomes the teardown of every module that writes a booking, through one shared conftest fixture. Source: CR-002 B-10.
- S-ADM-22: the audit count filters on `entity_type = 'language'`. Source: CR-002 B-11.
- S-XCT-25: the request_id lives in `outbox_message.payload`, queried by topic and by the payload's booking_id. Source: CR-002 B-12.
- S-ADM-28: "poster reference and runtime_minutes" becomes the byte-identical title, plus a statement-listener check that the query has no published_at condition. Source: CR-002 C-2.

### US dollars (Source: SRC-006 CUR-1, amendment approved by SRC-008 NIGHT-1)

The integers, the ratio of 100 and Asia/Kolkata are unchanged. The `*_paise` names stay, because SRC-006 makes a rename a migration.

- S-ACC-11: the string that must never be rendered, `"₹1,530.00"`, is now `"$1,530.00"`.
- S-ADM-12 (b): the two paise messages are now the cents sentences the code publishes, the interface converts dollars to cents, and CURRENCY_CODE is USD.
- S-BRW-13: `'Premium  $281.24'` and `'$0.00'`. The pending legend row and the raw JSON must contain no `$`.
- S-PAY-01: CURRENCY_CODE=USD; 275.00 and 1,661.46 dollars; "no dollar sign". The rg proving the API and domain format no money is now `rg -nP '\$(\{|\d)'` (a `$` before a digit or an interpolation), because a bare `$` would hit the regex end anchors in api/browse.py. **[JUDGMENT CALL] This pattern is the build session's translation of `rg -n '₹'`.**
- S-PAY-08: currency_code USD.
- S-PAY-13: `$1,661.46` with en-US grouping, the label `'Pay $1,661.46'`, and the accessible name `'Pay 1,661 dollars 46 cents'`, as checkout.ts renders it.
- S-RPT-06: `$27,833.31`, and no JSON string value contains `$`.
- S-RPT-19: `$27,833.31` with en-US grouping, `$0.00` twice, and no JSON string value contains `$`.
- S-RPT-20: the takings accessible name ends "dollars and thirty-one cents".
- S-RPT-21: `$250.00` and `$300.00` appear nowhere.
- S-SEA-03: every running total uses `$`, with en-US grouping and the `$` symbol.
- S-TKT-09: the plain-text line is `Paid      $843.72`, and both parts carry `$843.72`. The `Rs` form existed only because ₹ is not ASCII. **The cell compares against the PRD's E4 Copy block byte for byte, and that block still says `Rs 843.72`; this batch does not edit it.** *Later on 2026-11-07: the E4 Copy block and its prose now say `$843.72` (SRC-006 CUR-1), and tests/tkt/test_s_tkt_09.py compares its literal to that block.*
- S-XCT-05 (b): CURRENCY_CODE=USD, and the ratio must be 100 while the code is USD.
- S-XCT-08: `for $281.24`.
- S-XCT-29: CURRENCY_CODE = USD.

### Hall shapes (Source: CR-003)

- S-XCT-44: CR-003's drawn rows replace the old shapes. Out: the 9x10 to 11x20 grids, the rows x columns and three-band self-check, Screen 1's row J, the labels A1/A10/J20, and the `ceil(rows * 0.5)` / `ceil(rows * 0.3)` band rule. In: Screen 1 rows A-H; labels A1, A11 and N19; each row's category as CR-003 draws it; Screen 1 Standard A-D (47), Premium E-G (37), Recliner H (6).

### New story (Source: SRC-008 ROLE-1 and its ADDENDUM)

- S-ADM-30 (new, E-ADM-A, milestone 2): an admin-only Settings section grants and removes admin access by email.
  - Each add and each removal writes its audit row in the same transaction.
  - A granted email (trimmed, case-insensitive) becomes admin at register or sign-in.
  - A role in a request body is ignored.
  - Removing an email demotes its account to customer at once.
  - A granted manager becomes admin and keeps its hall assignments.
  - The seeded admin is not on the list, and an admin cannot remove their own email.
- S-SCP-06, S-SEA-07: checked, not edited. The 2026-10-18 batch above already brought both into line with SRC-008: a role in the request is ignored and the account is a customer, and an absent SEAT_HOLD_TTL_SECONDS boots with 180.

### Approved, but CR-002 itself applies no cell change

- B-13 / Q-R3-05 (S-SEA-08, a token containing `/`): a code fix, no AC change.
- C-1 / Q-R3-03 (S-SEA-09, `Up to 6 seats.`): a contract change to EP-BRW-06. The cell stays.
- Group D (S-SEA-18, S-BRW-18, the last clause of S-XCT-43, T-P1-08, T-P1-09): not defects. They wait for AWS.
- Group E: stale ledger StatusNotes, not cells. The owning lanes update the notes.

## Raised, not amended (no higher source decides it, or the fix is product behaviour)

These are open questions for the client or the merge owner. They are written here and not appended to
`CLIENT_ASK.md`, because CONSTITUTION Art II.9 keeps that file "exactly as the client handed it over".

- Q-R3-01 Pricing constant names. S-ADM-13 says BASIS_POINT_SCALE / BASIS_POINT_HALF and S-PAY-02 says BASIS_POINTS_DENOMINATOR / ROUNDING_HALF_NUMERATOR. These are Bible equals, and neither the PRD (E3 P-PAY-03/04, E8 P-XCT-02) nor any ADR names the constants. Recommendation: keep S-ADM-13's pair and amend S-PAY-02.
- Q-R3-02 Milestones. S-XCT-33 and S-XCT-49 (Milestone 2) need the worker command, and S-PAY-11 (Milestone 4) needs the receipt template. Both arrive in Phase 5 (SRC-002 §12.6). The Bible's own rule says a story may not sit before what it depends on, but S-XCT-33's no-migrate-on-boot clause must hold from Phase 2. Recommendation: split the worker and receipt clauses into Phase 5 rows. That changes the plan, so it is not done here.
- Q-R3-03 MAX_SEATS_PER_BOOKING has no endpoint field (S-SEA-09, SCR-SEA-01, S7.21). PRD S1.2.1 case 2: a screen renders a figure that no response returns. Recommendation: the PRD adds max_seats_per_booking to the seat-map body, as it already does for poll_interval_seconds.
- Q-R3-04 Copy gaps. There is no published plural for P-SEA-03's "C12 is no longer available" (S-SEA-04), no sentence for three or more lost seats in P-HLD-14 rows 3 and 3b ("change these two"; S-SEA-12), and no sentence for a dropped connection on SCR-PAY-01 / S-PAY-14. Customer copy belongs to the PRD (rank 2), and the lanes' interim strings are their own judgment calls.
- Q-R3-05 S-SEA-08 token containing '/'. PRD P-HLD-03 and the EP-HLD-02 block both say 400 REQUEST_INVALID, so the Bible is right and was not edited. The gap is in implementation: the router answers 404 for a two-segment path. A not-found handler for unroutable /api/holds/<43 chars> paths could answer 400 without changing the published routes. Otherwise the PRD has to accept 404 for that one shape.
- Q-R3-06 Compose profile services. S-XCT-35/36 (and now S-SCP-02) say "exactly six services", but docker-compose.yml also defines the frontrow_roles_init, migrate (profile tools) and test (profile test) services, and it names the static service `frontend`, not `web`. The Bible should say whether profile-gated tool services count.
- Q-R3-07 PRD self-inconsistencies, not owned here. P-ADM-12's worked example re-quotes C12/C13 at T0+120s after they are sold. P-SEA-01 row 2 restates `held by another customer`. P-XCT-19 says the migrate task "reads DATABASE_URL the same way", but it needs the owner role's URL. E3 P-PAY-12 row 2 ("any v1 endpoint" refuses status/cancelled_at with 400) conflicts with the EP-ACC-01 block, which has no 400.
