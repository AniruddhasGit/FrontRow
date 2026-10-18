# S-SEA-05 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/sea/test_s_sea_05.py (5 passed, including the new test_a_rollback_on_an_extend_never_releases_a_seat_already_in_the_hold). Full-suite run in frontrow_p4close: none of test_s_sea_05 in the FAILED list.

**Note:** DependsOn not yet Done: S-SEA-02, E-ACC, E-ADM-A. Was already Done. Verifier gap closed. On an extend where 402 is already held, 403 is won and 410 is lost: the only compare-and-delete is for 403, 402 keeps the hold's token with its PTTL not raised, the hold still reads [402], and the answer is 409 ['C10'].
