# S-ACC-10 — Done

Lane `p2-accounts`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_10.py, 5 PASS: test_booking_user_id_is_not_null_and_its_foreign_key_restricts (confdeltype 'r', is_nullable NO), test_the_migration_declares_the_restrict (0001 holds the fk_booking__user_id ... ON DELETE RESTRICT line), test_deleting_a_user_with_a_booking_is_refused_then_red_proved_then_restored (23503 with counts unchanged; then CASCADE: the delete succeeds and booking, user and booking_seat counts are 0/0/0; then RESTRICT is restored, confdeltype is 'r' again and a fresh delete gives 23503), test_a_user_with_no_booking_can_be_deleted_and_its_session_then_ends (401 'Sign in to continue.'), test_no_route_takes_a_booking_owner_from_the_request (58 contract endpoints; only EP-ADM-24 carries {user_id}; no owner field under /api/bookings, /api/me/ or /api/showtimes; the DELETEs are exactly ADM-21, HLD-03 and HLD-04; the mounted routes agree).

**Note:** The red-proof also flips fk_booking_seat__booking_id to CASCADE and back (see doc_defects).
