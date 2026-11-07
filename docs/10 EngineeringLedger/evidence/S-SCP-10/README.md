# S-SCP-10 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/pay_ticket_account.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Choosing a Language sends GET /api/movies?language_id=... while html lang and the nav link names stay byte-identical, as guest and as customer.
