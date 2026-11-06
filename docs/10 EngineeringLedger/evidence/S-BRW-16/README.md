# S-BRW-16 — Done

Clause-gap pass, 2026-11-07. The writer did not verify its own work: no second reviewer was used. That is recorded here.

**Evidence:** backend/tests/brw/test_s_brw_16.py passed 11 of 11, from `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q tests/brw/test_s_brw_16.py`.

New tests:
- **test_an_admin_publish_raises_the_generation_by_exactly_one_and_the_next_read_shows_the_film:** a real POST /api/admin/movies/{id}/publish. cache:listing:generation rises by exactly 1, and the next listing read returns the film. Over the publish plus one listing read, the recorded command log holds exactly one `^INCR cache:listing:generation$` and at least one `^SETEX cache:listing:`. It holds 0 of `^SET cache:listing:`, `^SCAN` and `^(SET|DEL) cache:listing:generation`.
- **test_a_booking_commit_whose_seatmap_del_raises_still_commits_logs_once_and_the_entry_expires:** a real hold and POST /api/bookings, with the seat-map cache on at 10 s and DEL cache:seatmap:7 forced to raise. The confirm returns 201 and the booking and booking_seat rows exist. The log holds exactly one DEL for the key, and exactly one WARNING line carries the confirm's x-request-id. PTTL is at most 10000, and TTL then reads -2.

The existing tests cover these clauses:
- the TTLs of 60 and 10;
- the stampede: one NX PX 2000 winner, four losers each re-reading once and each querying PostgreSQL;
- a deleted counter's INCR returning 1;
- Redis stopped, with byte-identical 200s at a pinned instant.

The booking-commit DEL is also asserted by tests/pay/test_s_pay_07.py. The page-text sweep is in frontend/src/features/browse/render.test.mjs.
