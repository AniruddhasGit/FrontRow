# S-PAY-10

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/pay/test_s_pay_10.py (rg, 400 not echoed in the log line, 201 key set, 166146 three ways, the four _paise columns); test_s_pay_08.py:172 (OpenAPI additionalProperties false, exactly hold_token and showtime_id); checkout.test.mjs (no input, no tax/fee text, the 13 children in order, $1,661.46); rg re-run 2026-11-07 returns 0 hits
