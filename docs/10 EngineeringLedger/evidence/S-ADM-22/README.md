# S-ADM-22 — Done

Lane `p6-admin`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_22.py (7 tests) is in the same '74 passed' run.

**Note:** The typo clause uses language id 4004 (OVERRIDING SYSTEM VALUE) instead of the literal 4. The AC's bare 'WHERE entity_id = 4' counts every entity type, so a shared test database would pollute it. The asserted semantics are the same: exactly 1 row, and the language.withdrawn row is still readable.
