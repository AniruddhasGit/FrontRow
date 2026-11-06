# S-XCT-12 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/xct/test_s_xct_12.py. Every clause. New HTTP test: 11 characters -> 422 with the floor sentence; 25 Devanagari characters (75 bytes) -> 422 quoting 75 and no row stored; 72 Latin -> 201; a second registration -> 409 EMAIL_ALREADY_REGISTERED; wrong password and unknown email -> 401 CREDENTIALS_INVALID; Nikhil@Example.invalid read back unchanged; a 255-character email -> 422 and a 254-character one -> 201. Also to_thread.run_sync counted >= 1 over api/auth.py + domain/accounts, and Correct-Horse-99! in no captured stdout line (DEBUG) and no response body.
