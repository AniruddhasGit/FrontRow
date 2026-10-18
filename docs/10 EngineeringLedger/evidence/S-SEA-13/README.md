# S-SEA-13 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/sea/test_s_sea_13.py passed, 6 tests, adding test_a_release_before_the_confirm_revalidates_ends_the_confirm_with_nothing_charged and test_a_release_after_the_commit_deletes_nothing_and_is_hold_expired. Not in the full-suite FAILED list.

**Note:** DependsOn not yet Done: S-SEA-08. Release before re-validation: the release answers 204, the confirm answers 409 HOLD_EXPIRED, and there are zero payment_sleep calls and no payment row. Release after commit: both DELETE forms give 409 HOLD_EXPIRED and booking_seat (77,402) count is 1. The (status, code) pairs are exactly (204, none) and (409, HOLD_EXPIRED). The ordering is driven sequentially; no concurrent interleaving is injected.
