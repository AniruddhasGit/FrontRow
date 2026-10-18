# S-TKT-01 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/tkt/test_s_tkt_01.py, 6 passed: test_a_stubbed_draw_is_stored_as_eight_upper_case_characters, test_a_thousand_references_fit_the_alphabet_and_carry_their_check_character, test_the_unique_constraint_refuses_a_second_copy, test_four_collisions_then_a_free_value_books, test_five_collisions_is_500_and_sells_nothing, test_the_source_is_secrets_and_never_random.

**Note:** DependsOn not yet Done: E-PAY. The reference comes from the existing app/domain/reference.py (R-5) inside the confirm transaction. Each draw is inserted in a SAVEPOINT; only uq_booking__reference violations are retried, at most 5 draws (app.state.draw_reference is the stub port). A stubbed draw stores (8, true). 1000 references written to booking all match the alphabet and carry the check character. A second INSERT of a stored reference raises UniqueViolation and the count stays 1. 4 collisions then a free value gives 201 after 5 draws. 5 collisions give 500, with 0 bookings for the user and 0 booking_seat for the seat. 'import secrets' >= 1 hit and 'random\.' 0 hits in backend/app. Implemented in domain/booking rather than the row's listed domain/receipt.
