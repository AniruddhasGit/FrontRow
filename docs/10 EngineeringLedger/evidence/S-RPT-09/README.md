# S-RPT-09 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/rpt/test_s_rpt_09.py, green: BEGIN ISOLATION LEVEL REPEATABLE READ is captured in the server log and the key set is exact; a booking committed from a second connection between the headline and per-film queries leaves 2783331, then the next request gives 2808331; an injected per-film failure gives a 500 with no takings_paise, the message ends 'quote {rid}.' and no 4xx body contains 'quote '. The truncated case is asserted in tests/rpt/test_s_rpt_08.py::test_the_cap[101-True].

**Note:** 
