# S-XCT-03

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/xct/test_s_xct_03.py (allow-list, 409 rows 4/4b, INFO, read committed), test_s_xct_02.py, test_s_xct_27.py::test_a_seat_conflict_at_confirm_increments_seat_conflicts_total pass. PARENT: docs/10 EngineeringLedger/evidence/S-XCT-03/ does not exist; status-law needs it for Done
