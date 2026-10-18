# S-ADM-10 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_10.py, 5 passed ('.....'). The tests: test_overlap_is_409_and_the_zero_gap_and_later_creates_are_201 (exact sentence 'Screen 3 already has a showtime from 6:30 pm to 8:58 pm on 4 Sep 2026...', conflicts array with exactly 4 keys and naive local times, 20:58-22:53 gives 201); test_c_at_21_15_is_201_and_two_conflicts_give_an_array_of_two; test_the_edit_predicate_excludes_its_own_row_as_captured_from_the_statement (a before_cursor_execute capture: the edit SQL carries 'showtime.id !=' and the create SQL does not); test_two_concurrent_overlapping_creates_produce_one_201_and_one_409 (count +1); test_no_changeover_minimum_exists_anywhere. Red-proof: with the predicate made closed (<=, >=), the zero-gap test went red. With the screen lock removed, the concurrency test went red. Both were restored.

