# S-SCP-01 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/scp/test_s_scp_01.py: 8 passed. They cover contract endpoint_count == 58, mounted-minus-contract empty against the working tree's routers (FastAPI 0.143 _IncludedRouter walked through effective_candidates), no excluded-path match, and the 5 excluded URLs each returning 404, content-type application/json; charset=utf-8, error.code NOT_FOUND and an 8-hex request_id. Live compose check: GET /api/export/bookings.csv returned 404, application/json; charset=utf-8, {"error":{"code":"NOT_FOUND","message":"That page does not exist.","details":{},"request_id":"f2d8c07c"}}.

**Note:** charset=utf-8 is added once, centrally, in core/request_context.py for every application/json response.
