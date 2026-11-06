# S-ADM-01

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/adm/test_s_adm_01.py (8 tests: role matrix on /api/admin/movies, require_admin on every route, 32-route count, AST/rg, manager GET/HEAD, per-request role, 403 equality) all pass
