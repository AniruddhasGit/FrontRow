# S-SCP-04 — Done

Lane `p2-seed-scope`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/scp/test_s_scp_04.py (5 tests: booking columns, table names, users columns, password_reset_token.used_at exempt and present, the patterns watched matching what they refuse) against a DB built by the real `migrate` entrypoint command. Run: `docker compose --profile test run --rm test python -m pytest ... tests/scp/test_s_scp_04.py` -> `tests/scp/test_s_scp_04.py .....` inside `102 passed in 265.17s`.

**Note:** All four clauses asserted against alembic upgrade head on an empty database.
