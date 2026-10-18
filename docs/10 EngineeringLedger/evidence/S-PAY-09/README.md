# S-PAY-09 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/pay/test_s_pay_09.py, 4 passed: test_two_live_holders_one_wins_and_the_loser_rolls_back_in_full, test_three_lost_seats_are_named_in_hold_order_in_one_server_sentence_and_one_insert, test_no_conflict_clause_and_no_waiver_of_the_guard, test_the_guard_is_one_total_unique_index_on_showtime_and_seat.

**Note:** DependsOn not yet Done: S-PAY-07, E-XCT. The race is the realistic one. A is validated and is inside its gated capture when A's lock key is deleted; B then holds the seat and confirms. B waits on A's showtime row lock and then meets the unique constraint. The loser gets 409 SEAT_UNAVAILABLE with unavailable_seats exactly ['F7'], and the counts are captured 1, booking 1, booking_seat 1. The loser's log line is INFO with error_code SEAT_UNAVAILABLE, with no ERROR line and no 500. Three lost seats give ['F7','F8','F9'] in hold order inside one server sentence, with 2 INSERT INTO booking_seat statements in the window (one per request). There are 0 ON CONFLICT and 0 waiver hits. One unique index exists, on (showtime_id, seat_id) with no WHERE. seat_id = 'F7' raises 'invalid input syntax for type bigint' (the column is bigint; the AC's wording says integer).
