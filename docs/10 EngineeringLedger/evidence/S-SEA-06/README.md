# S-SEA-06 — Done

Lane `p4-seats`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/sea/test_s_sea_06.py, 8 passed: test_each_refusal_holds_nothing_and_sends_no_set[x6] (C2 twice, C7 twice, C19 not in this hall, C12 out of service, empty list, 999999 gives 404), test_membership_is_the_materialised_set_not_the_screen, test_membership_and_service_are_independent_checks. Also passes in the final full run.

**Note:** DependsOn not yet Done: E-ADM-A. The sorted KEYS lock:seat:77:* is unchanged in every case and no SET is sent. Seat 419 was added after showtime 77: it is refused on 77 and returns 201 on showtime 99, which was created after it. Seat 412 is in the showtime's seat set and is out of service, so it gets the out-of-service sentence. Judgment call: a seat id that matches no seat anywhere has no label to name, so it gets the registry's generic VALIDATION_FAILED wording.
