# S-BRW-14 — Done

Lane `render-harness`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** seatmap/render.test.mjs 'S-BRW-14: the mixed grid row between two bands means no band rule; the legend keeps payload order' ✔ and 'S-BRW-14: every grid row mixed...' ✔; model.test.mjs bands test ✔; backend/tests/brw/test_s_brw_14.py green

**Note:** DependsOn not yet Done: S-BRW-11, S-BRW-13. Data-band-rule count 0 on the AC's 6-row hall; the legend follows payload order ([9,3] renders 9 first); a category in two runs gets one legend row; when every row is mixed there are 0 data-band and 0 data-band-rule elements and one mixed notice.
