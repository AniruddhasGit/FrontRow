# S-ACC-02

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** tests/acc/test_s_acc_02.py (test_eleven_characters_on_reset_confirm_is_refused_with_the_same_sentence + 9 others) all pass in pytest_merged.txt
