# S-PAY-04

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/pay/test_s_pay_04.py (bounds 17999/18000/60000/0, TTL 60, provider unset/stripe, prefixes a/deadbeef/FAIL_/unset/33 chars, quoted-FAIL_ sweep, boot line) passes
