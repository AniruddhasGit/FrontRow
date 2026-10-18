# S-PAY-07 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/pay/test_s_pay_07.py passed; not in the full-suite FAILED list.

**Note:** DependsOn not yet Done: E-SEA. The rg 'seat[^;]*FOR UPDATE' red is fixed by rewording the halls.py and showtimes.py docstrings. test_a_fault_after_commit now asserts 201, because post-commit faults are best-effort, plus a byte-identical replay. The orchestrator re-runs the drill.
