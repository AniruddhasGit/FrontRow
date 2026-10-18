# T-P1-06 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** `docker stop -t 30 p1c-api` gave exit code 0 on both runs. Run 1: docker stop took 2402 ms. Run 2: 6397 ms, with log `api stopped cleanly` shutdown_ms=5391; Postgres and Redis were both stopped at that point, which is the known DNS-thread delay. Both are inside the 30 s grace period. In-flight drain: tests/test_shutdown.py::test_sigterm_drains_an_in_flight_request_and_exits_zero passed (the request completed 200, a new connection was refused, exit 0). The hook list app.state.shutdown_hooks exists and is empty in Phase 1.

**Note:** The OwnedPath backend/app/core/shutdown.py does not exist. The hook list is in main.py and drain/exit is in server.py. Nothing is released in Phase 1.
