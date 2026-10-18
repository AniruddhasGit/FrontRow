# S-ADM-13 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/adm/test_s_adm_13.py and test_s_adm_13_count.py passed. New: test_patch_validates_the_uplift_with_the_same_sentences; the DELETE now asserts (405, METHOD_NOT_ALLOWED); the GET body keys equal {items, affected_future_showtimes, evaluated_at_utc}.

**Note:** DependsOn not yet Done: S-ADM-12, S-ADM-14. The three missing clause tests are added. DependsOn S-ADM-12 and S-ADM-14 are still Blocked; the orchestrator decides.
