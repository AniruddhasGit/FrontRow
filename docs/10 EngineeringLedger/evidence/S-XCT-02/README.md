# S-XCT-02 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_02.py passed, 3 tests. New: test_two_live_holders_constraint_present_dropped_restored, with stage B at PAYMENT_SIMULATED_DELAY_MS=1500. Figures are (confirms_201, confirms_409, rows, exit): present (1,1,1,0), dropped (2,0,2,0), restored (1,1,1,0). The catalogue then shows exactly UNIQUE (showtime_id, seat_id).

**Note:** DependsOn not yet Done: S-XCT-03. The red proof was watched, end to end through EP-PAY-01. The DROP and ADD CONSTRAINT are done by the test on its own throwaway database only. The script never alters the schema.
