# S-ACC-11 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_11.py, 8 passed: test_two_upcoming_and_thirty_seven_past_page_independently, test_each_row_carries_exactly_the_published_keys_and_the_cinemas_offset, test_out_of_bounds_parameters_are_422[page=0,page=1001,page_size=0,page_size=51,group=other], test_no_session_is_401_and_no_bookings_is_two_empty_arrays.

**Note:** DependsOn not yet Done: E-PAY. Paging gives page 1 (2, 20), page 2 (0, 17), page 3 (0, 0), all 200. With group=upcoming, past is [] and total_past is 37. Each row's keys are exactly the 10 published ones, with a FR-XXXX-XXXX reference and offset times (+05:30). Seats order as ['F2','F10'] and ['F7','F8','F9'] even when booked in the order F9, F7, F8. total_paise 153000 is a JSON int. No session gives 401 'Sign in to see your bookings.' and no bookings gives two empty arrays with totals 0. The API is backend/app/api/me.py and the queries are in domain/booking. These tests were written after me.py existed, so a red was not observed for this row.
