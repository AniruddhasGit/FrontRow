# S-ADM-06 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_06.py, 9 passed ('.........'). The tests: test_a_batch_of_500_is_201_and_501_is_422; the C12/C13/C14 fixture checks duplicate_labels in submitted order, the plural sentence, and that nothing is written; the singular C13 case; coordinate collisions give the singular sentence and '3 of those positions'; each field bound has its own sentence; row_label is stored upper-trimmed, 'I' is allowed, and non-ASCII gives 422 (JC-R6-03); PATCH and DELETE before any showtime write seat.updated and seat.deleted; GET seats comes back in drawing order with has_showtimes and showtime_count; test_a_seat_write_waits_on_the_screen_row_lock (pg_locks granted=false for the app backend pid = 1, then the insert completes 201). The 220-seat / 220 seat.created clause is backend/tests/adm/test_s_adm_02.py::test_a_220_seat_batch_writes_220_seat_created_rows_one_per_seat (passed). Red-proof: with .with_for_update() removed from lock_screen, the lock test went red. Then it was restored.

**Note:** The lock test's holder takes FOR SHARE, not FOR UPDATE. A FOR UPDATE holder also blocks the foreign-key check's FOR KEY SHARE, so the test passed even with the app's lock removed. That was observed, and the test was strengthened.
