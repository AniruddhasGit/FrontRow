# S-XCT-33 — Done

Lane `blocked-fix`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/xct/test_s_xct_33.py::test_the_api_one_revision_behind_starts_healthy_and_fails_at_the_first_request_touching_a_new_column: alembic upgrade 0001 (the revision before the latest, 0002), alembic_version == 0001, /health/live 200, /health/ready 200, an old-column read 200, a showtime.created_at read (a column 0002 adds) -> 500 INTERNAL_ERROR. Passes in the full run and the targeted run. The zero-revision test is kept.

**Note:** DependsOn not yet Done: S-XCT-29. ponytail: the test is pinned to the 0001->0002 pair. A later revision keeps it a valid one-behind case. The AC's 'one revision behind head' is literal only while 0002 is the head; when 0003 lands, the pair should move.
