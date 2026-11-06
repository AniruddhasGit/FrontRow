# S-RPT-01 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/rpt/test_s_rpt_01.py: test_day_week_month_windows_from_the_injected_clock, test_the_interval_is_half_open_so_a_late_show_belongs_to_the_next_local_day, test_the_zone_is_read_from_the_cinema_row, test_no_wall_clock_and_no_database_clock_on_this_surface. Passed as part of 'tests/rpt tests/scp/test_s_scp_16.py' (99 passed, 0 failed, frontrow_p8).

**Note:** DependsOn not yet Done: E-XCT, E-ADM-A. The zone is read from the cinema row by load_zones/default_zone. Both period edges are computed in Python from the injected clock and reach SQL only as bound parameters.
