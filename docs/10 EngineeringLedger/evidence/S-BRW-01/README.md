# S-BRW-01 — Done

Clause-gap pass, 2026-11-07. The writer did not verify its own work: no second reviewer was used. That is recorded here.

**Evidence:** backend/tests/brw/test_s_brw_01.py passed 10 of 10, from `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q tests/brw/test_s_brw_01.py`. The new assertion is in test_poster_showtime_and_seatmap_are_ungated_at_the_exclusive_bound. At T=2026-08-21T00:00:00+05:30 the excluded film's GET /api/movies/{id}/poster returns 302 with a signed Location. GET /api/showtimes/{id} and /seatmap each return 200. The other tests cover these clauses:
- the four window instants;
- the null gate columns;
- no COALESCE and the three SQL fragments;
- the direct execution returning 0 rows;
- the 404 body matching a never-existing id once request_id is removed, with the request ids differing;
- 0 and abc returning 422 with zero statements.

The rendered copy 'That movie is not showing.' is asserted in frontend/src/features/browse/render.test.mjs.
