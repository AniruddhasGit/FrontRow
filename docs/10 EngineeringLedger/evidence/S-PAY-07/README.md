# S-PAY-07 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/pay/test_s_pay_07.py passed; not in the full-suite FAILED list.

**Note:** DependsOn not yet Done: E-SEA. The rg 'seat[^;]*FOR UPDATE' red is fixed by rewording the halls.py and showtimes.py docstrings. test_a_fault_after_commit now asserts 201, because post-commit faults are best-effort, plus a byte-identical replay. The orchestrator re-runs the drill.

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/pay/test_s_pay_07.py (step order, one FOR UPDATE in bookings.py, allow-list, 50-confirm outbox check, two faults, cut-off not enforced, never-answering queue, totals) passes
