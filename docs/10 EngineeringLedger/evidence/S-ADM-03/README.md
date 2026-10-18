# S-ADM-03 — Done

Lane `p2-admin`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/adm/test_s_adm_03.py, 7 passed ('tests/adm/test_s_adm_03.py .......'). The tests: test_list_is_ordered_and_carries_every_field, test_rename_with_matching_version_is_200_version_plus_one_and_one_cinema_updated_row, test_name_and_zone_in_one_request_write_two_rows, test_an_unknown_zone_a_121_character_name_and_a_taken_name_are_422_with_nothing_written (Asia/Atlantis, 121 chars, lower(trim) collision), test_a_stale_version_is_409_and_writes_nothing, test_no_create_and_no_delete_route_and_both_answer_405_from_the_global_handler, test_a_hall_without_cinema_id_is_422_and_never_defaulted. Red-proof: with check_version disabled, test_a_stale_version_is_409_and_writes_nothing went red. Then the check was restored.

**Note:** EP-ADM-28/29 live in backend/app/api/admin/cinemas.py and backend/app/domain/admin/cinemas.py. The items also carry showtime_count, as EP-ADM-28 specifies.
