# S-XCT-23 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/xct/test_s_xct_23.py. Every clause. New: DELETE on /api/admin/movies, showtimes, screens and cinemas and on /api/admin/lookups/{kind} and /{kind}/{id} for all four vocabularies gives the same 405 body, with no DELETE route mounted on any of those templates; DELETE /api/admin/seats/{seat_id} is mounted and answers 204 for a hall with no showtime rows; POST, PUT, PATCH and DELETE on /api/reports/dashboard give the same 405; METHOD_NOT_ALLOWED sits on exactly one line of contract.json. S-XCT-22 (DependsOn) is still Blocked.
