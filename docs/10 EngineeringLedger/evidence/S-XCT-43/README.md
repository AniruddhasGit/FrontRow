# S-XCT-43 — Done

Lane `p2-integrate`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/xct/test_s_xct_43.py: 8 passed (pytest -rA), including the new test_the_tls_spec_is_found_through_the_queue_rows_spec_cell. Row 14 of AWS_PREP_QUEUE.md (Item: 'TLS certificate') now has [`P2_TLS_CERTIFICATE.md`](P2_TLS_CERTIFICATE.md) in its Spec cell. test_s_xct_40 then required the four headings, so P2_TLS_CERTIFICATE.md's heading was normalised to '## What to build'. tests/xct/test_s_xct_40.py::test_every_named_spec_exists_and_carries_the_four_headings passes.

**Note:** DependsOn not yet Done: S-XCT-13. Its DependsOn, S-XCT-13, is still Blocked. The orchestrator decides whether that holds the flip. The key-material check walks the filesystem, not git ls-files, because the test image has no git. That walk covers a superset of the tracked files, so it is stricter.
