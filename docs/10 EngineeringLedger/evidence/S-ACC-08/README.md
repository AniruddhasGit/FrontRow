# S-ACC-08 — Done

Lane `p7-ops`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/acc/test_s_acc_08.py: 8 passed (live token -> 200 + new fr_session, version 1->2, last_signed_in_at from the injected clock, used_at set, old cookie 401 AUTH_REQUIRED, new 200; forced rollback leaves used_at null, hash and version unchanged; 50 simultaneous -> [200]+[400]*49 RESET_TOKEN_INVALID 'already been used', no RATE_LIMITED, version 2; unknown and expired sentences; 42/44/0/missing -> 422 with zero statements from a before_cursor_execute listener; 42 chars -> 422 not 503 with the DB port closed; OpenAPI body properties == {token, password}, old_password ignored -> 200, outbox count unchanged; token in no DEBUG line)

**Note:** DependsOn not yet Done: S-ACC-07, S-ACC-02. No audit row: PRD E5 (sections/E5_account.md:234-236) audits only admin changes (P-ADM-19), not customer activity.
