# S-XCT-07 — Done

Lane `p2-foundation`, workflow wl883ib1u, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/xct/test_s_xct_07.py: 8 PASS. information_schema.table_privileges for current_user frontrow_app is exactly [INSERT, SELECT]. UPDATE and DELETE on audit_log as frontrow_app raise InsufficientPrivilege. Both through HTTP give 500 INTERNAL_ERROR with message 'The server could not complete this request. If you need help, quote {request_id}.', where request_id matches ^[0-9a-f]{8}$ and equals X-Request-Id. 'base_price_changed' is refused with 500 and showtime 41 is never 28000 (count 0); 'showtime.base_price_changed' is accepted. AUDIT_ACTIONS is the module-level tuple in backend/app/domain/audit.py (39 members, transcribed from P-ADM-19). Every action= literal in backend/app is a member. Mutation: with the boundary check removed, the paraphrase test went red, then it was restored.

**Note:** The two HTTP clauses use a route mounted by the test on the real app. No product endpoint may ever UPDATE audit_log, and EP-ADM-11 does not exist yet. That route uses the documented handler pattern: check_action() before conn.begin(), then write_audit() inside it. The admin lane's real handler must call check_action() before begin(); re-verify there.
