# T-P1-04 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** Real containers. Both up: 200 {"status":"ready","checks":{"postgres":"ok","redis":"ok"},"payment_provider":"simulated"}. Redis stopped: 503 {"status":"not_ready","checks":{"postgres":"ok","redis":"unreachable"},...}. Postgres stopped: 503 {..."postgres":"unreachable","redis":"ok"...}. Both stopped: 503 naming both. Also passed: test_s_xct_21.py::test_ready_503_names_what_is_down_while_live_stays_200[3 cases].

