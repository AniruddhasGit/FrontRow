# S-RPT-02 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/rpt/test_s_rpt_02.py (test_bad_period_and_date_are_422 x4, test_no_bound_on_the_anchor_in_either_direction x2, test_rendered_instants_carry_the_offset_and_no_utc_suffix): green. frontend reports.test.mjs 'S-RPT-02: no text node on /dashboard or /dashboard/audit is a bare UTC instant': pass. src/test/reports_absence.test.mjs source sweep (_utc in features/reports = []): pass.

**Note:** DependsOn not yet Done: E-XCT. 
