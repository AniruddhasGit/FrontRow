# S-PAY-01 — Done

Lane `blocked-fix`, workflow wf_db5fb564-900, 2026-11-06. Verifier verdict: PASS_WITH_DEFECTS; this row was not refuted.

**Evidence:** backend/tests/pay/test_s_pay_01.py: test_an_unset_ratio_boots_with_the_s7_9_default_of_100 (rewritten to the amended AC), test_a_zero_or_non_integer_ratio_is_refused_naming_it[0|1.5], test_the_process_exits_before_binding_and_stderr_names_the_variable, test_the_money_columns_are_exactly_four_and_all_bigint (LIKE '%paise%'), test_pricing_holds_no_float_or_decimal (pricing.py + bookings.py), test_pricing_never_multiplies_or_divides_by_a_literal_100 (pricing, bookings, domain/payment), test_the_201_body_carries_integer_paise_and_no_formatted_money (166146 as a JSON int, 27500 applied, no banned keys, no rupee sign). All pass (both baseline pay_01 reds cleared).

**Note:** DependsOn not yet Done: E-ADM-A. Absent -> the S7.9 default of 100. Invalid -> still refused.
