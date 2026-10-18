# S-XCT-37 — Done

Lane `phase1-close`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_37.py: 6 passed. Covered: no task-queue or argon2 requirement; no forbidden JS library; every package in both manifests is on the recorded allowlist in the test; forbidden services appear only on lines saying forbidden (backend/app, migrations, frontend/src, docs/30); no minio or mailhog in compose; the 'local development does not fully exercise...' sentence is in P1_EC2_ECS_CLUSTER.md; '## Services this product uses' lists exactly the 10 services.

**Note:** The allowlist includes sqlalchemy, alembic, pyjwt, bcrypt (added by the Phase 2 lane) and boto3, with the source for each. A new package fails this test until someone records it there.
