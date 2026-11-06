# S-RPT-04 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/rpt/test_s_rpt_04.py::test_both_halves_in_one_test green (in the 99 passed).

**Note:** DependsOn not yet Done: S-RPT-03, E-PAY, E-TKT. Both halves are in one test: A gets 250000, checked against the query the test runs itself and strictly below the admin's 350000; screen 2 is refused with 403; manager B gets scope_empty with 0.
