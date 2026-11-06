# S-TKT-13 — Done

Run 2026-11-07, branch worktree-agent-a2148c98c2e80639c: `docker compose -p frontrow --profile test run --rm --no-deps test python -m pytest` over the 19 touched/related backend files - 175 passed, 0 failed in 308.38s.

**Evidence:** backend/tests/tkt/test_s_tkt_13.py; frontend/src/features/ticket/ticket.test.mjs ('dispatch state'). Every clause. New: two bookings identical except receipt_dispatch sent vs failed (same owner) give GET /api/bookings/by-reference/{r} bodies that are equal once the reference is removed; and SCR-TKT-01 (ConfirmationPage, renderToStaticMarkup) for the same pair renders markup identical once the reference is replaced (node --test: 6 pass, 0 fail).
