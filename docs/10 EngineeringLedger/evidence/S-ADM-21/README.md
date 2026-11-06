# S-ADM-21 — Done

Lane `p6-admin`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_21.py (8 tests) is inside the 74-passed run of tests/adm/test_s_adm_21..28 in compose project frontrow_p6 ('74 passed in 60.50s'). frontend/src/features/admin/films.test.mjs 'S-ADM-21: an empty language list renders no language select and the empty-vocabulary sentence instead' passed under node --test (12/12 admin tests pass, tsc -b exit 0).

**Note:** DependsOn not yet Done: S-ADM-01, S-ADM-02. Every clause is asserted: the four kinds, studio answering 404 with the sentence, the audit row, the 60/61 bounds, the duplicate active and withdrawn sentences, Drama in two tables, the trim and the admin's case kept, is_active/id answering 400, the list shape and order, reference_count 2 then 3, the two DELETEs answering 405, no rename route, the unseeded empty list, and the SCR-ADM-02 empty-language render. A minor gap: 'two rows with different ids' is not asserted as id inequality, because ids in separate tables may legitimately coincide.
