# S-SCP-11 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/scp/test_s_scp_11.py; backend/tests/xct/test_s_xct_45.py (seed COPY count). Every clause. The run-time trace is now the cell's Core before_cursor_execute listener on the engine: it walks the frames of the cursor's greenlet and then its parent greenlets' suspended stacks (greenlet.parent.gr_frame), which hold the awaiting coroutines, and records inspect.getmodule(frame).__name__; for every INSERT INTO booking_seat in a full confirm the app.domain.* set is exactly {app.domain.booking}.
