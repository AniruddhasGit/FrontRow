# S-XCT-21 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_21.py: 15 passed. Covered: live issues 0 probes and 0 SQLAlchemy statements (counting before_cursor_execute listener on the real engine); ready 200 body with checks and payment_provider; 503 for postgres, redis and both while live stays 200; ready stays 200 with SQS, SES and S3 pointed at unroutable endpoints; a real server process against a blackholed (accept-and-never-answer) Postgres returns 503 in under 2 s with a 10 s httpx client timeout; a second request inside the 3 s TTL issues no probe; no cookie needed; no version, hostname or URL in the body; 'restart loop' appears in health.py; /health/ready appears on the load balancer queue row; the 'reversing them...' sentence is in P1_ALB.md. Real stopped-container outputs are listed under T-P1-03 and T-P1-04.

**Note:** The 'counting Redis client wrapper' is the counting readiness probe, because that probe is the only Redis caller in the process.
