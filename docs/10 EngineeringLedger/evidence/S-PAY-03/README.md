# S-PAY-03 — Done

Lane `p4-booking`, workflow wf_61979593-b09, 2026-10-18. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/pay/test_s_pay_03.py, 3 passed (lane run: 247 passed, every failure listed under test_output): test_an_admin_price_change_during_the_hold_changes_nothing_already_held, test_the_confirm_path_calls_no_pricing_function, test_a_hold_with_no_price_snapshot_is_500_and_rolls_back_and_logs_no_money. Red first: the route did not exist (the payment/bookings modules were missing, so S-PAY-05/06 failed at import before any code was written).

**Note:** DependsOn not yet Done: S-PAY-02, E-SEA, E-ADM-A. The flow follows the AC's injected clock: a hold at 14:00:00Z stores 30938. At 14:01:10Z an admin PATCH /api/admin/showtimes/7 sets base 30000 and returns 200. A second customer's hold at 14:01:20Z stores 33750 and is charged 33750. The confirm at 14:02:40Z returns 30938/30938. booking_seat holds (30938, 27500, 1250, category id). After the booking, changing the uplift to 2000 leaves GET /api/me/bookings/{ref} at 30938. If a seat's price_paise is deleted from the Redis hold record, the confirm returns 500 with exactly code/message/details/request_id, 0 bookings and 0 payments, and its log lines carry no *_paise key and no 30938 or 33750 value.
