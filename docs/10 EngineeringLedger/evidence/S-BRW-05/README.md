# S-BRW-05 — Done

Lane `render-harness`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** render.test.mjs 'S-BRW-05: a control renders only at two or more values; an outage says so exactly once' ✔; backend/tests/brw/test_s_brw_05.py green

**Note:** DependsOn not yet Done: S-BRW-01. 'A filter already present in the URL is still applied': the test loads /?language_id=2 with /api/reference failed and sees the filter in the rendered state ('Clear filters'). The request is built from that state inside an effect, and SSR runs no effects, so the GET itself is not observed.
