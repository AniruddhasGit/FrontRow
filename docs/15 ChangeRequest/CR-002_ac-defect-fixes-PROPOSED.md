# CR-002 — Acceptance-criteria defect fixes (PROPOSED, for the client to approve)

| | |
|---|---|
| **Raised** | 2026-11-06, by the build session (Round 4, Track D), from the ledger, `AMENDMENTS.md`, `round4_input.md` and the Round 4 batch 1 lane reports |
| **Status** | **PROPOSED.** Nothing in this file has been applied. The Bible, the ledger, the SIT file and every test are unchanged. |
| **Who decides** | The client (`CONSTITUTION.md` Art II.1: an `AcceptanceCriteria` cell is overruled only by a higher source or a client ruling). Amending what "done" means is a reserved matter (`CLAUDE.md`, *Reserved*), so the build session drafts and does not decide. |
| **How it lands** | One approved item becomes one line under a new dated heading in `docs/05 Bible/AMENDMENTS.md`, the cell is edited in `FrontRow_Bible.csv`, and `generate_ledger.py` / `build_sit.py` regenerate the derived files, as in round 3. |

## How to read each item

Each item gives:

- **Current clause**: quoted exactly from `docs/05 Bible/FrontRow_Bible.csv` as it stands on 2026-11-06.
- **Why it cannot pass honestly**: the evidence, with a file and line or the doc it conflicts with.
- **Proposed clause**: the replacement text. It tests the same intent, and is never weaker on oversell, locks, integer paise, idempotency, authorisation, audit or card data. Where it changes a scan, it states which hits it stops counting and why none of them can be a violation.
- **Risk if left as is**: what happens if nobody amends it.

**The rule this CR follows** (`frontrow_aws/CLAUDE.md`, ponytail): never game a grep-based criterion. Code was not renamed, reworded or moved to make a scan go green. Where round 3 did that (`MUTEX_TTL_MS = 5 * 1000`, `threading.Event().wait()`, `self.instant = clock.now`, the reworded `FOR UPDATE` docstrings), batch 1 reverted it. Every red that came back is listed here instead.

**Evidence status.** The scans quoted below were re-run read-only on the working tree on 2026-11-06. Another build was editing that tree at the same time (Round 4 batch 2: core, reports and account). So a hit count can move before approval. Re-run each scan when an item is applied.

---

## Group A — grep/rg clauses that over-reach (or name paths that do not exist)

### A-1 · S-PAY-02 · the `5000` sweep catches a lock TTL

- **Current clause:** "`rg -n '\b10000\b|\b5000\b' backend/app/domain backend/app/api backend/app/workers --glob '!**/pricing.py'` returns 0 hits"
- **Why it fails:** `backend/app/domain/holds/__init__.py:138` `MUTEX_TTL_MS = 5000`. This is the per-customer hold mutex lifetime in milliseconds, not a basis-point constant. Round 3 hid it as `5 * 1000`. The round-3 verifier called that grep-gaming, and batch 1 reverted it.
- **Proposed clause:** "`rg -n '\b10000\b|\b5000\b' backend/app/domain backend/app/api backend/app/workers --glob '!**/pricing.py' | rg -v '^\S+:\d+:\s*[A-Z][A-Z0-9_]*_(MS|SECONDS)\s*=\s*\d+\s*(#.*)?$'` returns 0 hits. A hit is excused only when it is a whole-line assignment of a named duration constant whose name ends `_MS` or `_SECONDS`. Every other bare 10000 or 5000, in any expression, is a hit."
- **Why this is not weaker:** the money rule is that the denominator and the half are defined once, in `pricing.py`. The new clause still catches any `x * u / 10000`, `+ 5000` or `// 10000` written inline. It excuses only a line that defines a time constant and does no arithmetic.
- **Risk if left as is:** S-PAY-02 can only go green by disguising a lock TTL, which is the grep-gaming the constitution forbids.
- **Status:** PROPOSED

### A-2 · S-PAY-07 and S-XCT-03 · the row-lock sweeps (one replacement for both)

- **Current clauses:**
  - S-PAY-07: "`rg -n 'booking_seat[^;]*FOR UPDATE|seat[^;]*FOR UPDATE' backend/app` returns 0 hits"
  - S-XCT-03: "`rg -n 'FOR UPDATE' backend/app --glob '!**/domain/admin/**' | rg -v 'FROM showtime'` returns 0 hits, so every row lock outside the admin writes is taken on the showtime row and none on a seat-occupancy row that does not exist yet - the screen-row lock P-ADM-13 requires of every admin hall and seat write is the one other lock and is outside this check"
- **Why they fail:**
  1. **S-PAY-07** hits `backend/app/domain/admin/halls.py:8`. That is a docstring that truthfully describes the P-ADM-13 lock on the **screen** row.
  2. **S-XCT-03 now hits three lines that other criteria require:**
     - `backend/app/workers/__init__.py:4` and `:75`, the outbox relay's `FOR UPDATE SKIP LOCKED`. **S-TKT-06 requires this** in its own text: "selects the row with FOR UPDATE SKIP LOCKED in a bounded batch".
     - `backend/app/api/receipts.py:135`, `FOR UPDATE OF rd`, the receipt_dispatch row lock taken on resend.
  3. **S-XCT-03 also misses locks it should catch.** It searches only for the text `FOR UPDATE`, so it cannot see SQLAlchemy `.with_for_update()`. Eight of the eleven locks in `backend/app` are written that way: `domain/admin/{cinemas,films,halls x2,managers,lookups,showtimes,seat_categories}.py`.
  4. **The round-3 `--glob '!**/domain/admin/**'` exemption is wider than P-ADM-13 needs.** A stray seat-occupancy lock in admin code would go unseen (round-3 verifier finding).
- **Proposed clause (one clause, placed in S-XCT-03; S-PAY-07 then refers to it):** "Every hit of `rg -n 'FOR UPDATE|with_for_update\(' backend/app`, excluding comment and docstring lines, is a row of this allow-list. Each row names the file and the one table it locks:
  - `api/bookings.py`: `showtime`, the confirm
  - `domain/admin/*`: `screen`, `seat`, `showtime`, `movie`, `cinema`, `users`, `seat_category` and the four lookup tables. These are version-checked admin edits (P-ADM-13, FR-ADR-019).
  - `workers/__init__.py`: `outbox_message`, with `SKIP LOCKED` (S-TKT-06)
  - `api/receipts.py`: `receipt_dispatch` (P-TKT-05)

  No hit locks `booking_seat` or `showtime_seat`. The check is a test that runs the rg, parses the locked table from each hit, and fails on any row not in the list, or on any lock of `booking_seat` or `showtime_seat`. S-PAY-07 keeps its other clause, `rg -n 'FOR UPDATE' backend/app/api/bookings.py` returning exactly 1 hit on a line matching `showtime`, and replaces its seat sweep with: the S-XCT-03 allow-list holds."
- **Why this is not weaker:**
  - It now catches `with_for_update()` locks, which the current text cannot see.
  - It drops the blanket `domain/admin` exemption.
  - It still forbids any lock on a seat-occupancy table, which is the oversell invariant (SRC-001 §2.2: the UNIQUE constraint decides, never a lock).
  - Its only allowance is for a docstring line, which takes no lock.
- **Risk if left as is:** S-PAY-07 stays red on an honest docstring. S-XCT-03 stays red on locks that S-TKT-06 and P-TKT-05 require, and keeps passing over the `.with_for_update()` locks it cannot see.
- **Status:** PROPOSED

### A-3 · S-TKT-06 · the scheduler sweep catches the guard tests that quote it

- **Current clause:** "`rg -in -e apscheduler -e celery -e BackgroundScheduler -e croniter -e crontab -e 'schedule.every' -e 'add_job\(' backend/` returns 0 hits"
- **Why it fails:** `backend/` includes `backend/tests/`. These seven guard tests quote the forbidden words in order to assert they are absent: `tests/adm/test_s_adm_09.py`, `test_s_adm_19.py`, `test_s_adm_23.py`, `tests/xct/test_s_xct_36.py`, `test_s_xct_37.py`, `tests/sea/test_s_sea_07.py` and `tests/scp/test_s_scp_02.py`. The only fix inside the clause as written is to rebuild every other lane's pattern from fragments.
- **Proposed clause:** "`rg -in -e apscheduler -e celery -e BackgroundScheduler -e croniter -e crontab -e 'schedule.every' -e 'add_job\(' backend/app backend/migrations backend/requirements.txt backend/entrypoint.sh backend/Dockerfile` returns 0 hits. `rg -n '^\s*(import|from)\s+(apscheduler|celery|croniter)\b' backend/tests` returns 0 hits, so no test imports a scheduler. `backend/` contains no file named `beat.py`, `scheduler.py` or `crontab`."
- **Why this is not weaker:** every tree that ships, or installs a dependency, is still scanned for the words. The tests are still barred from importing a scheduler. Only a quoted string inside a guard assertion stops counting.
- **Risk if left as is:** permanent red, or fragment-assembled patterns spread across six lanes' test files to satisfy one row.
- **Status:** PROPOSED

### A-4 · S-TKT-06 and S-TKT-07 · `now\(\)` catches the injected clock the same clauses require

- **Current clauses:**
  - S-TKT-06: "`rg -n 'now\(\)|CURRENT_TIMESTAMP|statement_timestamp' backend/app/workers` returning 0 hits"
  - S-TKT-07: "`rg -n 'now\(\)|CURRENT_TIMESTAMP' backend/app/workers` returning 0 hits"
- **Why they fail:** the injected clock is called as `self.clock.now()` (`backend/app/workers/__init__.py:12, 100, 112, 138, 166, 192, 216`), so the pattern hits it. The clause is aimed at the SQL `now()` function, the database's clock. Round 3 hid the call behind an alias (`self.instant = clock.now`), and batch 1 reverted that.
- **Proposed clause (both rows):** "`rg -niP '(?<![.\w])now\(\)|CURRENT_TIMESTAMP|statement_timestamp|clock_timestamp|transaction_timestamp|LOCALTIMESTAMP' backend/app/workers` returns 0 hits. The lookbehind excludes a method call such as `clock.now()` and nothing else."
- **Why this is not weaker:** it is stricter. It adds the three PostgreSQL clock functions the current pattern misses, plus case-insensitivity, so `NOW()` written in SQL is caught too.
- **Risk if left as is:** the worker must hide its clock to pass, which hides exactly what the criterion is meant to see.
- **Status:** PROPOSED

### A-5 · S-SEA-08 · `time.sleep(` is treated as a clock read

- **Current clause:** "no test in this story reads the wall clock, asserted by `rg -n 'time\.sleep\(|datetime\.now\(|datetime\.utcnow\(|time\.time\(' backend/tests/` returning 0 hits"
- **Why it fails:**
  - `time.sleep` waits. It reads no clock.
  - The scan is repository-wide, so it hits other lanes' polls of external processes: `tests/adm/test_s_adm_06.py:149`, `test_s_adm_09.py:130`, `test_s_adm_16.py:57`, `tests/pay/test_s_pay_04.py:104`, `tests/sea/kit.py:256`, `tests/sea/drill_live.py:52`, `tests/sea/test_s_sea_17.py:116`, `tests/test_shutdown.py:64,115`, and `tests/xct/test_s_xct_21.py:140`, `_24.py:52`, `_29.py:192`.
  - **S-SEA-08's own text requires a wait.** It says "polling `EXISTS lock:seat:77:402` until it returns 0 so that Redis's own TTL removed them".
  - The round-3 `threading.Event().wait()` stand-ins hid the same wait under another name, and batch 1 reverted them.
- **Proposed clause:** "No test reads the wall clock, asserted by `rg -n 'datetime\.now\(|datetime\.utcnow\(|datetime\.today\(|date\.today\(|time\.time\(|time\.time_ns\(' backend/tests/` returning 0 hits. Every `time.sleep(` under `backend/tests/` sits inside a loop that polls an external process or Redis (an HTTP readiness probe, a container, a database transaction, or an `EXISTS`), and that loop is bounded by an iteration count rather than by a clock reading. A test asserts this by parsing each hit's enclosing `for`/`while` with `ast` and finding a bounded `range(...)` or counter."
- **Why this is not weaker:** every wall-clock read is still forbidden, and it now covers `date.today` and `time_ns` too. A sleep can no longer stand in for an expiry, because it must sit in a poll loop bounded by a count. S-XCT-19's real-elapsed-time staleness check is unaffected, because it is a different row.
- **Risk if left as is:** S-SEA-08 can never be Done without renaming waits, which is grep-gaming.
- **Status:** PROPOSED

### A-6 · S-XCT-48 · the committed-hash scan walks untracked agent worktrees

- **Current clause:** "`rg -nP '\$2[aby]\$\d\d\$' .` returns 0 hits, so no hash is committed either - this scan stays over the whole repository, documentation trees included"
- **Why it fails:** the test's `rg()` helper (`backend/tests/xct/_support.py:32`) walks every file, `.claude/` included. That folder holds untracked agent worktrees with stale evidence copies. One hit: `.claude/worktrees/agent-a4aed4da5dccf7ca1/docs/10 EngineeringLedger/evidence/PHASE2_wl883ib1u.md`. Real `rg` skips hidden directories by default, so the AC as written and the test disagree. Neither one checks the stated intent, which is "committed".
- **Proposed clause:** "No committed file holds a bcrypt hash, asserted by running the pattern `\$2[aby]\$\d\d\$` over the content of every path `git ls-files` lists (or, where the image has no git, every file under the working tree outside `.git/` and `.claude/`), returning 0 hits. Documentation trees stay in scope. The self-check over `docs/05 Bible/` is unchanged."
- **Why this is not weaker:** the scope is now exactly "committed", which is what the clause claims to prove. It includes any hidden tracked file that real `rg` would skip, so it is stricter than rg's defaults.
- **Risk if left as is:** the row goes red or green depending on which agent worktrees happen to be on disk.
- **Status:** PROPOSED

### A-7 · S-SCP-11 · `\bpos\b` hits a byte offset, and the "mapper" listener has no mapper

- **Current clause:** "`rg -niE '\bpos\b|\btill\b|counter_?sale|terminal_?sale' backend/app/ frontend/src/` returns 0 hits ... and a test registers a SQLAlchemy before_insert event listener on the booking_seat mapper, records inspect.getmodule(frame_info.frame).__name__ for every frame of the call stack at each insert across a run that exercises both the booking confirmation path and scripts/seed.py, and asserts the resulting set of originating modules has len() == 2, contains scripts.seed, and has as its only other member a module whose name starts with backend.app.domain."
- **Why it fails, three ways:**
  1. `backend/app/domain/posters.py` has 16 hits, all on `pos`, a local byte offset in the PNG/JPEG header walkers. It is not point-of-sale, and it was not renamed just to pass.
  2. There is no ORM mapper. The schema is SQLAlchemy Core tables (`docs/06 schema.sql`, `backend/migrations/versions/0001_initial_schema.py`), and `scripts/seed.py:362` writes `booking_seat` with psycopg `COPY ... FROM STDIN`, which no SQLAlchemy listener sees.
  3. Modules are named `app.*`, not `backend.app.*` (SRC-002 §11.1 layout; `from app.domain...` throughout).
- **Proposed clause:**
  - "`rg -niP 'point[-_ ]?of[-_ ]?sale|\bpos[-_/]|[-_/]pos\b|\bpos(terminal|sale|_?id)\b|\btill\b|counter_?sale|terminal_?sale' backend/app/ frontend/src/` returns 0 hits, and S-SCP-01's mounted-path regex still refuses any route path matching `pos/`."
  - "Exactly two code sites write `booking_seat`: `rg -n -i 'insert\(booking_seat\)|INSERT INTO booking_seat|COPY booking_seat' backend/app scripts` hits exactly one file under `backend/app/domain/` and `scripts/seed.py`."
  - "At run time, a Core `before_cursor_execute` listener on the engine records `inspect.getmodule(...).__name__` for every frame at each `INSERT INTO booking_seat` across a full confirm. The set of originating application modules is exactly one module whose name starts with `app.domain.`."
  - "The seed's COPY is asserted separately: after a seed, `SELECT count(*) FROM booking_seat` equals the seed's reported booked-seat count."
- **Why this is not weaker:** both writers are still pinned, one by a runtime trace and one by a code census. Any `pos_`, `/pos`, `possale`, `pos_id` or "point of sale" is still caught. The only thing that stops counting is a bare word `pos`, standing alone as an identifier. That residual is named here: a bare `pos` variable that did mean point-of-sale would slip through. S-SCP-01's route check backs this up.
- **Risk if left as is:** permanent red, or a rename done only to pass the scan.
- **Status:** PROPOSED

### A-8 · S-ADM-09 · the showtime-insert census names a file that does not exist and a pattern the code cannot match

- **Current clause:** "Ripgrep over backend/app backend/migrations and scripts/ for the pattern INSERT INTO showtime|Showtime[(] returns hits in exactly three files - backend/app/api/admin/showtimes.py, backend/app/domain/showtimes.py and scripts/seed.py - and 0 hits under backend/app/workers and backend/app/jobs"
- **Why it fails:**
  - `backend/app/domain/showtimes.py` does not exist. The domain is `backend/app/domain/admin/showtimes.py`, as the ledger's OwnedPaths and FR-ADR-022 (rules live in domain) require.
  - The insert is SQLAlchemy Core `insert(showtime)`, which the pattern cannot see.
  - Today the pattern hits `scripts/seed.py`, `backend/app/domain/reports/__init__.py`, `backend/app/domain/browse/seatmap.py` and `backend/app/domain/admin/showtimes.py`. The middle two hit on `Showtime(`, a dataclass or type name, not an insert.
- **Proposed clause:** "Ripgrep over backend/app backend/migrations and scripts/ for the pattern `(?i)INSERT INTO showtime\b|insert\(showtime\)` returns hits in exactly two files, `backend/app/domain/admin/showtimes.py` and `scripts/seed.py`, and 0 hits under backend/app/workers and backend/app/jobs."
- **Why this is not weaker:** it now matches the insert form the code actually uses, so it is stricter. Dropping `Showtime[(]` removes only matches on a type name, which never insert a row.
- **Risk if left as is:** the clause is unpassable. Worse, a reader may "fix" it by adding a `Showtime(` call to a handler.
- **Status:** PROPOSED

### A-9 · S-ADM-23 · the movie-insert census, and an ambiguous ON CONFLICT clause

- **Current clause:** "... for the pattern ON CONFLICT within any statement naming movie returns 0 hits ... and ripgrep over backend/app backend/migrations and scripts/ for the pattern INSERT INTO movie\b|Movie[(] returns hits in exactly two files - backend/app/api/admin/movies.py and scripts/seed.py"
- **Why it fails:**
  1. The admin insert is Core `insert(movie)` in `backend/app/domain/admin/films.py` (FR-ADR-022). The pattern cannot see it, and `api/admin/movies.py` holds no insert.
  2. `scripts/seed.py:245` `INSERT INTO movie_genre ... ON CONFLICT DO NOTHING` "names movie" if `movie` is read as a substring. It does not if `movie` is read as the table.
- **Proposed clause:**
  - "... `rg -n -i 'INSERT INTO movie\b[^_]|insert\(movie\)' backend/app backend/migrations scripts/` returns hits in exactly two files, `backend/app/domain/admin/films.py` and `scripts/seed.py`, and 0 hits under backend/app/workers and backend/app/jobs."
  - "No statement that inserts into the `movie` table carries ON CONFLICT, asserted by `rg -n -i 'INSERT INTO movie\b[^_][^;]*ON CONFLICT' backend/app scripts` returning 0 hits. Join tables such as `movie_genre` are outside this check, because their ON CONFLICT DO NOTHING makes the seed idempotent and creates no film."
- **Why this is not weaker:** the film table itself is still guarded, so a duplicate film can never be swallowed. The join-table reading is the one the PRD intends: P-ADM-01 says title is not unique, so an upsert on `movie` is what is barred.
- **Risk if left as is:** unpassable, and the ambiguity invites a seed rewrite that changes nothing about film creation.
- **Status:** PROPOSED (the ON CONFLICT reading also needs a one-line ruling; see the recommendation)

### A-10 · S-XCT-05 · three clauses the code cannot honestly meet

- **Current clauses:**
  1. "`column_name ~ '(price|amount|total)' AND (data_type <> 'bigint' OR column_name NOT LIKE '%\_paise')` returning 0 rows"
  2. "`rg -n 'uplift_basis_points' backend/app scripts --glob '!**/domain/pricing.py' --glob '!**/models/**' --glob '!**/migrations/**'` returns 0 hits"
  3. "`rg -l 'from app.domain.pricing import seat_price_paise' backend/app scripts` returns exactly five files - the seat-map read, the checkout total, the receipt render, the dashboard query and scripts/seed.py"
- **Why they fail:**
  1. `booking_seat.base_price_paise_applied` (`0001_initial_schema.py:357`) contains `price` and does not end in `_paise`. This is the same slip round 3 fixed in S-PAY-01(b).
  2. `uplift_basis_points` is the name of a column that other criteria require code to read and write:
     - S-ADM-13 is the CRUD on `seat_category.uplift_basis_points` (`domain/admin/seat_categories.py`, `api/admin/seat_categories.py`).
     - S-ADM-12 is the base-price bound "against the highest stored uplift" (`domain/admin/showtimes.py:62`).
     - The seed writes the categories (`scripts/seed.py:188, 318, 362`).

     S-PAY-02 already has the right check: no arithmetic on the identifier.
  3. The receipt render and the dashboard must **not** recompute a price. They read the stored `booking_seat.price_paise` snapshot (P-PAY-04, P-HLD-11: "re-read at confirm, never recomputed"). The five files that actually import the function are `scripts/seed.py`, `domain/booking`, `domain/browse/seatmap.py`, `domain/holds` (the hold-time snapshot) and `domain/admin/common.py` (the S-ADM-12 bound).
- **Proposed clauses:**
  1. "`... AND (data_type <> 'bigint' OR column_name !~ '_paise(_applied)?$')` returning 0 rows"
  2. "`rg -nP 'uplift_basis_points\w*\s*[-+*/%]|[-+*/%]\s*uplift_basis_points' backend/app scripts --glob '!**/domain/pricing.py'` returns 0 hits, so no caller does uplift arithmetic. Reading, storing and validating the column stays allowed."
  3. "Every file matching `rg -l 'from app.domain.pricing import' backend/app scripts` is one of: the seat-map read, the hold snapshot, the booking total, the admin base-price bound, and `scripts/seed.py`. The receipt render (`backend/app/workers/render.py`) and the reporting domain (`backend/app/domain/reports/`) import nothing from `app.domain.pricing` and read `booking_seat.price_paise` instead."
- **Why this is not weaker:**
  - Item 1 is stricter than the S-PAY-01(b) fix: only two exact suffixes pass.
  - Item 2 still bars every arithmetic use, and now catches `uplift_basis_points_applied` and `%` too.
  - Item 3 is stricter on integer paise. It forbids the two surfaces that most need the snapshot from re-deriving a price.
- **Risk if left as is:** the row is unpassable. To meet item 3 a lane would have to make the receipt recompute prices, which breaks the snapshot invariant.
- **Status:** PROPOSED

### A-11 · S-PAY-11 · the `withdraw` allow-list is narrower than the vocabulary the PRD requires

- **Current clause:** "rg -in 'withdraw' backend/app returns hits only on the four lookup audit actions language.withdrawn, certification.withdrawn, genre.withdrawn and format.withdrawn of the closed AuditAction enum S-ADM-02 publishes, with no hit on a line that also matches showtime"
- **Why it fails:** these Bible rows require other uses of the word:
  - S-ADM-22 requires the query flag `include_withdrawn` (`api/admin/lookups.py:24-29`, `domain/admin/lookups.py:47-52`).
  - S-ADM-28 requires the sentence "This film is not published, so there is nothing to withdraw." (`domain/admin/films.py:39`).
  - P-ADM-24 requires the withdrawn-duplicate sentence (`domain/admin/lookups.py:31`).
  - Module docstrings describe film and lookup withdrawal (`films.py:1, 242`, `lookups.py:1, 6, 7`).

  S-XCT-42 already holds the correct version of this rule: "returns no hit on a line that also matches showtime".
- **Proposed clause:** "`rg -in 'withdraw' backend/app` returns no hit on a line that also matches `showtime`. Every route path, function name and request-schema field containing `withdraw` concerns a film (`movie`) or a lookup entry, asserted by walking `app.routes` and the OpenAPI request schemas. The generated OpenAPI declares no DELETE operation, and no operation whose path contains `withdraw` or `cancel`, on any path beginning `/api/admin/showtimes`."
- **Why this is not weaker:** the invariant, that no route can strand a captured payment by withdrawing a showtime, is now checked on the route table and schemas, not just on text. That is stricter. The text rule is the same one S-XCT-42 uses.
- **Risk if left as is:** S-PAY-11 conflicts with three Bible rows in its own epic family and can never pass.
- **Status:** PROPOSED

### A-12 · S-ADM-12 · the money constants are specified in a file that does not exist

- **Current clause:** "The minor-unit ratio and the currency code each exist as one named configuration value, MINOR_UNIT_RATIO = 100 and CURRENCY_CODE = INR, both defined in backend/app/core/money.py; ripgrep over backend/app for the pattern [*/]\s*100\b, excluding backend/app/core/money.py, returns 0 hits."
- **Why it fails:** `backend/app/core/money.py` does not exist. Configuration values live in `backend/app/core/config.py` as `CURRENCY_MINOR_UNIT_RATIO` and `CURRENCY_CODE`. That is the name PRD S7.9 publishes and the name S-XCT-05 and S-PAY-01 already use. The strict money types live in `backend/app/domain/money.py`.
- **Proposed clause:** "The minor-unit ratio and the currency code each exist as one named configuration value, `CURRENCY_MINOR_UNIT_RATIO` (default 100) and `CURRENCY_CODE` (INR), the S7.9 names, both declared in `backend/app/core/config.py`. Ripgrep over backend/app for the pattern `[*/]\s*100\b`, excluding `backend/app/core/config.py` and `backend/app/domain/money.py`, returns 0 hits."
- **Why this is not weaker:** there is still exactly one definition and still no inline `* 100` or `/ 100`. Only the names and paths change, to the ones S7.9 already rules.
- **Risk if left as is:** S-ADM-12, S-XCT-05 and S-PAY-01 disagree on one constant's name and home.
- **Status:** PROPOSED

### A-13 · S-XCT-20 · two scan paths that do not exist

- **Current clause:** "asserted by rg -n 'socket_connect_timeout|socket_timeout' backend/app/core/redis.py returning both ... and rg -n 'FOR UPDATE|advisory_lock|pg_advisory' backend/app/domain/holds.py returns 0 hits"
- **Why it fails:**
  - `backend/app/core/redis.py` does not exist. The Redis client is built in `backend/app/main.py`, which is the only file that matches `socket_connect_timeout|socket_timeout`.
  - `backend/app/domain/holds.py` is a package, `backend/app/domain/holds/__init__.py`.
  - A scan of a missing path is an error, not a pass. The test helper raises on it on purpose (`_support.py:40`).
- **Proposed clause:** "`rg -n 'socket_connect_timeout|socket_timeout' backend/app` returns hits only at the one place the Redis client is constructed, and both names appear there, each read from a named configuration variable. `rg -n 'FOR UPDATE|with_for_update|advisory_lock|pg_advisory' backend/app/domain/holds/` returns 0 hits."
- **Why this is not weaker:** it is stricter. The check is not tied to a filename, and `with_for_update` is added to the no-PostgreSQL-fallback check.
- **Risk if left as is:** unpassable, or a file created only to give the scan something to read.
- **Status:** PROPOSED

---

## Group B — criteria that conflict with another document

### B-1 · S-XCT-43 vs S-ACC-07 and PRD P-ACC-07 · `?token=` vs `#token=` in the reset link

- **Current clauses:**
  - S-XCT-43: "nothing is designed around the absence of TLS, asserted by rg -nP '\?token=|access_token=|Authorization: Bearer' backend/app frontend/src returning 0 hits"
  - S-ACC-07: "the link the confirm screen accepts has the form {PUBLIC_BASE_URL}/account/reset/confirm?token=<the 43-character token>"
  - PRD P-ACC-07 (`docs/03 PRD/FrontRow_PRD.md:8412`, `:17977`, `:18209`, `:18242`; `sections/E5_account.md:697`): "`{PUBLIC_BASE_URL}/account/reset/confirm?token=<token>`"
- **Why it fails:** the three documents cannot all hold.
  - The code today follows S-XCT-43, as a logged judgment call: `backend/app/workers/render.py:106` builds `.../account/reset/confirm#token={token}`, and `frontend/src/features/auth/routes.tsx:16` reads `window.location.hash`. So S-XCT-43's rg passes (0 hits), while S-ACC-07 and the PRD sentence are not met.
  - If the code followed the PRD, S-XCT-43 would go red, as it did in round 3 (round-3 verifier, major).
  - The PRD outranks the Bible (Art II.1), but a fragment is the stricter choice. It is never sent to the server, so it never reaches access logs, the ALB, or a `Referer` header. TLS is unruled (OPEN-TLS-01), so over plain HTTP a query-string token travels on every hop.
- **Proposed change (PRD and Bible together):**
  - PRD P-ACC-07: replace `?token=<token>` with `#token=<token>` at all four places in `FrontRow_PRD.md` and the copy in `E5_account.md`, adding: "The token rides in the URL fragment, which the browser never sends to the server, so it is absent from every access log."
  - S-ACC-07 cell: "...has the form {PUBLIC_BASE_URL}/account/reset/confirm#token=<the 43-character token>, and the confirm screen reads it from `location.hash` and removes it from the address bar after reading, asserted by the rendered reset email body containing `/account/reset/confirm#token=` and not `?token=`".
  - S-XCT-43: unchanged.
- **Why this is not weaker:** it is stricter on secrets in transit. S-XCT-43's guard is kept in full, and S-ACC-07 gains a positive assertion.
- **Risk if left as is:** one of S-ACC-07 or S-XCT-43 is always red. A future lane "fixing" the link to match the PRD would put a live credential into server logs.
- **Status:** PROPOSED. **This changes a PRD sentence, so it needs the client's approval.**

### B-2 · S-ADM-20 vs S-ADM-17, S-ADM-28 and S-PAY-11 · the `refund` copy list, and a cancelled_at path

- **Current clause:** "ripgrep over backend/app and frontend/src for the pattern cancelled_at returns hits only in backend/app/models/booking.py and the Alembic migration that creates the column. Ripgrep over backend/app backend/migrations and frontend/src for the case-insensitive pattern refund returns hits only on published copy lines and on no code path - the SCR-TKT-01 line ..., the receipt's line ..., and the admin withdrawal confirmations E6 publishes, which contain nothing is refunded (SCR-ADM-05, S-ADM-17)"
- **Why it fails:**
  1. Round 3 amended S-PAY-11 and S-XCT-42 to allow "E6's film withdraw confirmation" (SCR-ADM-02, PRD `E6_admin.md:3577`). S-ADM-20 lists only SCR-ADM-05. `frontend/src/features/admin/FilmEditor.tsx:17` carries the SCR-ADM-02 line, so S-ADM-20's list is one entry short of its sibling rows.
  2. `backend/app/models/booking.py` does not exist. The Core table is declared in `backend/app/models/__init__.py`, which is today's only `cancelled_at` hit besides `0001_initial_schema.py`.
- **Proposed clause:**
  - "...returns hits only in the module under `backend/app/models/` that declares the `booking` table, and the Alembic migration that creates the column."
  - "...and the admin withdrawal confirmations E6 publishes, which contain nothing is refunded (SCR-ADM-05 for S-ADM-17, and SCR-ADM-02's film withdraw confirmation for S-ADM-28)..."
- **Why this is not weaker:** the rule is still copy only and no code path. Each allowed line is a PRD-published sentence that states the absence of a refund.
- **Risk if left as is:** S-ADM-20 conflicts with S-ADM-28's required copy.
- **Status:** PROPOSED
- **Note (not a doc defect):** `frontend/src/features/ticket/ticket.test.mjs` "the word is named exactly once" still asserts the pre-round-3 text of S-PAY-11, and fails with 3 hits against 1 expected (batch 1 verifier). The fix is to the test, by the ticket lane, to match the amended cell. It needs no CR.

### B-3 · S-XCT-20 vs P-HLD-14 (CONFIRM_REDIS_DOWN) and S-SEA-15 · the confirm's 503 sentence

- **Current clause:** "POST /api/showtimes/41/holds and POST /api/bookings each return 503 DEPENDENCY_UNAVAILABLE on the configured client timeout with message 'Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes.'"
- **Why it fails:** the PRD gives the confirm its own sentence. `docs/03 PRD/sections/E2_seat_hold.md`, P-HLD-14, state-table rows `CONFIRM_REDIS_DOWN` (around lines 593-596, 681-684, 857-860), shows "We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote a1b2c3d4." E3 restates that it owns no copy for this row ("Specified once in `P-HLD-14` ... at its *at confirm* row"). The code follows the PRD: `backend/app/domain/booking/__init__.py:72`. The PRD outranks the Bible.
- **Proposed clause:** "POST /api/showtimes/41/holds returns 503 DEPENDENCY_UNAVAILABLE on the configured client timeout with message 'Seat holds are unavailable right now. You can still browse showtimes. Try again in a few minutes.', and POST /api/bookings returns 503 DEPENDENCY_UNAVAILABLE with message 'We cannot complete your booking right now. You have not been charged. Try again in a few minutes. If you need help, quote {request_id}.' (P-HLD-14, CONFIRM_REDIS_DOWN), with `SELECT count(*) FROM payment` unchanged"
- **Why this is not weaker:** it is stricter. It adds the zero-payment assertion, which is the invariant the PRD sentence states.
- **Risk if left as is:** one of S-XCT-20 or S-SEA-15 is always red.
- **Status:** PROPOSED

### B-4 · S-XCT-19 vs S-PAY-07 · "DEL of the lock key" vs the compare-and-delete script

- **Current clause:** "a recording Redis client asserts the command order for one hold is SET lock:seat:41:312 NX, then the transaction COMMIT, then DEL of the lock key, then DEL cache:seatmap:41, in that order and no other"
- **Why it fails:** S-PAY-07 in the same Bible requires "Redis lock release with the compare-and-delete script". A bare DEL can delete a lock that another holder has since taken, which breaks the lock-ownership invariant. The code uses the EVAL, and the test asserts the EVAL and that no bare DEL of a lock key occurs. The row was flipped Done with this deviation filed (round-3 verifier, minor), but the cell was never amended.
- **Proposed clause:** "...then the transaction COMMIT, then EVAL of the compare-and-delete script on the lock key (never a bare DEL of a `lock:` key), then DEL cache:seatmap:41, in that order and no other. The recorder is not reset between the SET NX and the COMMIT, so SET NX < COMMIT is asserted too."
- **Why this is not weaker:** it is stricter on locks, and it closes the round-3 gap where SET NX < COMMIT was not asserted.
- **Risk if left as is:** a Done row stands against its own text. A future lane "restoring" the bare DEL would reintroduce a lock-theft race.
- **Status:** PROPOSED

### B-5 · S-ADM-04 vs PRD S7.9 · "CINEMA_TIMEZONE unset exits"

- **Current clause:** "With CINEMA_TIMEZONE unset, or set to a value zoneinfo.ZoneInfo() raises for, the process exits non-zero before binding its port."
- **Why it fails:** two PRD sources disagree.
  - The S7.9 defaults table (`docs/03 PRD/sections/E8_crosscutting.md:4305`) gives `CINEMA_TIMEZONE` the default `Asia/Kolkata`, and its boot-check rows (`:1269`, `:4407`) refuse only a value that does not resolve.
  - P-ADM-26 (`FrontRow_PRD.md:12585`) says "unset or does not resolve".

  `backend/app/core/config.py:171` follows S7.9. Round 3 settled the same conflict for SEAT_HOLD_TTL_SECONDS, SALES_CUTOFF_MINUTES, SEATMAP_POLL_INTERVAL_SECONDS and CURRENCY_MINOR_UNIT_RATIO in favour of the S7.9 defaults table, citing SRC-002 §7.1 (only a required variable crashes boot).
- **Proposed clause:** "With CINEMA_TIMEZONE unset the process boots with Asia/Kolkata (PRD S7.9 default); set to a value zoneinfo.ZoneInfo() raises for, it exits non-zero before binding its port, naming the variable."
- **Why this is not weaker:** an invalid zone still exits. Local time still comes only from the cinema row (P-ADM-26), and every other clause of the row is unchanged.
- **Risk if left as is:** S-ADM-04 is unpassable against the configuration S7.9 rules.
- **Status:** PROPOSED. P-ADM-26's "unset" wording joins the Q-R3-07 list of PRD self-inconsistencies.

### B-6 · S-BRW-09 vs PRD SCR-BRW-02 · the empty-state sentence on a date that is not empty

- **Current clause:** "a request with date=2026-08-17 returns next_date_with_showtimes null, the copy 'No showtimes for this movie.' renders and the page contains no button whose accessible name starts 'Next: '"
- **Why it fails:** the fixture has an open showtime on 2026-08-17 at 09:00, so the list for that date is not empty. PRD SCR-BRW-02 (exception row 2; States "Empty — every date") uses that sentence only for an empty list with next null. The client renders the PRD behaviour.
- **Proposed clause:** "a request with date=2026-08-17 returns the 09:00 showtime and next_date_with_showtimes null, and the page contains no button whose accessible name starts 'Next: '; a request with date=2026-08-18, which has no showtime on or after it inside the display window, returns an empty list with next_date_with_showtimes null, the copy 'No showtimes for this movie.' renders, and the page contains no 'Next: ' button"
- **Why this is not weaker:** both behaviours are asserted, the last-date case and the truly empty case, against one fixture.
- **Risk if left as is:** to pass, the client would have to show "No showtimes" above a showtime it is listing.
- **Status:** PROPOSED

### B-7 · S-SCP-01 vs EP-ADM-03/04 · `POST /api/admin/movies/import` answers 405, not 404

- **Current clause:** "... POST /api/admin/movies/import and GET /api/pos/sales each return 404 with Content-Type application/json; charset=utf-8 and a body matching the error envelope ... error.code is the literal string NOT_FOUND"
- **Why it fails:** once `GET`/`PATCH /api/admin/movies/{movie_id}` is mounted (EP-ADM-03/04, built in batch 1), `/api/admin/movies/import` matches that template. Starlette answers 405 for a method the template does not mount. An `{movie_id:int}` convertor would change `route.path` and break S-SCP-01's own mounted-minus-contract walk. Batch 1 added this red (`tests/scp/test_s_scp_01.py`) and reported it.
- **Proposed clause:** "... POST /api/admin/movies/import returns 404 NOT_FOUND because its path parameter fails the integer type, answered by the 405 handler in `backend/app/api/errors.py`. That handler answers 404 NOT_FOUND, not 405, whenever the matched template's path parameter does not parse as its declared type. The other four probes are unchanged. Whatever the status, SELECT count(*) FROM movie is unchanged by the request."
- **Why this is not weaker:** 404 is kept, which is what the clause intends: the address does not exist. It adds an assertion that nothing is imported. The alternative, accepting 405, would also be honest, but it tells a caller the path exists, which is weaker.
- **Risk if left as is:** one permanent red that was added by correct work.
- **Status:** PROPOSED. It needs a small code change in the foundation's error handler once approved. The other option (accept 405) is for the client to choose.

### B-8 · S-XCT-10 · "four routers" does not match the per-lane routers

- **Current clause:** "Four routers exist and each carries exactly one authorisation dependency attached at the router: public (no session), customer (/api/me, /api/bookings, /api/holds), reporting (/api/reports, role manager or admin) and admin (/api/admin, role admin only)"
- **Why it fails:** each lane owns its router, and each customer router speaks its own 401 sentence:
  - `api/me.py:46` `caller`
  - `api/holds.py:53` `signed_in`
  - `api/bookings.py:90` `confirm_session`
  - `api/receipts.py:89` `owned_reference`
  - `api/auth_session.py:10` `current_user`
  - `api/reports/__init__.py:30-31` and `api/manager.py:12` `require_reporting` / `require_change_log`
  - `api/admin/__init__.py:22` `require_admin`, with sub-routers carrying none

  The invariant, one dependency per router with every role check in `deps.py`, holds. The count of four does not.
- **Proposed clause:** "Every APIRouter that `backend/app/api` mounts under a non-public prefix carries exactly one authorisation dependency at the router, drawn from `backend/app/api/deps.py`. The admin sub-routers carry none of their own and inherit `require_admin` from `/api/admin`. This is asserted by walking app.routes and finding that every APIRoute under `/api/me`, `/api/bookings`, `/api/holds`, `/api/auth` (except register, login and the reset pair), `/api/reports` and `/api/admin` has exactly one dependency from deps.py on its dependant, and no handler declares a second. The public set is exactly the routes of `api/browse.py`, `api/health.py`, the unauthenticated `api/auth.py` routes and `/metrics`. Every other clause of the row (the deps.py-only role rg, role read per request, 401/403 sentences, 403-before-422, no reporting write verb) is unchanged."
- **Why this is not weaker:** it is stricter. It names every protected prefix and fixes the public set, so a new unprotected router fails.
- **Risk if left as is:** the row asks the code to merge four lanes' routers and lose their distinct published 401 sentences.
- **Status:** PROPOSED. Whether `/metrics` is public is not ruled by this CR; it follows whatever the PRD says for Phase 7, and the build session has not checked that clause.

### B-9 · S-ACC-06 · a "users mapper before_update listener" with no mapper

- **Current clause:** "users.email is written once and never again, asserted at the mapper: a SQLAlchemy before_update event listener registered on the users mapper for the duration of the suite records the changed attribute names of every UPDATE issued against a users row"
- **Why it fails:** the schema is Core tables, so no `users` mapper exists. The lane already uses a Core `before_cursor_execute`/`before_execute` listener instead (ledger judgment call).
- **Proposed clause:** "...asserted at the engine: a SQLAlchemy Core `before_cursor_execute` listener registered for the duration of the module records the SET column names of every UPDATE issued against `users`, ..." (the rest is unchanged).
- **Why this is not weaker:** an engine listener sees every statement, including textual SQL that a mapper event would miss, so it is stricter.
- **Risk if left as is:** the clause names something that cannot exist.
- **Status:** PROPOSED

### B-10 · S-SCP-14 · "after the full suite has run"

- **Current clause:** "SELECT count(*) FROM booking WHERE cancelled_at IS NOT NULL returns 0 after the full suite has run and SELECT DISTINCT status FROM booking returns exactly one row"
- **Why it fails:** each test module creates and drops its own database, so no single database exists after the full suite.
- **Proposed clause:** "...returns 0, and SELECT DISTINCT status FROM booking returns at most the one row `confirmed`, at the teardown of every test module whose database holds a booking. This is asserted by one shared fixture in `backend/tests/conftest.py` that every such module uses, and that fails the module otherwise."
- **Why this is not weaker:** it is stricter. Every booking-writing module's database is checked, not one final database.
- **Risk if left as is:** the clause cannot be run as written.
- **Status:** PROPOSED

### B-11 · S-ADM-22 · an audit count with no entity_type filter

- **Current clause:** "leaves SELECT count(*) FROM audit_log WHERE entity_id = 4 at 1"
- **Why it fails:** `audit_log` carries `entity_type` (`0001_initial_schema.py`, `CREATE TABLE audit_log`), and id 4 is reused across entity types. On any database holding other entities with id 4, the count is wrong.
- **Proposed clause:** "leaves SELECT count(*) FROM audit_log WHERE entity_type = 'language' AND entity_id = 4 at 1"
- **Why this is not weaker:** it is stricter on audit. It counts exactly the entity meant.
- **Risk if left as is:** the test passes or fails depending on fixture order.
- **Status:** PROPOSED

### B-12 · S-XCT-25 · a table and columns that do not exist

- **Current clause:** "The booking's outbox row carries the originating request_id in a request_id column ... asserted by SELECT request_id FROM outbox WHERE booking_id = 9008 returning {request_id}"
- **Why it fails:** the table is `outbox_message` (`0001_initial_schema.py:88`), and it has no `request_id` or `booking_id` column. Both travel in `payload jsonb`, which is the shape that S-PAY-07's own query relies on (`o.payload->>'booking_id'`).
- **Proposed clause:** "The booking's outbox row carries the originating request_id in its payload, it travels in the queue message payload, and it is bound to the worker's logging context for the whole job, asserted by `SELECT payload->>'request_id' FROM outbox_message WHERE topic = 'receipt.send' AND (payload->>'booking_id')::bigint = 9008` returning {request_id}..." (the rest is unchanged).
- **Why this is not weaker:** the end-to-end check is identical. Only the SQL is corrected to the real schema.
- **Risk if left as is:** unpassable as written.
- **Status:** PROPOSED

### B-13 · S-SEA-08 · a 43-character token containing `/` (open question Q-R3-05)

- **Current clause:** "with a token of 42 characters, of 44 characters, or of 43 characters containing `+`, `/` or `=`, it returns 400 REQUEST_INVALID"
- **Why it fails:** `/api/holds/<43 chars with />` is two path segments, so routing answers 404 before the handler runs. The Bible agrees with the PRD (P-HLD-03, EP-HLD-02 block), so this is an implementation gap and not a Bible defect.
- **Proposed fix:** no AC change. See the Q-R3-05 recommendation below: a not-found handler for unroutable `/api/holds/...` paths answers 400 without changing the published routes.
- **Status:** PROPOSED (a code change, no amendment)

---

## Group C — fields a surface does not carry

### C-1 · S-SEA-09 · `Up to 6 seats.` needs a figure no endpoint returns (open question Q-R3-03)

- **Current clause:** "with MAX_SEATS_PER_BOOKING set to 6 and no code change all three of this story's strings re-render at the new cap - the note reads `Up to 6 seats.`"
- **Why it fails:** the cap is rendered on the client, but no response carries it. `docs/03 PRD/api/contract.json` EP-BRW-06 (the seat map) carries `poll_interval_seconds` but no `max_seats_per_booking`. Checked 2026-11-06.
- **Proposed fix:** a contract change (PRD), not a Bible edit. EP-BRW-06's 200 body adds `max_seats_per_booking` (integer, from `MAX_SEATS_PER_BOOKING`), as it already does for `poll_interval_seconds`. The S-SEA-09 cell stays as is.
- **Risk if left as is:** the note can only be met by shipping a literal 10, which the same row forbids.
- **Status:** PROPOSED. **It changes the published contract, so it needs the client's approval.**

### C-2 · S-ADM-28 · "poster reference and runtime_minutes" on two bodies that carry neither

- **Current clause:** "GET /api/me/bookings/{reference} and the receipt for a booking on that film still return the real title, poster reference and runtime_minutes, because they read the movie row directly and not through the S-ADM-27 visibility function"
- **Why it fails:** neither EP-ACC-08 (`/api/me/bookings/{reference}`) nor EP-TKT-01 (`/api/bookings/by-reference/{reference}`) declares a poster field or `runtime_minutes` in `contract.json`. EP-ACC-08 carries `movie_title`. Checked 2026-11-06.
- **Proposed clause:** "GET /api/me/bookings/{reference} and the receipt for a booking on that film still return the real title, byte-identical to the value before the withdrawal, because they read the movie row directly and not through the S-ADM-27 visibility function; the test also asserts that the query behind each body selects from `movie` without the visibility predicate, by a statement listener finding no `published_at` condition in it."
- **Why this is not weaker:** the intent, that withdrawal never hides a film from its own booking, is still proved, on the field that exists plus the query. Adding the two fields to the contract instead would be scope growth.
- **Risk if left as is:** to pass, a lane must add response fields that no contract publishes.
- **Status:** PROPOSED. The other option is to add `poster_url` and `runtime_minutes` to EP-ACC-08 and EP-TKT-01 (a PRD change), and that is for the client to choose.

---

## Group D — Zone C and real-AWS clauses: not a defect, waits for AWS

These are correct as written. Each waits on infrastructure the client builds (`CLAUDE.md`, *Zones*). The build session creates nothing in AWS and has never observed the app running there, so every claim below is reasoned, not observed.

| Row | Clause | What it waits for | Status |
|---|---|---|---|
| S-SEA-18 | "the same script run against the deployed environment by changing only --base-url produces the same three figures" | The deployed ECS service, ALB and RDS (Zone C). The local run passes. The header clause was amended in round 3. | **Not a defect: waits for AWS.** |
| S-BRW-18 | "GET /api/movies/11/poster returns 302 ... X-Amz-Expires=3600 and X-Amz-Signature" | The ECS task role credential chain and the S3 bucket. The local-HMAC half (presigning with static test credentials while outbound sockets are blocked) can be tested without AWS now that boto3 has landed. That half is build work, not a CR. | **Not a defect: the task-role half waits for AWS.** |
| S-XCT-43 (last clause) | "the Zone C specification file ... contains all five literal steps 'request an ACM certificate validated by DNS', ..." | The spec text can be checked now. The ACM certificate, HTTPS listener and SES DKIM/SPF are Zone C, and OPEN-TLS-01 is still open. | **Not a defect: waits for AWS.** |
| T-P1-08 | the 250 MB budget | Which measurement the budget means (RSS, cgroup memory, or the task's memoryReservation) is a client question that needs the t3.micro to measure on. | **Not a defect: waits for AWS and a client answer.** |
| T-P1-09 | "said in chat" | Not AWS and not a doc defect. The orchestrator must announce the Phase 1 AWS needs in chat (CLAUDE.md, *AWS*: advance notice). This is a process step. | **Not a defect: a process step.** |

---

## Group E — ledger notes that are stale (already amended in round 3)

`AMENDMENTS.md` (2026-10-18) already amended these cells, but the ledger's StatusNote still describes the old conflict. No new CR is needed. The owning lane re-runs the test against the amended cell and updates the note.

- **Re-scanned read-only on 2026-11-06, now 0 hits:**
  - S-PAY-04 (`["']FAIL_`)
  - S-BRW-04 (Asia/Kolkata, P-ADM-25 sentence allowed)
  - S-PAY-10 (card-field rg)
- **Not re-run by this track (unverified):**
  - S-SEA-07, S-SEA-11 and S-SEA-15(a) (S7.9 defaults); S-SEA-15(b) (one attempted command)
  - S-BRW-10 and S-BRW-15 (defaults)
  - S-PAY-01(a, b)
  - S-SEA-18 (headers), S-SEA-19 (27 entries)
  - S-SCP-06 (201 and customer). Its test still asserts 400 (round-4 input, minor).
  - S-SCP-12 (backend/tests in scope)
  - S-XCT-12(a, b), and S-XCT-10's path half
  - S-ADM-17 and S-ADM-20's first refund amendment. B-2 above is the remaining gap.

**Rows left out of this CR on purpose**, because they are not AC defects:

- **Rows that need a real browser:** S-ACC-15, S-BRW-02, S-BRW-07, S-BRW-12, S-BRW-13, S-BRW-17, S-SCP-09, S-SCP-10, S-SEA-01..04, S-SEA-12, S-SEA-14, S-SEA-21, S-XCT-38 and S-XCT-39. They wait on an approved browser runner.
- **Rows that wait on unbuilt phases or other lanes:** for example S-ACC-02, S-ACC-09, S-ADM-01, S-SCP-05 and S-XCT-23.
- **Rows whose fix is a test or code follow-up:**
  - S-TKT-10, S-TKT-12, S-TKT-13
  - S-XCT-45: the seed's queue message count can be read from ElasticMQ, so the clause is testable as written.
  - S-XCT-44: the seed must call `app.domain.posters` now that the module exists.
  - S-XCT-33.

---

## Open client questions (copied verbatim from `AMENDMENTS.md`, "Raised, not amended")

The recommended answers below are **recommendations only**. They are not rulings, and nothing here applies them. The round-3 verifier noted that SRC-004 R-6 routes build decisions to the `/llm-council`, not to the client. Q-R3-01, Q-R3-02 and Q-R3-06 are build decisions of that kind, and they are marked below.

> **Q-R3-01** Pricing constant names. S-ADM-13 says BASIS_POINT_SCALE / BASIS_POINT_HALF and S-PAY-02 says BASIS_POINTS_DENOMINATOR / ROUNDING_HALF_NUMERATOR. These are Bible equals, and neither the PRD (E3 P-PAY-03/04, E8 P-XCT-02) nor any ADR names the constants. Recommendation: keep S-ADM-13's pair and amend S-PAY-02.

**Recommended answer (recommendation):** agree. Keep `BASIS_POINT_SCALE` / `BASIS_POINT_HALF`, and amend S-PAY-02's rg to `rg -n 'BASIS_POINT_SCALE|BASIS_POINT_HALF' backend/app` returning definitions only in `backend/app/domain/pricing.py`. A naming choice is a build decision, so route it to the council (SRC-004 R-6) rather than the client.

> **Q-R3-02** Milestones. S-XCT-33 and S-XCT-49 (Milestone 2) need the worker command, and S-PAY-11 (Milestone 4) needs the receipt template. Both arrive in Phase 5 (SRC-002 §12.6). The Bible's own rule says a story may not sit before what it depends on, but S-XCT-33's no-migrate-on-boot clause must hold from Phase 2. Recommendation: split the worker and receipt clauses into Phase 5 rows. That changes the plan, so it is not done here.

**Recommended answer (recommendation):** split. Phase 5 has now landed the worker and the receipt template (batch 1 upheld S-XCT-33), so the split mainly matters for the record: the Phase 2 rows keep only the clauses that hold in Phase 2. It is a plan change, so route it to the council.

> **Q-R3-03** MAX_SEATS_PER_BOOKING has no endpoint field (S-SEA-09, SCR-SEA-01, S7.21). PRD S1.2.1 case 2: a screen renders a figure that no response returns. Recommendation: the PRD adds max_seats_per_booking to the seat-map body, as it already does for poll_interval_seconds.

**Recommended answer (recommendation):** agree. Add `max_seats_per_booking` to the EP-BRW-06 200 body (C-1 above). This is a published-contract change, so the client approves it.

> **Q-R3-04** Copy gaps. There is no published plural for P-SEA-03's "C12 is no longer available" (S-SEA-04), no sentence for three or more lost seats in P-HLD-14 rows 3 and 3b ("change these two"; S-SEA-12), and no sentence for a dropped connection on SCR-PAY-01 / S-PAY-14. Customer copy belongs to the PRD (rank 2), and the lanes' interim strings are their own judgment calls.

**Recommended answer (recommendation):** the client publishes the three sentences in the PRD. Until then, the lanes' interim strings stay, each marked `[JUDGMENT CALL]`. The build session should not invent customer copy (CLAUDE.md: escalate, never invent). As a starting draft for the client to edit, follow the pattern of the existing sentences: list the seats ("C12 and C13 are no longer available."; "C12, C13 and C14 were taken..."). The client writes the final words.

> **Q-R3-05** S-SEA-08 token containing '/'. PRD P-HLD-03 and the EP-HLD-02 block both say 400 REQUEST_INVALID, so the Bible is right and was not edited. The gap is in implementation: the router answers 404 for a two-segment path. A not-found handler for unroutable /api/holds/<43 chars> paths could answer 400 without changing the published routes. Otherwise the PRD has to accept 404 for that one shape.

**Recommended answer (recommendation):** fix it in code, with the not-found handler. Keep the PRD and Bible as written. The handler matches only `^/api/holds/[^?]{43,}$` paths that span more than one segment, and returns the published 400 sentence without touching Redis, which keeps "the Redis command log for that request is empty". This is a build decision, so it goes to the council and needs no client signature.

> **Q-R3-06** Compose profile services. S-XCT-35/36 (and now S-SCP-02) say "exactly six services", but docker-compose.yml also defines the frontrow_roles_init, migrate (profile tools) and test (profile test) services, and it names the static service `frontend`, not `web`. The Bible should say whether profile-gated tool services count.

**Recommended answer (recommendation):** count only the services that start under `docker compose up` with no profile. The check becomes "`docker compose config --services` with no profile lists exactly the six"; profile-gated `migrate` and `test` are excluded by construction. Either the static service is renamed `web`, or the cell is amended to `frontend`; amending the cell is the smaller diff. Also rule whether `frontrow_roles_init`, a one-shot service with no profile, counts. The recommendation is to give it a profile, or else to count it and say "seven". This is a build decision, so it goes to the council.

> **Q-R3-07** PRD self-inconsistencies, not owned here. P-ADM-12's worked example re-quotes C12/C13 at T0+120s after they are sold. P-SEA-01 row 2 restates `held by another customer`. P-XCT-19 says the migrate task "reads DATABASE_URL the same way", but it needs the owner role's URL. E3 P-PAY-12 row 2 ("any v1 endpoint" refuses status/cancelled_at with 400) conflicts with the EP-ACC-01 block, which has no 400.

**Recommended answer (recommendation):** the client approves one PRD errata pass covering all five slips (the four above plus P-ADM-26's "unset" from B-5). Each is corrected to the source already ruled:

- P-ADM-12 uses seats other than C12/C13 (the round-3 S-ADM-15 fix).
- P-SEA-01 row 2 becomes `held by someone else` (SCR-BRW-03).
- P-XCT-19 names the owner-role URL variable.
- P-PAY-12 row 2 reads "any v1 endpoint whose request schema forbids unknown properties", which leaves register's documented ignore-the-role behaviour (EP-ACC-01) intact.
- P-ADM-26 says "does not resolve" only, matching S7.9.

---

## Summary for approval

| Group | Items | Needs a PRD change | Needs a code change after approval |
|---|---|---|---|
| A, grep/rg over-reach | A-1 … A-13 | none | none, beyond the tests re-reading the new cells |
| B, doc conflicts | B-1 … B-13 | B-1 (P-ACC-07 link) | B-7 (the 405 handler answers 404); B-13 (the holds not-found handler) |
| C, fields not carried | C-1, C-2 | C-1 (EP-BRW-06 field); C-2 only if the client prefers adding the fields | C-1 (the seat map returns the cap) |
| D, Zone C | 5 rows | none | none: they wait for AWS |

Every item is **PROPOSED**. Nothing has been applied, committed or pushed.
