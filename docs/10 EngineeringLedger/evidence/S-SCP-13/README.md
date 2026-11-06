# S-SCP-13

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** EP-TKT-01 now exists: tests/scp/test_s_scp_13.py asserts the 80000 total and sum, no extra key in the live bodies or the contract, the by-reference _paise keys == [total_paise], and promo/discount -> 400 REQUEST_INVALID. ticket.test.mjs:34 asserts the five fact labels with PAID the only money. All pass
