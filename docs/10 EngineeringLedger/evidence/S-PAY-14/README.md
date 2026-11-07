# S-PAY-14 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/pay_ticket_account.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** At 0:00 'Hold expired', one polite line, one 5000 ms timer, route moves at 5000 not 4999, fr.selection re-applied; in flight at 0:00 nothing aborts and the late 201 navigates; the hold clears fr.last_booking_reference; past the cut-off no request and the panel unchanged.
