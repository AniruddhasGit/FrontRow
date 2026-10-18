# S-ADM-08 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_08.py, 5 passed ('.....'). The tests: test_the_sequence_501_to_504 (90/91/90, restoring J11 leaves 503 at 90, 504 = 91, 501 = 90 throughout, PATCH changes neither count, census query = 0); test_zero_seats_in_service_is_409_and_no_showtime_is_written; test_both_unique_indexes_exist_by_name_and_are_different_jobs; test_no_route_edits_a_seat_set_and_such_addresses_are_404 (POST /showtimes/501/seats and DELETE /showtimes/501/seats/77 give 404 'That page does not exist.'); test_a_failing_seat_set_insert_is_503_and_leaves_no_showtime.

**Note:** The test caught a real bug: the async driver reports rowcount -1 for INSERT ... SELECT, so seat_count_at_creation came out as -1. Fixed by counting RETURNING rows. uq_showtime_seat__showtime_id_seat_id exists by name in information_schema, but its constraint_type is PRIMARY KEY, not UNIQUE: PostgreSQL folded the duplicate UNIQUE into the PK and kept the unique's name (observed). See doc_defects.
