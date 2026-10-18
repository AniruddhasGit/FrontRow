# S-BRW-08 — Done

Lane `render-harness`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** render.test.mjs 'S-BRW-01, S-BRW-08: a film that is not showing renders its sentence and the way back' ✔ and 'S-BRW-08: a date with no showtimes renders ...' ✔; backend/tests/brw/test_s_brw_08.py green

**Note:** DependsOn not yet Done: S-BRW-01. MovieScreen is seeded with film 'missing' / an empty list with next date set (PRD SCR-BRW-02 exception row 1).
