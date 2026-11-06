# S-ADM-27 — Done

Lane `p6-admin`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_27.py (7 tests) is in the '74 passed' run.

**Note:** DependsOn not yet Done: S-ADM-25. The single predicate lives in app/domain/visibility.py; the rg plus an AST walk find callers only in catalogue.py and films.py. The preconditions are re-read under FOR UPDATE: a second connection clears the window mid-handler and the request still answers 409. Separate published and window_open fields are returned, with no live/is_live/visible key.
