# S-SCP-16 — Done

Lane `p8-reports`, workflow wf_4a2fdba9-2d0, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/scp/test_s_scp_16.py (test_json_utf8_and_no_content_disposition x4 endpoints, test_no_export_address_exists x3 including /api/admin/bookings.csv giving 404 NOT_FOUND) green. frontend src/test/reports_absence.test.mjs 'S-SCP-16 / S-RPT-21: no control on a dashboard route is named for an export, and no a[download]' (with a non-vacuity guard): pass.

**Note:** DependsOn not yet Done: E-RPT. 
