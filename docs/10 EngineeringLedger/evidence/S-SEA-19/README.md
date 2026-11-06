# S-SEA-19

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/sea/test_s_sea_19.py (hold rows, substitution, 429, regex sweep, code-set equality); row 4: test_s_pay_09.py:52 and test_s_xct_03.py ONE; row 4b: test_s_xct_03.py TWO; row 18: test_s_sea_15.py:137; row 10: render.test.mjs:295 / hold.test.mjs:55; all pass
