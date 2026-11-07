# S-XCT-22 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/pay_ticket_account.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Five 409 codes give five different strings (SEAT_UNAVAILABLE, SALES_CLOSED, HOLD_EXPIRED, IDEMPOTENCY_IN_FLIGHT, VERSION_CONFLICT); a 4xx hides and a 5xx shows the request id on checkout, confirmation, bookings, reset request and sign-in.
