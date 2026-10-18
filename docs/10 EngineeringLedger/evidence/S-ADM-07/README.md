# S-ADM-07 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_07.py, 7 passed ('.......'). The tests: test_frozen_fields_and_delete_are_409_with_their_sentences_and_no_audit_row (row_label, seat_number, seat_category_id, DELETE; details keys exactly screen_id, seat_id, showtime_count, frozen_fields; audit count unchanged); test_in_the_same_state_grid_service_add_and_rename_stay_permitted; test_a_past_unbooked_showtime_freezes_exactly_like_a_future_sold_out_one; test_a_future_sold_out_showtime_refuses_identically (bodies equal apart from request_id and ids); test_the_domain_function_raises_layout_frozen_with_no_http_request; test_the_check_is_not_in_the_handler (rg showtime_count|LAYOUT_FROZEN over api/admin = 0); test_exactly_one_route_accepts_row_label_and_it_is_patch_seat. Red-proof: with the freeze condition disabled, 3 tests went red. Then it was restored.

**Note:** LayoutFrozen is in backend/app/domain/admin/halls.py.
