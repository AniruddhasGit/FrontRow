# S-ADM-26 — Done

Lane `p6-admin`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_26.py (8 tests) is in the '74 passed' run.

**Note:** DependsOn not yet Done: S-ADM-23, S-ADM-14. All clauses pass with the injected clock (set_clock): zone designators answer 422, the 05:30 offset is stored, values come back naive, display_until is exclusive at 18:29:59/18:30:00Z, nothing is rounded or derived, the merged-row bound holds, a past window is accepted, the two audit rows carry their exact keys, and published_at is preserved.
