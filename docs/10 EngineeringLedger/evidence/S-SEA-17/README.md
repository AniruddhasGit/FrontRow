# S-SEA-17 — Done

Lane `p4-close`, workflow wf_d4b6fac7-d2f, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** tests/sea/test_s_sea_17.py passed, 4 tests. New: test_a_confirm_in_flight_when_sigterm_arrives_completes_and_commits. It runs a real tests/drain_harness.py process with PAYMENT_SIMULATED_DELAY_MS=3000, sees the confirm's transaction 'idle in transaction' in pg_stat_activity, sends a real SIGTERM, and gets the confirm's 201, exit code 0, and booking_seat count 1.

**Note:** The process runs inside the test image, not as a container. The container-level SIGTERM and SIGKILL stages remain drill_live (sigterm, sigkill), which the orchestrator re-runs; I did not run them.
