# S-SCP-14 — Done

Gap-closing lane, 2026-11-07. Not yet reviewed by a fresh zero-context session.

**Evidence:** backend/tests/scp/test_s_scp_14.py, 4 passed (`docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q -p no:cacheprovider tests/scp/test_s_scp_14.py`). The tests: test_no_live_response_and_no_published_schema_carries_status_or_the_timestamp (GET /api/me/bookings, GET /api/me/bookings/{reference} and the 201 body, key by key, plus the EP-ACC-07, EP-ACC-08, EP-TKT-01 and EP-PAY-01 response schemas in contract.json); test_the_by_reference_read_carries_neither (GET /api/bookings/by-reference/{reference}); test_neither_can_be_set_and_status_is_written_once (POST /api/bookings with status or cancelled_at is 400 REQUEST_INVALID); test_the_shared_teardown_check_fails_on_a_violating_booking (red-proof of the shared check: a booking given a cancelled_at, then a status 'withdrawn', each makes it raise).

**The shared teardown fixture:** `migrated_db` in backend/tests/conftest.py (moved there from tests/dbkit.py) tears down through tests/dbkit.py `drop_database`, which now runs `assert_bookings_never_cancelled` first: `SELECT count(*) FROM booking WHERE cancelled_at IS NOT NULL` must be 0 and `SELECT DISTINCT status FROM booking` a subset of {confirmed}, else the module's teardown fails (the database is still dropped). Every module's database, and every ad-hoc database a test drops through drop_database, is checked. Broad run with the fixture in place: see the lane report (tests/tkt, pay, scp, sea, seed, xct 04/34).

The confirmation page's policy line directly beneath the entry line, on first render and a later visit, is asserted in frontend/src/features/ticket/ticket.test.mjs.
