# S-XCT-06 — Done

Lane `p2-integrate`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_06.py: 12 passed (pytest -rA, 2026-10-18), including the three new HTTP-path tests through the real EP-ADM-11 PATCH /api/admin/showtimes/41 as admin 17: test_http_the_price_change_and_its_audit_row_commit_together, test_http_a_failing_audit_insert_rolls_the_price_back, test_http_a_failing_update_leaves_no_audit_row. The request_id is read from X-Request-Id or error.request_id and must match ^[0-9a-f]{8}$. The 9 earlier mechanism tests still pass. Output is in scratchpad/integ_done_evidence.txt.

**Note:** The lane note's only gap was the HTTP path through EP-ADM-11, which the admin lane has now built. Every clause is proved on that path as well. In the failing-UPDATE case the patched object is sqlalchemy's update inside app.domain.admin.showtimes.
