# S-XCT-25 — Done

Lane `blocked-fix`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/xct/test_s_xct_25.py: all 3 pass, including test_the_request_id_reaches_the_worker_line_through_the_outbox_and_the_queue. Its API half finds a line with service api, route /api/bookings, status_code 201 and booking_id 9008. That line comes from the new log.info('booking confirmed', extra={route, status_code, booking_id}) in backend/app/api/bookings.py.

**Note:** DependsOn not yet Done: S-XCT-24, E-TKT. The AC's 'SELECT request_id FROM outbox' still names a table and column that do not exist (the test reads outbox_message.payload->>'request_id'). This is a doc defect and does not block the row.
