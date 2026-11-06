# S-ADM-30

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/adm/test_s_adm_30.py (11 tests pass); docs/06 DataModel/seed/expected_summary.json admin_grant; frontend/src/features/admin/access.test.mjs
