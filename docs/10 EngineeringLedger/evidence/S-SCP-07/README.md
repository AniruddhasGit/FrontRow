# S-SCP-07 — Done

Lane `render-harness`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** frontend/src/features/admin/render.test.mjs 'S-SCP-07: no control on the showtime list or the edit form matches withdraw|cancel|delete|pull' ✔ (red-proofed: renaming 'Discard this form' to 'Cancel this form' turns it red); API clauses in backend/tests/scp/test_s_scp_07.py, green in the full run (not in the FAILED list)

**Note:** DependsOn not yet Done: E-ADM-A. The admin showtime list (seeded day) and edit form (seeded editing) are rendered with react-dom/server. Every control-role element's accessible name, computed from its attributes, labels and content, is swept. Roles and names come from the harness table, not from a browser accessibility engine.
