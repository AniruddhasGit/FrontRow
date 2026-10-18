# S-PAY-05 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/pay/test_s_pay_05.py, 4 passed: test_a_confirm_captures_through_three_states_and_records_the_key, test_capture_from_pending_and_anything_from_failed_is_refused, test_a_rolled_back_attempt_then_a_fresh_key_leaves_one_failed_and_one_captured, test_this_module_measures_no_real_time_and_the_provider_has_no_http_client. Red first: ImportError, cannot import name 'payment' from 'app.domain'.

**Note:** DependsOn not yet Done: S-PAY-04, S-PAY-01. The payment row reads (captured, 166146, the key sent), with all three timestamps set. payment has no booking_id column. capture from pending raises InvalidPaymentTransition and leaves (pending, null). From failed, both authorize and capture raise and the state stays failed. One payment row per key. A FAIL_ attempt followed by a fresh key gives exactly failed 1 and captured 1. The delay port app.state.payment_sleep was called exactly once, with [1500]. backend/app/domain/payment has 0 HTTP-client hits.
