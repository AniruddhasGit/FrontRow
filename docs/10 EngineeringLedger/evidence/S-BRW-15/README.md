# S-BRW-15

## 2026-11-07: Done (ledger reconciliation)

**Run:** full backend suite on main, 2026-11-07 (only failure: tests/pay/test_s_pay_11.py::test_no_route_can_withdraw_a_showtime; tests/xct/test_s_xct_28.py and test_s_xct_46.py fixed and passing since), and the frontend node suite, 152/152.

**Evidence:** 2026-10-18 amendment ('missing boots with 3') resolves the config conflict; tests/brw/test_s_brw_15.py asserts default 3 with the variable absent from VALID_ENV, 5 when set, and 'three' exiting; poller.test.mjs (fake timer: per-interval, one in flight, hidden 30 s, visible, 5 s from payload) and seatmap/render.test.mjs:213 (no refresh control, one strip, grid kept); all pass
