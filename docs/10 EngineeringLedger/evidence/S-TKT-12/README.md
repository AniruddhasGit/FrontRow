# S-TKT-12 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/tkt/test_s_tkt_12.py; frontend/src/features/ticket/ticket.test.mjs (ENTRY). Every clause. New: test_presenting_one_reference_twice_writes_nothing - count(*) of every public base table (audit_log among them) is identical before and after two owner GET /api/bookings/by-reference/FR-ACDE-FHJD calls, both 200. Recorded equivalence: `python -m pip freeze` is read as importlib.metadata over the same dist-info, because the venv is built --without-pip; the test image is FROM builder, whose venv the runtime image copies, so its distribution set contains the runtime's.
