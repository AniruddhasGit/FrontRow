# S-SEA-05 — Done

Lane `p4-seats`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/sea/test_s_sea_05.py, 4 passed: test_three_seats_are_three_single_set_nx_px_commands_in_ascending_order, test_a_lost_seat_releases_what_this_request_won_and_never_writes_the_rest, test_a_nil_on_a_key_this_customer_already_holds_is_not_a_loss_and_extends_nothing, test_a_seat_with_a_committed_booking_takes_the_rollback_path. Red observed first: the route did not exist and the first test returned 404 NOT_FOUND. They also pass in the final full run (scratchpad full2.txt: 823 passed, 11 failed, every failure in another lane's file).

**Note:** DependsOn not yet Done: S-SEA-02, E-ACC, E-ADM-A. Each clause is asserted against the app's recorded Redis command log and SQL log. The SET commands go out as SET key token NX PX 180000, in the order 402, 410, 418, with no SETNX and no EXPIRE. The token is 43 characters and expires_at is 14:05:37.412Z. The rollback releases only 402 and 418 is never written. A nil on the customer's own key is a no-op, and the new seat gets PX 150000, the time left on the hold. The holds:user index and the instance:{id}:holds registry are set with TTLs of 179 to 180 s. DEL cache:seatmap:77 comes after the last lock SET. No INSERT or UPDATE is sent.
