# S-ADM-16 — Done

Run 2026-11-07 (fork A of the blocked-rows sweep), `MSYS_NO_PATHCONV=1 docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest -q -p no:cacheprovider tests/adm/test_s_adm_04.py ... tests/adm/test_s_adm_18.py -rA`.

**Evidence:** backend/tests/adm/test_s_adm_16.py, 5 passed. New: test_the_customer_booking_still_renders_the_retired_seat - a booking on C12, the seat taken out of service, then GET /api/me/bookings/{reference} as the customer (cached_client, Redis 9, because EP-ACC-08 rate-limits) returns 200 with seats [C12], identical to the body before the toggle. The other four tests (audit rows and 409 sentences, the screen-row lock wait, the seat sets before and after, no cancel/refund segment) were already there and pass.
