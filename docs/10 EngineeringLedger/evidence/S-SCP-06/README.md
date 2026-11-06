# S-SCP-06

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** 2026-10-18 amendment (role: staff -> 201 customer, S-ACC-01/EP-ACC-01) resolves the conflict, and SRC-008 ROLE-1 keeps the four roles. tests/scp/test_s_scp_06.py asserts the enum, the vocabulary rg, no role field, and register with role staff -> 201 + customer; all pass
