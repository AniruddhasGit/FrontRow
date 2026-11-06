# S-PAY-15

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/pay/test_s_pay_15.py (402 twice, failed rows 2, no booking, no idempotency record, then 201 with one booking and one capture; FAIL_ rg over frontend/src); checkout.test.mjs 'no control in the product names the failure prefix'; test_s_pay_04.py::test_a_prefix_drawn_from_the_uuid_alphabet_is_refused
