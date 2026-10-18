# S-XCT-19 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_19.py passed. New: test_after_a_hold_a_release_and_a_booking_the_entry_is_gone (EXISTS 0 after each); test_the_command_order_for_a_seat_from_hold_to_booking (COMMIT < lock EVAL < DEL cache:seatmap:7, and no bare DEL of the lock key); test_a_seatmap_del_that_raises_is_not_retried_and_the_booking_stands (1 attempt, booking 1, PTTL 0<x<=10000).

**Note:** DependsOn not yet Done: E-BRW. Deviation (doc defect): the AC says 'DEL of the lock key'. The release is the compare-and-delete EVAL, which the lock invariant requires; a bare DEL could delete another holder's key. 'Gone within 10 s' is asserted as PTTL <= 10000 on Redis's own clock rather than by waiting.
