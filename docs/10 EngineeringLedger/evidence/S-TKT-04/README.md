# S-TKT-04 — Done

2026-11-07, real-browser verification (Playwright, Chromium 1248) against the local stack: Vite :5173 and docker compose (api, worker, postgres, redis, elasticmq). Owner's request: make sure the PRD is met and works.

**Evidence:** `e2e/checks/pay_ticket_account.test.mjs`, run with `cd e2e && npm run check`; the full run's output is `e2e/evidence/run_all.txt` and screenshots are in `e2e/evidence/`.

**What was proved:** Fixed 2026-11-07: the loading state rendered nothing (now the frame with an empty .fr-ref) and the 'Send the receipt again' control in the clause's tab order did not exist (added; existing resend endpoint). Focus on h1, DOM order heading/reference/copy/facts/resend, copy announces, no receipt phrase on reload. JUDGMENT CALL: queued:false shows 'A receipt is already being sent for this booking.' (PRD gap, on the owner list).
