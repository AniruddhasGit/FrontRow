# S-ADM-05 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_05.py, 6 passed ('......'). The tests cover: 201 with is_active true, has_showtimes false, version 1 and one screen.created row; duplicate and case-variant names refused with count unchanged; trimmed lengths 0 and 61 give 422 and 60 gives 201; rename gives version+1 and screen.updated, and also works on a hall that has showtimes; the list carries every field, in name order; there is no DELETE route, and DELETE answers 405 with 'That action is not available. Nothing was changed.' with screen count unchanged.

