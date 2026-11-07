# S-SEA-14 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/browse_seat.test.mjs; e2e/checks/pay_ticket_account.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** One polite insertion at 1:00, urgent colours on digits and bar, localStorage empty, reload resumes on the same expires_at, closing sends nothing and the keys still EXIST; the confirm-in-flight-not-aborted clause is the S-PAY-14 test (0:00 with a confirm in flight).
