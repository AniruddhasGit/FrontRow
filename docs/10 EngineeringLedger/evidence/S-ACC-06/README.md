# S-ACC-06 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/acc/test_s_acc_06.py. Every clause as the CR-002 B-9 cell states it. The users.email write-once clause now uses a SQLAlchemy Core before_cursor_execute listener on the app's engine that reads the SET column names out of every UPDATE against users while register, login, logout, reset request and confirm, POST /api/admin/managers and PUT /api/admin/managers/{id}/screens run; the recorded set is exactly {last_signed_in_at, password_hash, password_version}. The earlier before_execute hook is gone.
