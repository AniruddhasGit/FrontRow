# S-SCP-05

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** EP-BRW-07 GET /api/reference is built and tested: tests/brw/test_s_brw_05.py:53 asserts cinemas length 1 (positive). tests/scp/test_s_scp_05.py covers the other three assertions; all pass
