# S-SCP-08 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/scp/test_s_scp_08.py passed, 4 tests. New: test_two_seats_either_side_of_a_free_one_are_held_and_are_two_keys (C1 and C3 with C2 free gives 201; SCAN MATCH lock:seat:77:* gives exactly [401, 403]).

**Note:** DependsOn not yet Done: E-SEA, E-BRW. The fixture row is C, not A, so the labels are C1 and C3.
