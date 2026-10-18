# S-ACC-12 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/acc/test_s_acc_12.py, 4 passed: test_the_boundary_is_ends_at_on_the_injected_clock, test_each_group_is_totally_ordered_and_pages_cleanly, test_ends_at_is_stored_and_not_nullable, test_this_module_never_reads_a_clock_or_sleeps.

**Note:** The booking is upcoming at 09:30Z, past at exactly 11:05Z and past at 11:06Z, on the injected clock. Five bookings, three sharing one starts_at, come back in the exact id order: starts asc (upcoming) or desc (past), then created_at desc, then id asc. Paging at page_size=2 across 3 requests returns every id exactly once. ends_at is_nullable is NO.
