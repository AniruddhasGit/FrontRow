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
