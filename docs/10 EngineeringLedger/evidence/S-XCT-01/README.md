# S-XCT-01 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_01.py passed, 4 tests. The new test runs scripts/stress_seats.py unchanged (STRESS_OPERATOR set) against a real api process in the frontrow_p4close compose project: winners 1, losers 49, distinct_users 50, unique_constraint_violations 0, spread_ms < 100, run_at ending in Z, winner_confirm_status 201, booking_seat count 1 read from PostgreSQL.

**Note:** DependsOn not yet Done: S-XCT-03, S-XCT-48, E-SEA, E-PAY. The api is the real boot path (drain_harness: load_settings, create_app, uvicorn) in the test container, not the compose 'api' service. The base URL is 127.0.0.1:<free port>, not localhost:8000. The login bucket is raised to 60 for the warm-up only. DependsOn S-XCT-48 is still Blocked (orchestrator's evidence file); the orchestrator decides.
